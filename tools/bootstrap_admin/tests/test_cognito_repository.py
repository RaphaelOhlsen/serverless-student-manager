from typing import Any

import pytest
from botocore.exceptions import ClientError

from tools.bootstrap_admin.cognito_repository import (
    CognitoCreateResultError,
    CognitoIdentityValidationError,
    CognitoRepository,
    ReconciledCognitoIdentity,
)


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
            },
            {
                "Name": "email_verified",
                "Value": "true",
            },
        ],
        "MessageAction": "SUPPRESS",
        "ForceAliasCreation": False,
    }
    assert cognito_sub == "cognito-sub-123"


class FakeCreateResponseCognitoClient(FakeCognitoClient):
    def __init__(self, response: dict[str, Any]) -> None:
        super().__init__()
        self.response = response

    def admin_create_user(self, **kwargs: object) -> dict[str, Any]:
        self.last_create = dict(kwargs)
        return self.response


@pytest.mark.parametrize(
    ("response", "error_match"),
    [
        ({}, "response is missing User"),
        ({"User": {}}, "response is missing Attributes"),
        ({"User": {"Attributes": []}}, "response is missing sub"),
    ],
)
def test_create_suppressed_user_rejects_result_without_usable_sub(
    response: dict[str, Any],
    error_match: str,
) -> None:
    repository = CognitoRepository(FakeCreateResponseCognitoClient(response))

    with pytest.raises(CognitoCreateResultError, match=error_match):
        repository.create_suppressed_user(
            user_pool_id="us-east-1_example",
            user_id="user-123",
            email="admin@example.com",
        )


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
        CognitoIdentityValidationError,
        match="existing Cognito user email does not match expected email",
    ):
        repository.get_existing_user_sub(
            user_pool_id="us-east-1_example",
            user_id="user-123",
            expected_email="admin@example.com",
        )


def test_get_existing_user_fails_without_user_attributes() -> None:
    repository = CognitoRepository(FakeGetUserCognitoClient({"Username": "user-123"}))

    with pytest.raises(
        CognitoIdentityValidationError,
        match="AdminGetUser response is missing UserAttributes",
    ):
        repository.get_existing_user_sub(
            user_pool_id="us-east-1_example",
            user_id="user-123",
            expected_email="admin@example.com",
        )


def test_get_existing_user_fails_with_empty_response() -> None:
    repository = CognitoRepository(FakeGetUserCognitoClient({}))

    with pytest.raises(
        CognitoIdentityValidationError,
        match="AdminGetUser response is missing UserAttributes",
    ):
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

    with pytest.raises(CognitoIdentityValidationError, match="missing sub"):
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

    with pytest.raises(CognitoIdentityValidationError, match="missing email"):
        repository.get_existing_user_sub(
            user_pool_id="us-east-1_example",
            user_id="user-123",
            expected_email="admin@example.com",
        )


def test_get_verified_user_returns_sub_for_adr_025_identity() -> None:
    client = FakeGetUserCognitoClient(
        {
            "Username": "user-123",
            "UserAttributes": [
                {"Name": "sub", "Value": "cognito-sub-123"},
                {"Name": "email", "Value": "admin@example.com"},
                {"Name": "email_verified", "Value": "true"},
            ],
        }
    )
    repository = CognitoRepository(client)

    result = repository.get_verified_user_sub(
        user_pool_id="us-east-1_example",
        user_id="user-123",
        expected_email="admin@example.com",
        expected_sub="cognito-sub-123",
    )

    assert result == "cognito-sub-123"


def test_get_verified_user_returns_sub_when_expected_sub_is_not_yet_known() -> None:
    client = FakeGetUserCognitoClient(
        {
            "Username": "user-123",
            "UserAttributes": [
                {"Name": "sub", "Value": "cognito-sub-123"},
                {"Name": "email", "Value": "admin@example.com"},
                {"Name": "email_verified", "Value": "true"},
            ],
        }
    )
    repository = CognitoRepository(client)

    result = repository.get_verified_user_sub(
        user_pool_id="us-east-1_example",
        user_id="user-123",
        expected_email="admin@example.com",
    )

    assert result == "cognito-sub-123"


