from copy import deepcopy
from typing import Any, cast

import pytest
from botocore.exceptions import (  # type: ignore[import-untyped]
    ClientError,
    EndpointConnectionError,
    ReadTimeoutError,
)
from users_api.errors import (
    CognitoIdentityInvariantError,
    CognitoResultAmbiguousError,
    CognitoServiceError,
    CognitoUserNotFoundError,
)
from users_api.repositories.cognito_repository import (
    CognitoRepository,
    ReconciledCognitoReactivationState,
)

USER_ID = "11111111-1111-4111-8111-111111111111"
COGNITO_SUB = "22222222-2222-4222-8222-222222222222"
EMAIL = "synthetic@example.test"


def compatible_user(*, enabled: bool) -> dict[str, object]:
    return {
        "Username": USER_ID,
        "Enabled": enabled,
        "UserStatus": "CONFIRMED",
        "UserAttributes": [
            {"Name": "sub", "Value": COGNITO_SUB},
            {"Name": "email", "Value": EMAIL},
            {"Name": "email_verified", "Value": "true"},
            {"Name": "custom:ignored", "Value": "safe"},
        ],
    }


def client_error(code: str, operation: str, *, status: int = 400) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": "secret@example.test token-secret"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        operation,
    )


class FakeCognitoClient:
    def __init__(self) -> None:
        self.user: object = compatible_user(enabled=False)
        self.enable_response: object = {}
        self.get_error: Exception | None = None
        self.enable_error: Exception | None = None
        self.get_calls: list[dict[str, object]] = []
        self.enable_calls: list[dict[str, object]] = []

    def admin_create_user(self, **kwargs: object) -> dict[str, Any]:
        raise AssertionError(f"unexpected create call: {kwargs}")

    def admin_get_user(self, **kwargs: object) -> dict[str, Any]:
        self.get_calls.append(kwargs)
        if self.get_error is not None:
            raise self.get_error
        return cast(dict[str, Any], self.user)

    def admin_get_user_auth_factors(self, **kwargs: object) -> dict[str, Any]:
        raise AssertionError(f"unexpected auth factors call: {kwargs}")

    def admin_delete_user(self, **kwargs: object) -> dict[str, Any]:
        raise AssertionError(f"unexpected delete call: {kwargs}")

    def admin_disable_user(self, **kwargs: object) -> dict[str, Any]:
        raise AssertionError(f"unexpected disable call: {kwargs}")

    def admin_enable_user(self, **kwargs: object) -> dict[str, Any]:
        self.enable_calls.append(kwargs)
        if self.enable_error is not None:
            raise self.enable_error
        return cast(dict[str, Any], self.enable_response)


def repository(client: FakeCognitoClient) -> CognitoRepository:
    return CognitoRepository(client, "pool-1")


def readback(
    client: FakeCognitoClient,
    *,
    expected_enabled: bool | None,
) -> ReconciledCognitoReactivationState:
    return repository(client).admin_get_reactivation_state(
        user_id=USER_ID,
        expected_cognito_sub=COGNITO_SUB,
        expected_email=" SYNTHETIC@EXAMPLE.TEST ",
        expected_enabled=expected_enabled,
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_reactivation_readback_uses_exact_parameters_and_validates_enabled(enabled: bool) -> None:
    client = FakeCognitoClient()
    client.user = compatible_user(enabled=enabled)

    state = readback(client, expected_enabled=enabled)

    assert state.user_id == USER_ID
    assert state.cognito_sub == COGNITO_SUB
    assert state.enabled is enabled
    assert client.get_calls == [{"UserPoolId": "pool-1", "Username": USER_ID}]


@pytest.mark.parametrize("enabled", [False, True])
def test_reactivation_resume_readback_can_observe_either_enabled_state(enabled: bool) -> None:
    client = FakeCognitoClient()
    client.user = compatible_user(enabled=enabled)

    state = readback(client, expected_enabled=None)

    assert state.enabled is enabled


def test_new_reactivation_rejects_compatible_identity_that_is_already_enabled() -> None:
    client = FakeCognitoClient()
    client.user = compatible_user(enabled=True)

    with pytest.raises(CognitoIdentityInvariantError, match="enabled state is incompatible"):
        readback(client, expected_enabled=False)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda response: response.update(Username="different"), "username is incompatible"),
        (lambda response: response.update(UserStatus="RESET_REQUIRED"), "status is incompatible"),
        (lambda response: response.update(Enabled="false"), "enabled state is malformed"),
        (lambda response: response.update(UserAttributes=[]), "sub is missing"),
        (
            lambda response: response["UserAttributes"].append(
                {"Name": "sub", "Value": COGNITO_SUB}
            ),
            "attribute is duplicated",
        ),
        (
            lambda response: response["UserAttributes"].__setitem__(
                0, {"Name": "sub", "Value": "not-a-uuid"}
            ),
            "sub is missing or invalid",
        ),
        (
            lambda response: response["UserAttributes"].__setitem__(
                0, {"Name": "sub", "Value": "33333333-3333-4333-8333-333333333333"}
            ),
            "sub is incompatible",
        ),
        (
            lambda response: response["UserAttributes"].__setitem__(
                1, {"Name": "email", "Value": "different@example.test"}
            ),
            "email is incompatible",
        ),
        (
            lambda response: response["UserAttributes"].__setitem__(
                2, {"Name": "email_verified", "Value": "false"}
            ),
            "email is not verified",
        ),
    ],
)
def test_reactivation_readback_rejects_incompatible_identity(
    mutation: Any,
    message: str,
) -> None:
    client = FakeCognitoClient()
    response = compatible_user(enabled=False)
    mutation(response)
    client.user = response

    with pytest.raises(CognitoIdentityInvariantError, match=message) as captured:
        readback(client, expected_enabled=False)

    assert EMAIL not in str(captured.value)


