from typing import Any

import pytest

from tools.verify_first_admin_email.audit_repository import AuditRepository


class FakeDynamoDBClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.get_response: dict[str, Any] = {}
        self.put_error: Exception | None = None
        self.get_error: Exception | None = None

    def put_item(self, **kwargs: object) -> dict[str, Any]:
        self.calls.append(("put_item", dict(kwargs)))
        if self.put_error is not None:
            raise self.put_error
        return {}

    def get_item(self, **kwargs: object) -> dict[str, Any]:
        self.calls.append(("get_item", dict(kwargs)))
        if self.get_error is not None:
            raise self.get_error
        return self.get_response

    def update_item(self, **kwargs: object) -> dict[str, Any]:
        raise AssertionError(f"unexpected UpdateItem call: {kwargs}")


def _event() -> dict[str, object]:
    return {
        "PK": "RESOURCE#USER#user-123",
        "SK": "TS#2026-08-31T14:25:40.123Z#EVENT#event-123",
        "eventId": "event-123",
        "eventType": "FIRST_ADMIN_EMAIL_VERIFICATION",
        "expiresAt": 1_793_400_340,
    }


def test_put_audit_event_is_single_conditional_append_only_write() -> None:
    client = FakeDynamoDBClient()
    repository = AuditRepository(client)

    repository.put_event(audit_table_name="audit-table", event=_event())

    assert client.calls == [
        (
            "put_item",
            {
                "TableName": "audit-table",
                "Item": {
                    "PK": {"S": "RESOURCE#USER#user-123"},
                    "SK": {"S": "TS#2026-08-31T14:25:40.123Z#EVENT#event-123"},
                    "eventId": {"S": "event-123"},
                    "eventType": {"S": "FIRST_ADMIN_EMAIL_VERIFICATION"},
                    "expiresAt": {"N": "1793400340"},
                },
                "ConditionExpression": ("attribute_not_exists(PK) AND attribute_not_exists(SK)"),
            },
        )
    ]


def test_get_audit_event_uses_exact_key_and_consistent_read() -> None:
    client = FakeDynamoDBClient()
    client.get_response = {
        "Item": {
            "PK": {"S": "RESOURCE#USER#user-123"},
            "SK": {"S": "TS#2026-08-31T14:25:40.123Z#EVENT#event-123"},
            "eventId": {"S": "event-123"},
            "eventType": {"S": "FIRST_ADMIN_EMAIL_VERIFICATION"},
            "expiresAt": {"N": "1793400340"},
        }
    }
    repository = AuditRepository(client)

    result = repository.get_event(
        audit_table_name="audit-table",
        user_id="user-123",
        occurred_at="2026-08-31T14:25:40.123Z",
        event_id="event-123",
    )

    assert client.calls == [
        (
            "get_item",
            {
                "TableName": "audit-table",
                "Key": {
                    "PK": {"S": "RESOURCE#USER#user-123"},
                    "SK": {"S": "TS#2026-08-31T14:25:40.123Z#EVENT#event-123"},
                },
                "ConsistentRead": True,
            },
        )
    ]
    assert result == _event()


def test_get_audit_event_returns_none_when_missing() -> None:
    repository = AuditRepository(FakeDynamoDBClient())

    assert (
        repository.get_event(
            audit_table_name="audit-table",
            user_id="user-123",
            occurred_at="2026-08-31T14:25:40.123Z",
            event_id="event-123",
        )
        is None
    )


@pytest.mark.parametrize("operation", ["put", "get"])
def test_repository_propagates_errors_unchanged(operation: str) -> None:
    client = FakeDynamoDBClient()
    error = RuntimeError(f"{operation} failed")
    repository = AuditRepository(client)

    if operation == "put":
        client.put_error = error
    else:
        client.get_error = error

    with pytest.raises(RuntimeError) as raised:
        if operation == "put":
            repository.put_event(audit_table_name="audit-table", event=_event())
        else:
            repository.get_event(
                audit_table_name="audit-table",
                user_id="user-123",
                occurred_at="2026-08-31T14:25:40.123Z",
                event_id="event-123",
            )

    assert raised.value is error
