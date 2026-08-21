from typing import Any, Protocol

from boto3.dynamodb.types import (  # type: ignore[import-untyped]
    TypeDeserializer,
    TypeSerializer,
)


class DynamoDBClient(Protocol):
    def transact_write_items(self, **kwargs: object) -> dict[str, Any]: ...

    def get_item(self, **kwargs: object) -> dict[str, Any]: ...


_CONDITION_ITEM_DOES_NOT_EXIST = "attribute_not_exists(PK) AND attribute_not_exists(SK)"


class ProvisioningRepository:
    def __init__(self, client: DynamoDBClient) -> None:
        self._client = client
        self._serializer = TypeSerializer()
        self._deserializer = TypeDeserializer()

    def persist_first_admin_with_audit(
        self,
        *,
        users_table_name: str,
        audit_table_name: str,
        user_profile: dict[str, object],
        unique_email: dict[str, object],
        cognito_projection: dict[str, object],
        bootstrap_marker: dict[str, object],
        audit_event: dict[str, object],
        client_request_token: str,
    ) -> None:
        self._client.transact_write_items(
            TransactItems=[
                self._build_put(users_table_name, user_profile),
                self._build_put(users_table_name, unique_email),
                self._build_put(users_table_name, cognito_projection),
                self._build_put(users_table_name, bootstrap_marker),
                self._build_put(audit_table_name, audit_event),
            ],
            ClientRequestToken=client_request_token,
        )

    def get_user_profile(
        self,
        *,
        users_table_name: str,
        user_id: str,
    ) -> dict[str, object] | None:
        return self._get_item(
            table_name=users_table_name,
            partition_key=f"USER#{user_id}",
            sort_key="PROFILE",
        )

    def get_unique_email(
        self,
        *,
        users_table_name: str,
        normalized_email: str,
    ) -> dict[str, object] | None:
        return self._get_item(
            table_name=users_table_name,
            partition_key=f"UNIQUE#EMAIL#{normalized_email}",
            sort_key="UNIQUE",
        )

    def get_cognito_projection(
        self,
        *,
        users_table_name: str,
        cognito_sub: str,
    ) -> dict[str, object] | None:
        return self._get_item(
            table_name=users_table_name,
            partition_key=f"COGNITO#{cognito_sub}",
            sort_key="AUTHORIZATION",
        )

    def get_bootstrap_marker(
        self,
        *,
        users_table_name: str,
    ) -> dict[str, object] | None:
        return self._get_item(
            table_name=users_table_name,
            partition_key="CONTROL#FIRST_ADMIN_BOOTSTRAP",
            sort_key="CONTROL",
        )

    def get_audit_event(
        self,
        *,
        audit_table_name: str,
        user_id: str,
        occurred_at: str,
        event_id: str,
    ) -> dict[str, object] | None:
        return self._get_item(
            table_name=audit_table_name,
            partition_key=f"RESOURCE#USER#{user_id}",
            sort_key=f"TS#{occurred_at}#EVENT#{event_id}",
        )

    def _build_put(self, table_name: str, item: dict[str, object]) -> dict[str, object]:
        return {
            "Put": {
                "TableName": table_name,
                "Item": self._serialize_item(item),
                "ConditionExpression": _CONDITION_ITEM_DOES_NOT_EXIST,
            }
        }

    def _serialize_item(self, item: dict[str, object]) -> dict[str, object]:
        return {name: self._serializer.serialize(value) for name, value in item.items()}

    def _get_item(
        self,
        *,
        table_name: str,
        partition_key: str,
        sort_key: str,
    ) -> dict[str, object] | None:
        response = self._client.get_item(
            TableName=table_name,
            Key=self._serialize_item(
                {
                    "PK": partition_key,
                    "SK": sort_key,
                }
            ),
            ConsistentRead=True,
        )

        item = response.get("Item")

        if not isinstance(item, dict):
            return None

        return {name: self._deserializer.deserialize(value) for name, value in item.items()}
