from typing import Any, Protocol

from boto3.dynamodb.types import (  # type: ignore[import-untyped]
    TypeDeserializer,
    TypeSerializer,
)

from tools.bootstrap_admin.dynamodb_values import normalize_dynamodb_value

_CONDITION_ITEM_DOES_NOT_EXIST = "attribute_not_exists(PK) AND attribute_not_exists(SK)"


class DynamoDBClient(Protocol):
    def put_item(self, **kwargs: object) -> dict[str, Any]: ...

    def get_item(self, **kwargs: object) -> dict[str, Any]: ...


class AuditRepository:
    def __init__(self, client: DynamoDBClient) -> None:
        self._client = client
        self._serializer = TypeSerializer()
        self._deserializer = TypeDeserializer()

    def put_event(
        self,
        *,
        audit_table_name: str,
        event: dict[str, object],
    ) -> None:
        self._client.put_item(
            TableName=audit_table_name,
            Item=self._serialize_item(event),
            ConditionExpression=_CONDITION_ITEM_DOES_NOT_EXIST,
        )

    def get_event(
        self,
        *,
        audit_table_name: str,
        user_id: str,
        occurred_at: str,
        event_id: str,
    ) -> dict[str, object] | None:
        response = self._client.get_item(
            TableName=audit_table_name,
            Key=self._serialize_item(
                {
                    "PK": f"RESOURCE#USER#{user_id}",
                    "SK": f"TS#{occurred_at}#EVENT#{event_id}",
                }
            ),
            ConsistentRead=True,
        )
        item = response.get("Item")
        if not isinstance(item, dict):
            return None
        return {
            name: normalize_dynamodb_value(self._deserializer.deserialize(value))
            for name, value in item.items()
        }

    def _serialize_item(self, item: dict[str, object]) -> dict[str, object]:
        return {name: self._serializer.serialize(value) for name, value in item.items()}