@pytest.mark.parametrize(
    "email_verified",
    [None, "false", "TRUE"],
)
def test_get_verified_user_rejects_unverified_email(
    email_verified: str | None,
) -> None:
    attributes = [
        {"Name": "sub", "Value": "cognito-sub-123"},
        {"Name": "email", "Value": "admin@example.com"},
    ]

    if email_verified is not None:
        attributes.append({"Name": "email_verified", "Value": email_verified})

    client = FakeGetUserCognitoClient(
        {
            "Username": "user-123",
            "UserAttributes": attributes,
        }
    )
    repository = CognitoRepository(client)

    with pytest.raises(
        CognitoIdentityValidationError,
        match="email is not verified",
    ):
        repository.get_verified_user_sub(
            user_pool_id="us-east-1_example",
            user_id="user-123",
            expected_email="admin@example.com",
            expected_sub="cognito-sub-123",
        )


@pytest.mark.parametrize(
    ("mutation", "error_match"),
    [
        (
            {"Username": "other-user"},
            "username does not match expected username",
        ),
        (
            {
                "UserAttributes": [
                    {"Name": "sub", "Value": "other-sub"},
                    {"Name": "email", "Value": "admin@example.com"},
                    {"Name": "email_verified", "Value": "true"},
                ]
            },
            "sub does not match expected sub",
        ),
        (
            {
                "UserAttributes": [
                    {"Name": "sub", "Value": "cognito-sub-123"},
                    {"Name": "email", "Value": "other@example.com"},
                    {"Name": "email_verified", "Value": "true"},
                ]
            },
            "email does not match expected email",
        ),
    ],
)
def test_get_verified_user_rejects_incompatible_identity(
    mutation: dict[str, object],
    error_match: str,
) -> None:
    response: dict[str, object] = {
        "Username": "user-123",
        "UserAttributes": [
            {"Name": "sub", "Value": "cognito-sub-123"},
            {"Name": "email", "Value": "admin@example.com"},
            {"Name": "email_verified", "Value": "true"},
        ],
    }
    response.update(mutation)

    repository = CognitoRepository(FakeGetUserCognitoClient(response))

    with pytest.raises(
        CognitoIdentityValidationError,
        match=error_match,
    ):
        repository.get_verified_user_sub(
            user_pool_id="us-east-1_example",
            user_id="user-123",
            expected_email="admin@example.com",
            expected_sub="cognito-sub-123",
        )


@pytest.mark.parametrize(
    ("email_verified", "expected_verified"),
    [
        ("true", True),
        ("false", False),
        (None, False),
    ],
)
def test_get_reconciled_user_identity_distinguishes_verification_state(
    email_verified: str | None,
    expected_verified: bool,
) -> None:
    attributes = [
        {"Name": "sub", "Value": "cognito-sub-123"},
        {"Name": "email", "Value": " Admin@Example.COM "},
    ]
    if email_verified is not None:
        attributes.append({"Name": "email_verified", "Value": email_verified})
    client = FakeGetUserCognitoClient(
        {
            "Username": "user-123",
            "UserAttributes": attributes,
        }
    )
    repository = CognitoRepository(client)

    result = repository.get_reconciled_user_identity(
        user_pool_id="us-east-1_example",
        user_id="user-123",
        expected_email="admin@example.com",
        expected_sub="cognito-sub-123",
    )

    assert client.last_get == {
        "UserPoolId": "us-east-1_example",
        "Username": "user-123",
    }
    assert result == ReconciledCognitoIdentity(
        cognito_sub="cognito-sub-123",
        verified=expected_verified,
    )


