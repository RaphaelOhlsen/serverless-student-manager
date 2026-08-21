from typing import Any

import pytest

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
        self.get_calls = 0

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
        self.get_calls += 1
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


def test_bootstrap_cognito_created_writes_sub_with_conditional_update() -> None:
    table = FakeUpdatableDynamoDBTable()
    repository = IdempotencyRepository(table)

    repository.transition_state(
        record_id="NONHTTP#dev#bootstrap-admin#first-admin#operation-123",
        operation="bootstrap-admin",
        current_state="STARTED",
        next_state="COGNITO_CREATED",
        updated_at="2026-08-20T13:50:00.000Z",
        cognito_sub="cognito-sub-123",
    )

    assert table.last_update is not None
    assert table.last_update["Key"] == {
        "id": "NONHTTP#dev#bootstrap-admin#first-admin#operation-123",
    }
    assert table.last_update["ConditionExpression"] == (
        "#state = :current_state AND #operation = :operation"
    )
    assert table.last_update["ExpressionAttributeNames"] == {
        "#state": "state",
        "#operation": "operation",
    }
    assert table.last_update["ExpressionAttributeValues"] == {
        ":current_state": "STARTED",
        ":next_state": "COGNITO_CREATED",
        ":updated_at": "2026-08-20T13:50:00.000Z",
        ":operation": "bootstrap-admin",
        ":cognito_sub": "cognito-sub-123",
    }
    update_expression = table.last_update["UpdateExpression"]
    assert isinstance(update_expression, str)
    assert "#state = :next_state" in update_expression
    assert "updatedAt = :updated_at" in update_expression
    assert "cognitoSub = :cognito_sub" in update_expression
    assert table.get_calls == 0


def test_bootstrap_cognito_created_requires_sub_before_update() -> None:
    table = FakeUpdatableDynamoDBTable()
    repository = IdempotencyRepository(table)

    with pytest.raises(ValueError, match="cognito_sub is required"):
        repository.transition_state(
            record_id="record-123",
            operation="bootstrap-admin",
            current_state="STARTED",
            next_state="COGNITO_CREATED",
            updated_at="2026-08-20T13:50:00.000Z",
        )

    assert table.last_update is None
    assert table.get_calls == 0


def test_later_bootstrap_transition_does_not_rewrite_sub_when_absent() -> None:
    table = FakeUpdatableDynamoDBTable()
    repository = IdempotencyRepository(table)

    repository.transition_state(
        record_id="record-123",
        operation="bootstrap-admin",
        current_state="COGNITO_CREATED",
        next_state="PERSISTENCE_COMPLETED",
        updated_at="2026-08-20T13:55:00.000Z",
    )

    assert table.last_update is not None
    update_expression = table.last_update["UpdateExpression"]
    values = table.last_update["ExpressionAttributeValues"]
    assert isinstance(update_expression, str)
    assert update_expression.startswith("SET ")
    assert "#state = :next_state" in update_expression
    assert "updatedAt = :updated_at" in update_expression
    assert "cognitoSub" not in update_expression
    assert isinstance(values, dict)
    assert ":cognito_sub" not in values
    assert table.get_calls == 0


@pytest.mark.parametrize("next_state", ["COMPLETED", "RECONCILIATION_REQUIRED"])
def test_resume_transition_does_not_require_cognito_sub(next_state: str) -> None:
    table = FakeUpdatableDynamoDBTable()
    repository = IdempotencyRepository(table)

    repository.transition_state(
        record_id="record-123",
        operation="resume-first-admin-invitation",
        current_state="STARTED",
        next_state=next_state,
        updated_at="2026-08-20T14:00:00.000Z",
    )

    assert table.last_update is not None
    assert "cognitoSub" not in table.last_update["UpdateExpression"]


@pytest.mark.parametrize(
    ("operation", "next_state"),
    [
        ("bootstrap-admin", "COMPLETED"),
        ("unknown-operation", "COMPLETED"),
    ],
)
def test_invalid_transition_is_rejected_before_update(
    operation: str,
    next_state: str,
) -> None:
    table = FakeUpdatableDynamoDBTable()
    repository = IdempotencyRepository(table)

    with pytest.raises(ValueError, match="invalid idempotency state transition"):
        repository.transition_state(
            record_id="record-123",
            operation=operation,
            current_state="STARTED",
            next_state=next_state,
            updated_at="2026-08-20T14:00:00.000Z",
        )

    assert table.last_update is None
    assert table.get_calls == 0


def test_optional_sub_is_written_when_explicitly_provided() -> None:
    table = FakeUpdatableDynamoDBTable()
    repository = IdempotencyRepository(table)

    repository.transition_state(
        record_id="record-123",
        operation="bootstrap-admin",
        current_state="COGNITO_CREATED",
        next_state="PERSISTENCE_COMPLETED",
        updated_at="2026-08-20T14:00:00.000Z",
        cognito_sub="reconciled-sub-123",
    )

    assert table.last_update is not None
    assert "cognitoSub = :cognito_sub" in table.last_update["UpdateExpression"]
    assert table.last_update["ExpressionAttributeValues"][":cognito_sub"] == ("reconciled-sub-123")


class UpdateFailure(RuntimeError):
    pass


class FailingUpdatableDynamoDBTable(FakeUpdatableDynamoDBTable):
    def update_item(
        self,
        *,
        Key: dict[str, str],
        UpdateExpression: str,
        ConditionExpression: str,
        ExpressionAttributeNames: dict[str, str],
        ExpressionAttributeValues: dict[str, object],
    ) -> dict[str, Any]:
        raise UpdateFailure("update result is ambiguous")


def test_update_exception_is_propagated_without_read() -> None:
    table = FailingUpdatableDynamoDBTable()
    repository = IdempotencyRepository(table)

    with pytest.raises(UpdateFailure, match="update result is ambiguous"):
        repository.transition_state(
            record_id="record-123",
            operation="resume-first-admin-invitation",
            current_state="STARTED",
            next_state="COMPLETED",
            updated_at="2026-08-20T14:00:00.000Z",
        )

    assert table.get_calls == 0