@pytest.mark.parametrize(
    "response",
    [
        None,
        [],
        {},
        {"Username": USER_ID, "Enabled": False, "UserStatus": "CONFIRMED"},
        {
            **compatible_user(enabled=False),
            "UserAttributes": [{"Name": "sub", "Value": COGNITO_SUB}, "malformed"],
        },
    ],
)
def test_reactivation_readback_rejects_malformed_response(response: object) -> None:
    client = FakeCognitoClient()
    client.user = deepcopy(response)

    with pytest.raises(CognitoIdentityInvariantError) as captured:
        readback(client, expected_enabled=False)

    assert EMAIL not in str(captured.value)
    assert "token-secret" not in str(captured.value)


def test_reactivation_enable_uses_only_pool_and_stable_username() -> None:
    client = FakeCognitoClient()

    repository(client).admin_enable_user(user_id=USER_ID)

    assert client.enable_calls == [{"UserPoolId": "pool-1", "Username": USER_ID}]
    assert client.get_calls == []


@pytest.mark.parametrize(
    ("operation", "error", "error_type"),
    [
        (
            "read",
            client_error("UserNotFoundException", "AdminGetUser"),
            CognitoUserNotFoundError,
        ),
        (
            "read",
            client_error("AccessDeniedException", "AdminGetUser"),
            CognitoServiceError,
        ),
        (
            "read",
            client_error("InternalErrorException", "AdminGetUser", status=500),
            CognitoResultAmbiguousError,
        ),
        (
            "read",
            EndpointConnectionError(endpoint_url="https://secret.invalid"),
            CognitoResultAmbiguousError,
        ),
        (
            "enable",
            client_error("UserNotFoundException", "AdminEnableUser"),
            CognitoUserNotFoundError,
        ),
        (
            "enable",
            client_error("InvalidParameterException", "AdminEnableUser"),
            CognitoServiceError,
        ),
        (
            "enable",
            client_error("InternalErrorException", "AdminEnableUser", status=500),
            CognitoResultAmbiguousError,
        ),
        (
            "enable",
            client_error("ServiceUnavailable", "AdminEnableUser", status=503),
            CognitoResultAmbiguousError,
        ),
        (
            "enable",
            ReadTimeoutError(endpoint_url="https://secret.invalid", error="token-secret"),
            CognitoResultAmbiguousError,
        ),
        ("enable", RuntimeError("secret@example.test token-secret"), CognitoResultAmbiguousError),
    ],
)
def test_reactivation_calls_classify_and_sanitize_failures(
    operation: str,
    error: Exception,
    error_type: type[Exception],
) -> None:
    client = FakeCognitoClient()
    if operation == "read":
        client.get_error = error
    else:
        client.enable_error = error

    with pytest.raises(error_type) as captured:
        if operation == "read":
            readback(client, expected_enabled=None)
        else:
            repository(client).admin_enable_user(user_id=USER_ID)

    rendered = str(captured.value)
    assert "secret@example.test" not in rendered
    assert "token-secret" not in rendered
    assert "secret.invalid" not in rendered


@pytest.mark.parametrize("response", [None, [], "unexpected", 200])
def test_malformed_enable_response_is_ambiguous(response: object) -> None:
    client = FakeCognitoClient()
    client.enable_response = response

    with pytest.raises(CognitoResultAmbiguousError):
        repository(client).admin_enable_user(user_id=USER_ID)

    assert client.enable_calls == [{"UserPoolId": "pool-1", "Username": USER_ID}]