@pytest.mark.parametrize(
    ("response", "error_match"),
    [
        (
            {
                "Username": "other-user",
                "UserAttributes": [],
            },
            "username does not match expected username",
        ),
        (
            {"Username": "user-123"},
            "missing UserAttributes",
        ),
        (
            {
                "Username": "user-123",
                "UserAttributes": [
                    {"Name": "email", "Value": "admin@example.com"},
                ],
            },
            "missing sub",
        ),
        (
            {
                "Username": "user-123",
                "UserAttributes": [
                    {"Name": "sub", "Value": "other-sub"},
                    {"Name": "email", "Value": "admin@example.com"},
                ],
            },
            "sub does not match expected sub",
        ),
        (
            {
                "Username": "user-123",
                "UserAttributes": [
                    {"Name": "sub", "Value": "cognito-sub-123"},
                ],
            },
            "missing email",
        ),
        (
            {
                "Username": "user-123",
                "UserAttributes": [
                    {"Name": "sub", "Value": "cognito-sub-123"},
                    {"Name": "email", "Value": "other@example.com"},
                ],
            },
            "email does not match expected email",
        ),
    ],
)
def test_get_reconciled_user_identity_rejects_incompatible_identity(
    response: dict[str, Any],
    error_match: str,
) -> None:
    repository = CognitoRepository(FakeGetUserCognitoClient(response))

    with pytest.raises(CognitoIdentityValidationError, match=error_match):
        repository.get_reconciled_user_identity(
            user_pool_id="us-east-1_example",
            user_id="user-123",
            expected_email="admin@example.com",
            expected_sub="cognito-sub-123",
        )


@pytest.mark.parametrize("email_verified", ["TRUE", "False", "1", "", True, 1])
def test_get_reconciled_user_identity_rejects_unexpected_verified_value(
    email_verified: object,
) -> None:
    repository = CognitoRepository(
        FakeGetUserCognitoClient(
            {
                "Username": "user-123",
                "UserAttributes": [
                    {"Name": "sub", "Value": "cognito-sub-123"},
                    {"Name": "email", "Value": "admin@example.com"},
                    {"Name": "email_verified", "Value": email_verified},
                ],
            }
        )
    )

    with pytest.raises(
        CognitoIdentityValidationError,
        match="email_verified value is incompatible",
    ):
        repository.get_reconciled_user_identity(
            user_pool_id="us-east-1_example",
            user_id="user-123",
            expected_email="admin@example.com",
            expected_sub="cognito-sub-123",
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


class FakeUpdateUserAttributesCognitoClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.error = error

    def admin_update_user_attributes(self, **kwargs: object) -> dict[str, Any]:
        self.calls.append(("admin_update_user_attributes", dict(kwargs)))
        if self.error is not None:
            raise self.error
        return {}


def test_set_email_verified_uses_only_authorized_cognito_mutation() -> None:
    client = FakeUpdateUserAttributesCognitoClient()
    repository = CognitoRepository(client)

    repository.set_email_verified(
        user_pool_id="us-east-1_example",
        user_id="00000000-0000-4000-8000-000000000123",
    )

    assert client.calls == [
        (
            "admin_update_user_attributes",
            {
                "UserPoolId": "us-east-1_example",
                "Username": "00000000-0000-4000-8000-000000000123",
                "UserAttributes": [
                    {
                        "Name": "email_verified",
                        "Value": "true",
                    }
                ],
            },
        )
    ]
    assert all(attribute["Name"] != "email" for attribute in client.calls[0][1]["UserAttributes"])


def test_set_email_verified_propagates_client_error_unchanged() -> None:
    error = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
        "AdminUpdateUserAttributes",
    )
    repository = CognitoRepository(FakeUpdateUserAttributesCognitoClient(error))

    with pytest.raises(ClientError) as raised:
        repository.set_email_verified(
            user_pool_id="us-east-1_example",
            user_id="00000000-0000-4000-8000-000000000123",
        )

    assert raised.value is error


def test_set_email_verified_propagates_transport_error_unchanged() -> None:
    error = RuntimeError("transport failed")
    repository = CognitoRepository(FakeUpdateUserAttributesCognitoClient(error))

    with pytest.raises(RuntimeError) as raised:
        repository.set_email_verified(
            user_pool_id="us-east-1_example",
            user_id="00000000-0000-4000-8000-000000000123",
        )

    assert raised.value is error
