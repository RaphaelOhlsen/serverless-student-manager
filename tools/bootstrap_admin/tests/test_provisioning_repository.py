from typing import Any

import pytest
from botocore.session import Session  # type: ignore[import-untyped]
from botocore.validate import validate_parameters  # type: ignore[import-untyped]

from tools.bootstrap_admin.audit import build_user_created_audit_event
from tools.bootstrap_admin.models import (
    build_cognito_projection,
    build_first_admin_bootstrap_marker,
    build_unique_email,
    build_user_profile,
)
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


def _bootstrap_marker() -> dict[str, object]:
    return {
        "PK": "CONTROL#FIRST_ADMIN_BOOTSTRAP",
        "SK": "CONTROL",
        "userId": "user-123",
        "operationId": "operation-123",
        "createdAt": "2026-08-20T12:00:00.000Z",
        "createdBy": "github:raphael",
    }


def _audit_event() -> dict[str, object]:
    return {
        "PK": "RESOURCE#USER#user-123",
        "SK": "TS#2026-08-20T12:00:00.000Z#EVENT#event-123",
        "eventType": "USER_CREATED",
        "expiresAt": 1_779_278_400,
    }


def test_persist_first_admin_with_audit_uses_one_conditional_transaction() -> None:
    client = FakeDynamoDBClient()
    repository = ProvisioningRepository(client)

    repository.persist_first_admin_with_audit(
        users_table_name="users-table",
        audit_table_name="audit-table",
        user_profile=_user_profile(),
        unique_email=_unique_email(),
        cognito_projection=_cognito_projection(),
        bootstrap_marker=_bootstrap_marker(),
        audit_event=_audit_event(),
        client_request_token="literal-client-request-token",
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
                    "TableName": "users-table",
                    "Item": {
                        "PK": {"S": "CONTROL#FIRST_ADMIN_BOOTSTRAP"},
                        "SK": {"S": "CONTROL"},
                        "userId": {"S": "user-123"},
                        "operationId": {"S": "operation-123"},
                        "createdAt": {"S": "2026-08-20T12:00:00.000Z"},
                        "createdBy": {"S": "github:raphael"},
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
                        "SK": {"S": "TS#2026-08-20T12:00:00.000Z#EVENT#event-123"},
                        "eventType": {"S": "USER_CREATED"},
                        "expiresAt": {"N": "1779278400"},
                    },
                    "ConditionExpression": (
                        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                    ),
                }
            },
        ],
        "ClientRequestToken": "literal-client-request-token",
    }
    assert client.put_item_calls == 0


def test_complete_transaction_matches_botocore_service_model_and_has_unique_keys() -> None:
    client = FakeDynamoDBClient()
    repository = ProvisioningRepository(client)
    user_id = "223e4567-e89b-42d3-a456-426614174001"
    cognito_sub = "323e4567-e89b-42d3-a456-426614174002"
    operation_id = "123e4567-e89b-42d3-a456-426614174000"
    occurred_at = "2026-08-20T12:00:00.000Z"

    repository.persist_first_admin_with_audit(
        users_table_name="users-table",
        audit_table_name="audit-table",
        user_profile=build_user_profile(
            user_id=user_id,
            cognito_sub=cognito_sub,
            full_name="Example Admin",
            email="example-admin@example.invalid",
            created_at=occurred_at,
            created_by="github:example@123",
        ),
        unique_email=build_unique_email(
            user_id=user_id,
            email="example-admin@example.invalid",
        ),
        cognito_projection=build_cognito_projection(
            user_id=user_id,
            cognito_sub=cognito_sub,
        ),
        bootstrap_marker=build_first_admin_bootstrap_marker(
            user_id=user_id,
            operation_id=operation_id,
            created_at=occurred_at,
            created_by="github:example@123",
        ),
        audit_event=build_user_created_audit_event(
            user_id=user_id,
            actor_id="github:example@123",
            event_id="423e4567-e89b-42d3-a456-426614174003",
            correlation_id="523e4567-e89b-42d3-a456-426614174004",
            occurred_at=occurred_at,
            expires_at=1_795_009_512,
        ),
        client_request_token=operation_id,
    )

    transaction = client.last_transaction
    assert transaction is not None
    operation_model = Session().get_service_model("dynamodb").operation_model("TransactWriteItems")
    validate_parameters(transaction, operation_model.input_shape)

    transact_items = transaction["TransactItems"]
    assert isinstance(transact_items, list)
    assert len(transact_items) == 5
    keys: set[tuple[str, str, str]] = set()
    for action in transact_items:
        assert isinstance(action, dict)
        put = action["Put"]
        assert isinstance(put, dict)
        item = put["Item"]
        assert isinstance(item, dict)
        table_name = put["TableName"]
        assert isinstance(table_name, str)
        pk = item["PK"]
        sk = item["SK"]
        assert isinstance(pk, dict)
        assert isinstance(sk, dict)
        key = (table_name, pk["S"], sk["S"])
        assert all(isinstance(value, str) for value in key)
        assert key not in keys
        keys.add(key)
        assert put["ConditionExpression"] == (
            "attribute_not_exists(PK) AND attribute_not_exists(SK)"
        )

    assert transaction["ClientRequestToken"] == operation_id
    assert "role" in transact_items[0]["Put"]["Item"]
    assert "GSI3PK" in transact_items[4]["Put"]["Item"]


