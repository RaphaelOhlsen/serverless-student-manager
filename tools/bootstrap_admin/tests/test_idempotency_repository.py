from typing import Any

from tools.bootstrap_admin.idempotency_repository import IdempotencyRepository


class FakeDynamoDBTable:
    def __init__(self) -> None:
        self.last_put: dict[str, Any] | None = None

    def put_item(
        self,
        *,
        Item: dict[str, object],
        ConditionExpression: str,
    ) -> dict[str, Any]:
        self.last_put = {
            "Item": Item,
            "ConditionExpression": ConditionExpression,
        }
        return {}

    def get_item(
        self,
        *,
        Key: dict[str, str],
        ConsistentRead: bool,
    ) -> dict[str, Any]:
        return {}

    def update_item(
        self,
        *,
        Key: dict[str, str],
        UpdateExpression: str,
        ConditionExpression: str,
        ExpressionAttributeNames: dict[str, str],
        ExpressionAttributeValues: dict[str, object],
    ) -> dict[str, Any]:
        return {}


def test_create_started_record_uses_conditional_put() -> None:
    table = FakeDynamoDBTable()
    repository = IdempotencyRepository(table)

    record: dict[str, object] = {
        "id": "NONHTTP#dev#bootstrap-admin#first-admin#operation-123",
        "state": "STARTED",
        "payloadHash": "hash-123",
    }

    repository.create_started(record)

    assert table.last_put == {
        "Item": record,
        "ConditionExpression": "attribute_not_exists(id)",
    }


class FakeReadableDynamoDBTable:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.last_get: dict[str, Any] | None = None

    def put_item(
        self,
        *,
        Item: dict[str, object],
        ConditionExpression: str,
    ) -> dict[str, Any]:
        return {}

    def get_item(
        self,
        *,
        Key: dict[str, str],
        ConsistentRead: bool,
    ) -> dict[str, Any]:
        self.last_get = {
            "Key": Key,
            "ConsistentRead": ConsistentRead,
        }
        return self.response

    def update_item(
        self,
        *,
        Key: dict[str, str],
        UpdateExpression: str,
        ConditionExpression: str,
        ExpressionAttributeNames: dict[str, str],
        ExpressionAttributeValues: dict[str, object],
    ) -> dict[str, Any]:
        return {}


def test_get_existing_record_uses_strongly_consistent_read() -> None:
    expected_record: dict[str, object] = {
        "id": "NONHTTP#dev#bootstrap-admin#first-admin#operation-123",
        "state": "STARTED",
    }
    table = FakeReadableDynamoDBTable({"Item": expected_record})
    repository = IdempotencyRepository(table)

    record = repository.get("NONHTTP#dev#bootstrap-admin#first-admin#operation-123")

    assert table.last_get == {
        "Key": {
            "id": "NONHTTP#dev#bootstrap-admin#first-admin#operation-123",
        },
        "ConsistentRead": True,
    }
    assert record == expected_record


class FakeUpdatableDynamoDBTable:
    def __init__(self) -> None:
        self.last_update: dict[str, Any] | None = None

    def put_item(
        self,
        *,
        Item: dict[str, object],
        ConditionExpression: str,
    ) -> dict[str, Any]:
        return {}

    def get_item(
        self,
        *,
        Key: dict[str, str],
        ConsistentRead: bool,
    ) -> dict[str, Any]:
        return {}

    def update_item(
        self,
        *,
        Key: dict[str, str],
        UpdateExpression: str,
        ConditionExpression: str,
        ExpressionAttributeNames: dict[str, str],
        ExpressionAttributeValues: dict[str, object],
    ) -> dict[str, Any]:
        self.last_update = {
            "Key": Key,
            "UpdateExpression": UpdateExpression,
            "ConditionExpression": ConditionExpression,
            "ExpressionAttributeNames": ExpressionAttributeNames,
            "ExpressionAttributeValues": ExpressionAttributeValues,
        }
        return {}


def test_transition_state_uses_conditional_update() -> None:
    table = FakeUpdatableDynamoDBTable()
    repository = IdempotencyRepository(table)

    repository.transition_state(
        record_id="NONHTTP#dev#bootstrap-admin#first-admin#operation-123",
        current_state="STARTED",
        next_state="COGNITO_CREATED",
        updated_at="2026-08-19T20:05:00Z",
        cognito_sub="cognito-sub-123",
    )

    assert table.last_update == {
        "Key": {
            "id": "NONHTTP#dev#bootstrap-admin#first-admin#operation-123",
        },
        "UpdateExpression": (
            "SET #state = :next_state, updatedAt = :updated_at, cognitoSub = :cognito_sub"
        ),
        "ConditionExpression": "#state = :current_state",
        "ExpressionAttributeNames": {
            "#state": "state",
        },
        "ExpressionAttributeValues": {
            ":current_state": "STARTED",
            ":next_state": "COGNITO_CREATED",
            ":updated_at": "2026-08-19T20:05:00Z",
            ":cognito_sub": "cognito-sub-123",
        },
    }
