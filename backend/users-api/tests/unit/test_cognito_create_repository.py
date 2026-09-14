from typing import Any

import pytest
from botocore.exceptions import (  # type: ignore[import-untyped]
    ClientError,
    EndpointConnectionError,
)
from users_api.errors import (
    CognitoAliasExistsError,
    CognitoCreateDeterministicError,
    CognitoIdentityInvariantError,
    CognitoResultAmbiguousError,
    CognitoServiceError,
    CognitoUsernameExistsError,
    CognitoUserNotFoundError,
)
from users_api.repositories.cognito_repository import CognitoRepository

USER_ID = "11111111-1111-4111-8111-111111111111"
COGNITO_SUB = "22222222-2222-4222-8222-222222222222"
EMAIL = "admin@example.test"


def client_error(code: str, operation: str, *, status: int = 400) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": "sensitive provider detail"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        operation,
    )


def compatible_response() -> dict[str, Any]:
    return {
        "Username": USER_ID,
        "UserAttributes": [
            {"Name": "sub", "Value": COGNITO_SUB},
            {"Name": "email", "Value": " ADMIN@EXAMPLE.TEST "},
            {"Name": "email_verified", "Value": "true"},
            {"Name": "custom:unrelated", "Value": "accepted"},
        ],
    }


class FakeCognitoClient:
    def __init__(self) -> None:
        self.create_error: Exception | None = None
        self.get_error: Exception | None = None
        self.delete_error: Exception | None = None
        self.disable_error: Exception | None = None
        self.user = compatible_response()
        self.create_calls: list[dict[str, object]] = []
        self.get_calls: list[dict[str, object]] = []
        self.delete_calls: list[dict[str, object]] = []
        self.disable_calls: list[dict[str, object]] = []

    def admin_create_user(self, **kwargs: object) -> dict[str, Any]:
        self.create_calls.append(kwargs)
        if self.create_error is not None:
            raise self.create_error
        return {"User": {"Username": USER_ID}}

    def admin_get_user(self, **kwargs: object) -> dict[str, Any]:
        self.get_calls.append(kwargs)
        if self.get_error is not None:
            raise self.get_error
        return self.user

    def admin_get_user_auth_factors(self, **kwargs: object) -> dict[str, Any]:
        raise AssertionError(f"unexpected auth factors call: {kwargs}")

    def admin_delete_user(self, **kwargs: object) -> dict[str, Any]:
        self.delete_calls.append(kwargs)
        if self.delete_error is not None:
            raise self.delete_error
        return {}

    def admin_disable_user(self, **kwargs: object) -> dict[str, Any]:
        self.disable_calls.append(kwargs)
        if self.disable_error is not None:
            raise self.disable_error
        return {}


def repository(client: FakeCognitoClient) -> CognitoRepository:
    return CognitoRepository(client, "pool-1")


def test_admin_create_user_uses_stable_username_and_suppressed_message() -> None:
    client = FakeCognitoClient()
    repository(client).admin_create_user(user_id=USER_ID, email=" ADMIN@EXAMPLE.TEST ")

    assert client.create_calls == [
        {
            "UserPoolId": "pool-1",
            "Username": USER_ID,
            "UserAttributes": [
                {"Name": "email", "Value": EMAIL},
                {"Name": "email_verified", "Value": "true"},
            ],
            "MessageAction": "SUPPRESS",
            "ForceAliasCreation": False,
        }
    ]
    assert "TemporaryPassword" not in client.create_calls[0]


def test_admin_get_user_returns_only_reconciled_technical_identity() -> None:
    client = FakeCognitoClient()
    identity = repository(client).admin_get_user(user_id=USER_ID, expected_email=EMAIL)

    assert identity.user_id == USER_ID
    assert identity.cognito_sub == COGNITO_SUB
    assert not hasattr(identity, "email")
    assert client.get_calls == [{"UserPoolId": "pool-1", "Username": USER_ID}]


