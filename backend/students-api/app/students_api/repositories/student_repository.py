from dataclasses import dataclass
from typing import Any, Protocol, cast

from boto3.dynamodb.conditions import Key  # type: ignore[import-untyped]

from students_api.cursor import CursorPosition


class DynamoDBTable(Protocol):
    def get_item(self, *, Key: dict[str, str]) -> dict[str, Any]: ...

    def query(self, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True)
class StudentPage:
    items: list[dict[str, Any]]
    next_position: CursorPosition | None


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

    def list_students(
        self,
        *,
        status: str,
        name_prefix: str | None,
        limit: int,
        position: CursorPosition | None,
    ) -> StudentPage:
        index_name = "gsi-all-name" if status == "ALL" else "gsi-status-name"
        partition_name = "GSI2PK" if status == "ALL" else "GSI1PK"
        sort_name = "GSI2SK" if status == "ALL" else "GSI1SK"
        partition_value = "ALL" if status == "ALL" else f"STATUS#{status}"
        condition = Key(partition_name).eq(partition_value)
        if name_prefix is not None:
            condition &= Key(sort_name).begins_with(f"NAME#{name_prefix}")

        query: dict[str, Any] = {
            "IndexName": index_name,
            "KeyConditionExpression": condition,
            "Limit": limit,
            "ScanIndexForward": True,
        }
        if position is not None:
            query["ExclusiveStartKey"] = self._exclusive_start_key(
                partition_name, sort_name, partition_value, position
            )

        response = self._table.query(**query)
        raw_items = response.get("Items", [])
        if not isinstance(raw_items, list):
            raise RuntimeError("DynamoDB Query returned invalid Items")
        items = [cast(dict[str, Any], item) for item in raw_items if isinstance(item, dict)]
        last_key = response.get("LastEvaluatedKey")
        next_position = self._position_from_last_key(last_key, sort_name)
        return StudentPage(items=items, next_position=next_position)

    @staticmethod
    def _exclusive_start_key(
        partition_name: str,
        sort_name: str,
        partition_value: str,
        position: CursorPosition,
    ) -> dict[str, str]:
        student_key = f"STUDENT#{position.student_id}"
        key = {
            "PK": student_key,
            "SK": "PROFILE",
            partition_name: partition_value,
            sort_name: f"NAME#{position.normalized_name}#{student_key}",
        }
        return key

    @staticmethod
    def _position_from_last_key(value: Any, sort_name: str) -> CursorPosition | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise RuntimeError("DynamoDB Query returned invalid LastEvaluatedKey")
        student_key = value.get("PK")
        sort_key = value.get(sort_name)
        if not isinstance(student_key, str) or not student_key.startswith("STUDENT#"):
            raise RuntimeError("DynamoDB Query returned invalid student key")
        suffix = f"#{student_key}"
        if (
            not isinstance(sort_key, str)
            or not sort_key.startswith("NAME#")
            or not sort_key.endswith(suffix)
        ):
            raise RuntimeError("DynamoDB Query returned invalid index key")
        normalized_name = sort_key[len("NAME#") : -len(suffix)]
        return CursorPosition(
            student_id=student_key[len("STUDENT#") :],
            normalized_name=normalized_name,
        )
