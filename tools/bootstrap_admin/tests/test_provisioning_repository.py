from typing import Any

import pytest

from tools.bootstrap_admin.provisioning_repository import ProvisioningRepository


class FakeDynamoDBClient:
    def __init__(self) -> None:
        self.last_transaction: dict[str, object] | None = None
        self.get_calls: list[dict[str, object]] = []
        self.put_item_calls = 0
        self.get_responses: list[dict[str, Any]] = []

    def transact_write_items(self, **kwargs: object) -> dict[str, Any]:
        self.last_transaction = dict(kwargs)
        return {}

    def get_item(self, **kwargs: object) -> dict[str, Any]:
        self.get_calls.append(dict(kwargs))
        return self.get_responses.pop(0)

    def put_item(self, **kwargs: object) -> dict[str, Any]:
        self.put_item_calls += 1
        raise AssertionError(f"unexpected PutItem call: {kwargs}")


def _user_profile() -> dict[str, object]:
    return {
        "PK": "USER#user-123",
        "SK": "PROFILE",
        "userId": "user-123",
        "authVersion": 1,
    }


def _unique_email() -> dict[str, object]:
    return {
        "PK": "UNIQUE#EMAIL#admin@example.com",
        "SK": "UNIQUE",
        "userId": "user-123",
    }


def _cognito_projection() -> dict[str, object]:
    return {
        "PK": "COGNITO#cognito-sub-123",
        "SK": "AUTHORIZATION",
        "userId": "user-123",
        "authVersion": 1,
    }


def _audit_event() -> dict[str, object]:
    return {
        "PK": "RESOURCE#USER#user-123",
        "SK": "TS#2026-08-20T12:00:00Z#EVENT#event-123",
        "eventType": "USER_CREATED",
        "expiresAt": 1_779_278_400,
    }


def test_persist_user_with_audit_uses_one_conditional_transaction() -> None:
    client = FakeDynamoDBClient()
    repository = ProvisioningRepository(client)

    repository.persist_user_with_audit(
        users_table_name="users-table",
        audit_table_name="audit-table",
        user_profile=_user_profile(),
        unique_email=_unique_email(),
        cognito_projection=_cognito_projection(),
        audit_event=_audit_event(),
        client_request_token="operation-token-123",
    )

    assert client.last_transaction == {
        "TransactItems": [
            {
                "Put": {
                    "TableName": "users-table",
                    "Item": {
                        "PK": {"S": "USER#user-123"},
                        "SK": {"S": "PROFILE"},
                        "userId": {"S": "user-123"},
                        "authVersion": {"N": "1"},
                    },
                    "ConditionExpression": (
                        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                    ),
                }
            },
            {
                "Put": {
                    "TableName": "users-table",
                    "Item": {
                        "PK": {"S": "UNIQUE#EMAIL#admin@example.com"},
                        "SK": {"S": "UNIQUE"},
                        "userId": {"S": "user-123"},
                    },
                    "ConditionExpression": (
                        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                    ),
                }
            },
            {
                "Put": {
                    "TableName": "users-table",
                    "Item": {
                        "PK": {"S": "COGNITO#cognito-sub-123"},
                        "SK": {"S": "AUTHORIZATION"},
                        "userId": {"S": "user-123"},
                        "authVersion": {"N": "1"},
                    },
                    "ConditionExpression": (
                        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                    ),
                }
            },
            {
                "Put": {
                    "TableName": "audit-table",
                    "Item": {
                        "PK": {"S": "RESOURCE#USER#user-123"},
                        "SK": {"S": "TS#2026-08-20T12:00:00Z#EVENT#event-123"},
                        "eventType": {"S": "USER_CREATED"},
                        "expiresAt": {"N": "1779278400"},
                    },
                    "ConditionExpression": (
                        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                    ),
                }
            },
        ],
        "ClientRequestToken": "operation-token-123",
    }
    assert client.put_item_calls == 0


class DynamoDBFailure(RuntimeError):
    pass


class FailingDynamoDBClient(FakeDynamoDBClient):
    def transact_write_items(self, **kwargs: object) -> dict[str, Any]:
        raise DynamoDBFailure("transaction failed")


def test_persist_user_with_audit_propagates_client_exception() -> None:
    repository = ProvisioningRepository(FailingDynamoDBClient())

    with pytest.raises(DynamoDBFailure, match="transaction failed"):
        repository.persist_user_with_audit(
            users_table_name="users-table",
            audit_table_name="audit-table",
            user_profile=_user_profile(),
            unique_email=_unique_email(),
            cognito_projection=_cognito_projection(),
            audit_event=_audit_event(),
            client_request_token="operation-token-123",
        )


def test_get_user_profile_uses_exact_key_and_consistent_read() -> None:
    client = FakeDynamoDBClient()
    client.get_responses = [
        {
            "Item": {
                "PK": {"S": "USER#user-123"},
                "SK": {"S": "PROFILE"},
                "userId": {"S": "user-123"},
                "authVersion": {"N": "1"},
            }
        }
    ]
    repository = ProvisioningRepository(client)

    item = repository.get_user_profile(users_table_name="users-table", user_id="user-123")

    assert client.get_calls == [
        {
            "TableName": "users-table",
            "Key": {
                "PK": {"S": "USER#user-123"},
                "SK": {"S": "PROFILE"},
            },
            "ConsistentRead": True,
        }
    ]
    assert item == _user_profile()


def test_get_unique_email_uses_exact_key_and_consistent_read() -> None:
    client = FakeDynamoDBClient()
    client.get_responses = [{"Item": {key: {"S": value} for key, value in _unique_email().items()}}]
    repository = ProvisioningRepository(client)

    item = repository.get_unique_email(
        users_table_name="users-table",
        normalized_email="admin@example.com",
    )

    assert client.get_calls == [
        {
            "TableName": "users-table",
            "Key": {
                "PK": {"S": "UNIQUE#EMAIL#admin@example.com"},
                "SK": {"S": "UNIQUE"},
            },
            "ConsistentRead": True,
        }
    ]
    assert item == _unique_email()


def test_get_cognito_projection_uses_exact_key_and_consistent_read() -> None:
    client = FakeDynamoDBClient()
    client.get_responses = [
        {
            "Item": {
                "PK": {"S": "COGNITO#cognito-sub-123"},
                "SK": {"S": "AUTHORIZATION"},
                "userId": {"S": "user-123"},
                "authVersion": {"N": "1"},
            }
        }
    ]
    repository = ProvisioningRepository(client)

    item = repository.get_cognito_projection(
        users_table_name="users-table",
        cognito_sub="cognito-sub-123",
    )

    assert client.get_calls == [
        {
            "TableName": "users-table",
            "Key": {
                "PK": {"S": "COGNITO#cognito-sub-123"},
                "SK": {"S": "AUTHORIZATION"},
            },
            "ConsistentRead": True,
        }
    ]
    assert item == _cognito_projection()


def test_get_returns_none_when_item_is_missing() -> None:
    client = FakeDynamoDBClient()
    client.get_responses = [{}]
    repository = ProvisioningRepository(client)

    item = repository.get_user_profile(users_table_name="users-table", user_id="missing")

    assert item is None
