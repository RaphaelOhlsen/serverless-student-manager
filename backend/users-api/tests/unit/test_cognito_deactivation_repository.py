from typing import Any

import pytest
from botocore.exceptions import (  # type: ignore[import-untyped]
    ClientError,
    EndpointConnectionError,
)
from users_api.errors import (
    CognitoIdentityInvariantError,
    CognitoResultAmbiguousError,
    CognitoServiceError,
    CognitoUserNotFoundError,
)
from users_api.repositories.cognito_repository import CognitoRepository

USER_ID = "11111111-1111-4111-8111-111111111111"
COGNITO_SUB = "22222222-2222-4222-8222-222222222222"


def client_error(code: str, operation: str, *, status: int = 400) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": "sensitive provider detail"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        operation,
    )


class FakeCognitoClient:
    def __init__(self) -> None:
        self.user: object = {
            "Username": USER_ID,
            "Enabled": True,
            "UserAttributes": [
                {"Name": "sub", "Value": COGNITO_SUB},
                {"Name": "email", "Value": "synthetic@example.test"},
            ],
        }
        self.get_error: Exception | None = None
        self.signout_error: Exception | None = None
        self.disable_error: Exception | None = None
        self.get_calls: list[dict[str, object]] = []
        self.signout_calls: list[dict[str, object]] = []
        self.disable_calls: list[dict[str, object]] = []

    def admin_create_user(self, **kwargs: object) -> dict[str, Any]:
        raise AssertionError(f"unexpected create call: {kwargs}")

    def admin_get_user(self, **kwargs: object) -> dict[str, Any]:
        self.get_calls.append(kwargs)
        if self.get_error is not None:
            raise self.get_error
        assert isinstance(self.user, dict)
        return self.user

    def admin_get_user_auth_factors(self, **kwargs: object) -> dict[str, Any]:
        raise AssertionError(f"unexpected auth factors call: {kwargs}")

    def admin_delete_user(self, **kwargs: object) -> dict[str, Any]:
        raise AssertionError(f"unexpected delete call: {kwargs}")

    def admin_disable_user(self, **kwargs: object) -> dict[str, Any]:
        self.disable_calls.append(kwargs)
        if self.disable_error is not None:
            raise self.disable_error
        return {}

    def admin_user_global_sign_out(self, **kwargs: object) -> dict[str, Any]:
        self.signout_calls.append(kwargs)
        if self.signout_error is not None:
            raise self.signout_error
        return {}


def repository(client: FakeCognitoClient) -> CognitoRepository:
    return CognitoRepository(client, "pool-1")


def test_deactivation_calls_use_only_pool_and_stable_username() -> None:
    client = FakeCognitoClient()
    repo = repository(client)

    repo.admin_user_global_sign_out(user_id=USER_ID)
    repo.admin_disable_user(user_id=USER_ID)

    expected = [{"UserPoolId": "pool-1", "Username": USER_ID}]
    assert client.signout_calls == expected
    assert client.disable_calls == expected


@pytest.mark.parametrize("enabled", [True, False])
def test_deactivation_readback_validates_username_sub_and_enabled(enabled: bool) -> None:
    client = FakeCognitoClient()
    assert isinstance(client.user, dict)
    client.user["Enabled"] = enabled

    state = repository(client).admin_get_deactivation_state(
        user_id=USER_ID,
        expected_cognito_sub=COGNITO_SUB,
    )

    assert state.user_id == USER_ID
    assert state.cognito_sub == COGNITO_SUB
    assert state.enabled is enabled
    assert client.get_calls == [{"UserPoolId": "pool-1", "Username": USER_ID}]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda response: response.update(Username="different"),
        lambda response: response.update(Enabled="false"),
        lambda response: response.update(UserAttributes=[]),
        lambda response: response["UserAttributes"].append({"Name": "sub", "Value": COGNITO_SUB}),
        lambda response: response["UserAttributes"].__setitem__(
            0, {"Name": "sub", "Value": "different-sub"}
        ),
    ],
)
def test_deactivation_readback_rejects_incompatible_identity(mutate: Any) -> None:
    client = FakeCognitoClient()
    assert isinstance(client.user, dict)
    mutate(client.user)

    with pytest.raises(CognitoIdentityInvariantError):
        repository(client).admin_get_deactivation_state(
            user_id=USER_ID,
            expected_cognito_sub=COGNITO_SUB,
        )


@pytest.mark.parametrize(
    ("error", "error_type"),
    [
        (
            client_error("UserNotFoundException", "AdminGetUser"),
            CognitoUserNotFoundError,
        ),
        (
            client_error("InternalErrorException", "AdminGetUser", status=500),
            CognitoResultAmbiguousError,
        ),
        (
            EndpointConnectionError(endpoint_url="https://cognito.invalid"),
            CognitoResultAmbiguousError,
        ),
        (
            client_error("AccessDeniedException", "AdminGetUser"),
            CognitoServiceError,
        ),
    ],
)
def test_deactivation_readback_classifies_sanitized_failures(
    error: Exception,
    error_type: type[Exception],
) -> None:
    client = FakeCognitoClient()
    client.get_error = error

    with pytest.raises(error_type) as captured:
        repository(client).admin_get_deactivation_state(
            user_id=USER_ID,
            expected_cognito_sub=COGNITO_SUB,
        )

    assert "sensitive provider detail" not in str(captured.value)


@pytest.mark.parametrize(
    ("operation", "error", "error_type"),
    [
        (
            "signout",
            EndpointConnectionError(endpoint_url="https://cognito.invalid"),
            CognitoResultAmbiguousError,
        ),
        (
            "signout",
            client_error("AccessDeniedException", "AdminUserGlobalSignOut"),
            CognitoServiceError,
        ),
        (
            "disable",
            client_error("InternalErrorException", "AdminDisableUser", status=500),
            CognitoResultAmbiguousError,
        ),
    ],
)
def test_deactivation_effects_classify_sanitized_failures(
    operation: str,
    error: Exception,
    error_type: type[Exception],
) -> None:
    client = FakeCognitoClient()
    if operation == "signout":
        client.signout_error = error
    else:
        client.disable_error = error

    with pytest.raises(error_type) as captured:
        if operation == "signout":
            repository(client).admin_user_global_sign_out(user_id=USER_ID)
        else:
            repository(client).admin_disable_user(user_id=USER_ID)

    assert "sensitive provider detail" not in str(captured.value)
