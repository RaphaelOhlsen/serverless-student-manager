from typing import Any, Protocol


class IdempotencyTable(Protocol):
    def put_item(self, **kwargs: object) -> dict[str, Any]: ...

    def get_item(self, **kwargs: object) -> dict[str, Any]: ...

    def update_item(self, **kwargs: object) -> dict[str, Any]: ...


class IdempotencyRepository:
    def __init__(self, table: IdempotencyTable) -> None:
        self._table = table

    def start(self, record: dict[str, object]) -> None:
        self._table.put_item(
            Item=record,
            ConditionExpression="attribute_not_exists(id)",
        )

    def get(self, record_id: str) -> dict[str, object] | None:
        response = self._table.get_item(Key={"id": record_id}, ConsistentRead=True)
        item = response.get("Item")
        return item if isinstance(item, dict) else None

    def complete(
        self,
        *,
        record_id: str,
        response: dict[str, object],
        updated_at: str,
    ) -> None:
        self._table.update_item(
            Key={"id": record_id},
            UpdateExpression=(
                "SET #state = :completed, #response = :response, updatedAt = :updated_at"
            ),
            ConditionExpression="#state = :started",
            ExpressionAttributeNames={"#state": "state", "#response": "response"},
            ExpressionAttributeValues={
                ":started": "STARTED",
                ":completed": "COMPLETED",
                ":response": response,
                ":updated_at": updated_at,
            },
        )
