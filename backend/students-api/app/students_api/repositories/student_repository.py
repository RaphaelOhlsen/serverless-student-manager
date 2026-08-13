from typing import Any, Protocol, cast


class DynamoDBTable(Protocol):
    def get_item(self, *, Key: dict[str, str]) -> dict[str, Any]: ...


class StudentRepository:
    def __init__(self, table: DynamoDBTable) -> None:
        self._table = table

    def get_by_id(self, student_id: str) -> dict[str, Any] | None:
        response = self._table.get_item(
            Key={
                "PK": f"STUDENT#{student_id}",
                "SK": "PROFILE",
            }
        )

        item = response.get("Item")

        if not isinstance(item, dict):
            return None

        return cast(dict[str, Any], item)
