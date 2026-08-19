from typing import Any, Protocol

from tools.bootstrap_admin.idempotency import is_valid_state_transition


class DynamoDBTable(Protocol):
    def put_item(
        self,
        *,
        Item: dict[str, object],
        ConditionExpression: str,
    ) -> dict[str, Any]: ...

    def get_item(
        self,
        *,
        Key: dict[str, str],
        ConsistentRead: bool,
    ) -> dict[str, Any]: ...

    def update_item(
        self,
        *,
        Key: dict[str, str],
        UpdateExpression: str,
        ConditionExpression: str,
        ExpressionAttributeNames: dict[str, str],
        ExpressionAttributeValues: dict[str, object],
    ) -> dict[str, Any]: ...


class IdempotencyRepository:
    def __init__(self, table: DynamoDBTable) -> None:
        self._table = table

    def create_started(self, record: dict[str, object]) -> None:
        self._table.put_item(
            Item=record,
            ConditionExpression="attribute_not_exists(id)",
        )

    def get(self, record_id: str) -> dict[str, object] | None:
        response = self._table.get_item(
            Key={"id": record_id},
            ConsistentRead=True,
        )

        item = response.get("Item")

        if not isinstance(item, dict):
            return None

        return item

    def transition_state(
        self,
        *,
        record_id: str,
        current_state: str,
        next_state: str,
        updated_at: str,
        cognito_sub: str,
    ) -> None:
        if not is_valid_state_transition(current_state, next_state):
            raise ValueError(
                f"invalid idempotency state transition: {current_state} -> {next_state}"
            )

        self._table.update_item(
            Key={"id": record_id},
            UpdateExpression=(
                "SET #state = :next_state, updatedAt = :updated_at, cognitoSub = :cognito_sub"
            ),
            ConditionExpression="#state = :current_state",
            ExpressionAttributeNames={
                "#state": "state",
            },
            ExpressionAttributeValues={
                ":current_state": current_state,
                ":next_state": next_state,
                ":updated_at": updated_at,
                ":cognito_sub": cognito_sub,
            },
        )