def test_admin_get_user_rejects_non_object_response() -> None:
    client = FakeCognitoClient()
    client.user = []  # type: ignore[assignment]
    with pytest.raises(CognitoIdentityInvariantError, match="response"):
        repository(client).admin_get_user(user_id=USER_ID, expected_email=EMAIL)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda response: response.update(Username="other"), "username"),
        (
            lambda response: response["UserAttributes"].__setitem__(0, {"Name": "email"}),
            "attribute",
        ),
        (
            lambda response: response.update(UserAttributes="invalid"),
            "attributes",
        ),
        (
            lambda response: response["UserAttributes"].__setitem__(
                0, {"Name": "sub", "Value": "invalid"}
            ),
            "sub",
        ),
        (
            lambda response: response.update(
                UserAttributes=[
                    {"Name": "email", "Value": EMAIL},
                    {"Name": "email_verified", "Value": "true"},
                ]
            ),
            "sub",
        ),
        (
            lambda response: response.update(
                UserAttributes=[
                    {"Name": "sub", "Value": COGNITO_SUB},
                    {"Name": "email_verified", "Value": "true"},
                ]
            ),
            "email",
        ),
        (
            lambda response: response["UserAttributes"].__setitem__(
                1, {"Name": "email", "Value": "other@example.test"}
            ),
            "email",
        ),
        (
            lambda response: response["UserAttributes"].__setitem__(
                2, {"Name": "email_verified", "Value": "false"}
            ),
            "verified",
        ),
        (
            lambda response: response["UserAttributes"].__setitem__(
                2, {"Name": "email_verified", "Value": True}
            ),
            "attribute",
        ),
        (
            lambda response: response["UserAttributes"].append(
                {"Name": "sub", "Value": COGNITO_SUB}
            ),
            "duplicated",
        ),
    ],
)
def test_admin_get_user_rejects_incompatible_or_malformed_identity(
    mutate: Any,
    message: str,
) -> None:
    client = FakeCognitoClient()
    mutate(client.user)
    with pytest.raises(CognitoIdentityInvariantError, match=message):
        repository(client).admin_get_user(user_id=USER_ID, expected_email=EMAIL)


@pytest.mark.parametrize(
    ("code", "error_type"),
    [
        ("UsernameExistsException", CognitoUsernameExistsError),
        ("AliasExistsException", CognitoAliasExistsError),
        ("InvalidParameterException", CognitoCreateDeterministicError),
        ("AccessDeniedException", CognitoServiceError),
        ("InternalErrorException", CognitoResultAmbiguousError),
    ],
)
def test_admin_create_user_classifies_client_errors(
    code: str,
    error_type: type[Exception],
) -> None:
    client = FakeCognitoClient()
    client.create_error = client_error(
        code,
        "AdminCreateUser",
        status=500 if code == "InternalErrorException" else 400,
    )
    with pytest.raises(error_type) as captured:
        repository(client).admin_create_user(user_id=USER_ID, email=EMAIL)
    assert EMAIL not in str(captured.value)
    assert "sensitive provider detail" not in str(captured.value)


def test_admin_create_user_classifies_transport_timeout_as_ambiguous() -> None:
    client = FakeCognitoClient()
    client.create_error = EndpointConnectionError(endpoint_url="https://cognito.invalid")
    with pytest.raises(CognitoResultAmbiguousError):
        repository(client).admin_create_user(user_id=USER_ID, email=EMAIL)


@pytest.mark.parametrize(
    ("error", "error_type"),
    [
        (client_error("UserNotFoundException", "AdminGetUser"), CognitoUserNotFoundError),
        (
            client_error("InternalErrorException", "AdminGetUser", status=500),
            CognitoResultAmbiguousError,
        ),
        (client_error("AccessDeniedException", "AdminGetUser"), CognitoServiceError),
        (
            EndpointConnectionError(endpoint_url="https://cognito.invalid"),
            CognitoResultAmbiguousError,
        ),
    ],
)
def test_admin_get_user_classifies_read_errors(
    error: Exception,
    error_type: type[Exception],
) -> None:
    client = FakeCognitoClient()
    client.get_error = error
    with pytest.raises(error_type):
        repository(client).admin_get_user(user_id=USER_ID, expected_email=EMAIL)


def test_compensation_calls_use_only_stable_username() -> None:
    client = FakeCognitoClient()
    repo = repository(client)

    repo.admin_delete_user(user_id=USER_ID)
    repo.admin_disable_user(user_id=USER_ID)

    expected = [{"UserPoolId": "pool-1", "Username": USER_ID}]
    assert client.delete_calls == expected
    assert client.disable_calls == expected


@pytest.mark.parametrize(
    ("operation", "error", "error_type"),
    [
        (
            "delete",
            client_error("UserNotFoundException", "AdminDeleteUser"),
            CognitoUserNotFoundError,
        ),
        (
            "delete",
            EndpointConnectionError(endpoint_url="https://cognito.invalid"),
            CognitoResultAmbiguousError,
        ),
        (
            "disable",
            client_error("AccessDeniedException", "AdminDisableUser"),
            CognitoServiceError,
        ),
    ],
)
def test_compensation_calls_classify_sanitized_errors(
    operation: str,
    error: Exception,
    error_type: type[Exception],
) -> None:
    client = FakeCognitoClient()
    if operation == "delete":
        client.delete_error = error
    else:
        client.disable_error = error

    with pytest.raises(error_type) as captured:
        if operation == "delete":
            repository(client).admin_delete_user(user_id=USER_ID)
        else:
            repository(client).admin_disable_user(user_id=USER_ID)

    assert "sensitive provider detail" not in str(captured.value)
