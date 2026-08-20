from typing import Any

import pytest

from tools.bootstrap_admin.cognito_repository import CognitoRepository


class FakeCognitoClient:
    def __init__(self) -> None:
        self.last_create: dict[str, object] | None = None
        self.last_delete: dict[str, object] | None = None
        self.last_disable: dict[str, object] | None = None

    def admin_create_user(self, **kwargs: object) -> dict[str, Any]:
        self.last_create = dict(kwargs)

        return {
            "User": {
                "Username": "user-123",
                "Attributes": [
                    {
                        "Name": "sub",
                        "Value": "cognito-sub-123",
                    },
                    {
                        "Name": "email",
                        "Value": "admin@example.com",
                    },
                ],
            }
        }

    def admin_get_user(self, **kwargs: object) -> dict[str, Any]:
        raise AssertionError(f"unexpected AdminGetUser call: {kwargs}")

    def admin_delete_user(self, **kwargs: object) -> dict[str, Any]:
        self.last_delete = dict(kwargs)
        return {}

    def admin_disable_user(self, **kwargs: object) -> dict[str, Any]:
        self.last_disable = dict(kwargs)
        return {}


def test_create_suppressed_user_uses_controlled_cognito_flow() -> None:
    client = FakeCognitoClient()
    repository = CognitoRepository(client)

    cognito_sub = repository.create_suppressed_user(
        user_pool_id="us-east-1_example",
        user_id="user-123",
        email="admin@example.com",
    )

    assert client.last_create == {
        "UserPoolId": "us-east-1_example",
        "Username": "user-123",
        "UserAttributes": [
            {
                "Name": "email",
                "Value": "admin@example.com",
            }
        ],
        "MessageAction": "SUPPRESS",
        "ForceAliasCreation": False,
    }
    assert cognito_sub == "cognito-sub-123"


class FakeGetUserCognitoClient(FakeCognitoClient):
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        super().__init__()
        self.last_get: dict[str, object] | None = None
        self.response = (
            response
            if response is not None
            else {
                "Username": "user-123",
                "UserAttributes": [
                    {
                        "Name": "sub",
                        "Value": "cognito-sub-123",
                    },
                    {
                        "Name": "email",
                        "Value": "admin@example.com",
                    },
                ],
            }
        )

    def admin_get_user(self, **kwargs: object) -> dict[str, Any]:
        self.last_get = dict(kwargs)
        return self.response


def test_get_existing_user_returns_sub_when_email_matches() -> None:
    client = FakeGetUserCognitoClient()
    repository = CognitoRepository(client)

    cognito_sub = repository.get_existing_user_sub(
        user_pool_id="us-east-1_example",
        user_id="user-123",
        expected_email="admin@example.com",
    )

    assert client.last_get == {
        "UserPoolId": "us-east-1_example",
        "Username": "user-123",
    }
    assert cognito_sub == "cognito-sub-123"


def test_get_existing_user_rejects_incompatible_email() -> None:
    client = FakeGetUserCognitoClient(
        {
            "UserAttributes": [
                {"Name": "sub", "Value": "cognito-sub-123"},
                {"Name": "email", "Value": "other@example.com"},
            ]
        }
    )
    repository = CognitoRepository(client)

    with pytest.raises(
        RuntimeError,
        match="existing Cognito user email does not match expected email",
    ):
        repository.get_existing_user_sub(
            user_pool_id="us-east-1_example",
            user_id="user-123",
            expected_email="admin@example.com",
        )


def test_get_existing_user_fails_without_user_attributes() -> None:
    repository = CognitoRepository(FakeGetUserCognitoClient({"Username": "user-123"}))

    with pytest.raises(RuntimeError, match="AdminGetUser response is missing UserAttributes"):
        repository.get_existing_user_sub(
            user_pool_id="us-east-1_example",
            user_id="user-123",
            expected_email="admin@example.com",
        )


def test_get_existing_user_fails_with_empty_response() -> None:
    repository = CognitoRepository(FakeGetUserCognitoClient({}))

    with pytest.raises(RuntimeError, match="AdminGetUser response is missing UserAttributes"):
        repository.get_existing_user_sub(
            user_pool_id="us-east-1_example",
            user_id="user-123",
            expected_email="admin@example.com",
        )


def test_get_existing_user_fails_without_sub() -> None:
    client = FakeGetUserCognitoClient(
        {"UserAttributes": [{"Name": "email", "Value": "admin@example.com"}]}
    )
    repository = CognitoRepository(client)

    with pytest.raises(RuntimeError, match="AdminGetUser response is missing sub"):
        repository.get_existing_user_sub(
            user_pool_id="us-east-1_example",
            user_id="user-123",
            expected_email="admin@example.com",
        )


def test_get_existing_user_fails_without_email() -> None:
    client = FakeGetUserCognitoClient(
        {"UserAttributes": [{"Name": "sub", "Value": "cognito-sub-123"}]}
    )
    repository = CognitoRepository(client)

    with pytest.raises(RuntimeError, match="AdminGetUser response is missing email"):
        repository.get_existing_user_sub(
            user_pool_id="us-east-1_example",
            user_id="user-123",
            expected_email="admin@example.com",
        )


def test_delete_user_sends_exact_cognito_arguments() -> None:
    client = FakeCognitoClient()
    repository = CognitoRepository(client)

    repository.delete_user(user_pool_id="us-east-1_example", user_id="user-123")

    assert client.last_delete == {
        "UserPoolId": "us-east-1_example",
        "Username": "user-123",
    }


def test_disable_user_sends_exact_cognito_arguments() -> None:
    client = FakeCognitoClient()
    repository = CognitoRepository(client)

    repository.disable_user(user_pool_id="us-east-1_example", user_id="user-123")

    assert client.last_disable == {
        "UserPoolId": "us-east-1_example",
        "Username": "user-123",
    }


def test_resend_invitation_uses_only_required_cognito_arguments() -> None:
    client = FakeCognitoClient()
    repository = CognitoRepository(client)

    repository.resend_invitation(user_pool_id="us-east-1_example", user_id="user-123")

    assert client.last_create == {
        "UserPoolId": "us-east-1_example",
        "Username": "user-123",
        "MessageAction": "RESEND",
    }