class DynamoDBFailure(RuntimeError):
    pass


class FailingDynamoDBClient(FakeDynamoDBClient):
    def transact_write_items(self, **kwargs: object) -> dict[str, Any]:
        raise DynamoDBFailure("transaction failed")


def test_persist_first_admin_with_audit_propagates_client_exception() -> None:
    repository = ProvisioningRepository(FailingDynamoDBClient())

    with pytest.raises(DynamoDBFailure, match="transaction failed"):
        repository.persist_first_admin_with_audit(
            users_table_name="users-table",
            audit_table_name="audit-table",
            user_profile=_user_profile(),
            unique_email=_unique_email(),
            cognito_projection=_cognito_projection(),
            bootstrap_marker=_bootstrap_marker(),
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
    assert item is not None
    assert type(item["authVersion"]) is int


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


def test_get_bootstrap_marker_uses_exact_key_and_consistent_read() -> None:
    client = FakeDynamoDBClient()
    client.get_responses = [
        {
            "Item": {
                "PK": {"S": "CONTROL#FIRST_ADMIN_BOOTSTRAP"},
                "SK": {"S": "CONTROL"},
                "userId": {"S": "user-123"},
                "operationId": {"S": "operation-123"},
                "createdAt": {"S": "2026-08-20T12:00:00.000Z"},
                "createdBy": {"S": "github:raphael"},
            }
        }
    ]
    repository = ProvisioningRepository(client)

    item = repository.get_bootstrap_marker(users_table_name="users-table")

    assert client.get_calls == [
        {
            "TableName": "users-table",
            "Key": {
                "PK": {"S": "CONTROL#FIRST_ADMIN_BOOTSTRAP"},
                "SK": {"S": "CONTROL"},
            },
            "ConsistentRead": True,
        }
    ]
    assert item == _bootstrap_marker()


def test_get_bootstrap_marker_returns_none_when_item_is_missing() -> None:
    client = FakeDynamoDBClient()
    client.get_responses = [{}]
    repository = ProvisioningRepository(client)

    item = repository.get_bootstrap_marker(users_table_name="users-table")

    assert item is None


def test_get_audit_event_uses_composed_key_and_consistent_read() -> None:
    client = FakeDynamoDBClient()
    client.get_responses = [
        {
            "Item": {
                "PK": {"S": "RESOURCE#USER#user-123"},
                "SK": {"S": "TS#2026-08-20T12:00:00.000Z#EVENT#event-123"},
                "eventType": {"S": "USER_CREATED"},
                "expiresAt": {"N": "1779278400"},
            }
        }
    ]
    repository = ProvisioningRepository(client)

    item = repository.get_audit_event(
        audit_table_name="audit-table",
        user_id="user-123",
        occurred_at="2026-08-20T12:00:00.000Z",
        event_id="event-123",
    )

    assert client.get_calls == [
        {
            "TableName": "audit-table",
            "Key": {
                "PK": {"S": "RESOURCE#USER#user-123"},
                "SK": {"S": "TS#2026-08-20T12:00:00.000Z#EVENT#event-123"},
            },
            "ConsistentRead": True,
        }
    ]
    assert item == _audit_event()


def test_get_audit_event_returns_none_when_item_is_missing() -> None:
    client = FakeDynamoDBClient()
    client.get_responses = [{}]
    repository = ProvisioningRepository(client)

    item = repository.get_audit_event(
        audit_table_name="audit-table",
        user_id="user-123",
        occurred_at="2026-08-20T12:00:00Z",
        event_id="event-123",
    )

    assert item is None


def test_get_returns_none_when_item_is_missing() -> None:
    client = FakeDynamoDBClient()
    client.get_responses = [{}]
    repository = ProvisioningRepository(client)

    item = repository.get_user_profile(users_table_name="users-table", user_id="missing")

    assert item is None
