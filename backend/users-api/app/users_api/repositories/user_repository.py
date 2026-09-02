from typing import Any, Protocol

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer  # type: ignore[import-untyped]


class DynamoDBClient(Protocol):
    def get_item(self, **kwargs: object) -> dict[str, Any]: ...

    def transact_write_items(self, **kwargs: object) -> dict[str, Any]: ...


class UserRepository:
    def __init__(self, client: DynamoDBClient, users_table: str, audit_table: str) -> None:
        self._client = client
        self._users_table = users_table
        self._audit_table = audit_table
        self._serializer = TypeSerializer()
        self._deserializer = TypeDeserializer()

    def get_authorization(self, cognito_sub: str) -> dict[str, object] | None:
        return self._get_user_item(f"COGNITO#{cognito_sub}", "AUTHORIZATION")

    def get_profile(self, user_id: str) -> dict[str, object] | None:
        return self._get_user_item(f"USER#{user_id}", "PROFILE")

    def activate(
        self,
        *,
        user_id: str,
        cognito_sub: str,
        role: str,
        auth_version: int,
        occurred_at: str,
        event_id: str,
        correlation_id: str,
        expires_at: int,
        client_request_token: str,
    ) -> None:
        names = {"#status": "status", "#role": "role"}
        profile_values = self._serialize_values(
            {
                ":invited": "INVITED",
                ":active": "ACTIVE",
                ":user_id": user_id,
                ":sub": cognito_sub,
                ":role": role,
                ":auth_version": auth_version,
                ":occurred_at": occurred_at,
            }
        )
        items: list[dict[str, object]] = [
            {
                "Update": {
                    "TableName": self._users_table,
                    "Key": self._serialize_item({"PK": f"USER#{user_id}", "SK": "PROFILE"}),
                    "UpdateExpression": (
                        "SET #status = :active, updatedAt = :occurred_at, updatedBy = :user_id"
                    ),
                    "ConditionExpression": (
                        "attribute_exists(PK) AND attribute_exists(SK) "
                        "AND #status = :invited AND #role = :role "
                        "AND authVersion = :auth_version AND cognitoSub = :sub "
                        "AND userId = :user_id"
                    ),
                    "ExpressionAttributeNames": names,
                    "ExpressionAttributeValues": profile_values,
                }
            },
            {
                "Update": {
                    "TableName": self._users_table,
                    "Key": self._serialize_item(
                        {"PK": f"COGNITO#{cognito_sub}", "SK": "AUTHORIZATION"}
                    ),
                    "UpdateExpression": "SET #status = :active",
                    "ConditionExpression": (
                        "attribute_exists(PK) AND attribute_exists(SK) "
                        "AND #status = :invited AND #role = :role "
                        "AND authVersion = :auth_version AND userId = :user_id"
                    ),
                    "ExpressionAttributeNames": names,
                    "ExpressionAttributeValues": self._serialize_values(
                        {
                            ":invited": "INVITED",
                            ":active": "ACTIVE",
                            ":user_id": user_id,
                            ":role": role,
                            ":auth_version": auth_version,
                        }
                    ),
                }
            },
        ]

        if role == "ADMIN":
            items.append(
                {
                    "Update": {
                        "TableName": self._users_table,
                        "Key": self._serialize_item(
                            {"PK": "CONTROL#ACTIVE_ADMIN_COUNT", "SK": "CONTROL"}
                        ),
                        "UpdateExpression": "ADD activeAdminCount :one",
                        "ConditionExpression": (
                            "attribute_not_exists(activeAdminCount) "
                            "OR (attribute_type(activeAdminCount, :number_type) "
                            "AND activeAdminCount >= :zero)"
                        ),
                        "ExpressionAttributeValues": self._serialize_values(
                            {":one": 1, ":zero": 0, ":number_type": "N"}
                        ),
                    }
                }
            )

        audit_event = self._build_audit_event(
            user_id=user_id,
            event_id=event_id,
            correlation_id=correlation_id,
            occurred_at=occurred_at,
            expires_at=expires_at,
        )
        items.append(
            {
                "Put": {
                    "TableName": self._audit_table,
                    "Item": self._serialize_item(audit_event),
                    "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                }
            }
        )
        self._client.transact_write_items(
            TransactItems=items,
            ClientRequestToken=client_request_token,
        )

    def _get_user_item(self, partition_key: str, sort_key: str) -> dict[str, object] | None:
        response = self._client.get_item(
            TableName=self._users_table,
            Key=self._serialize_item({"PK": partition_key, "SK": sort_key}),
            ConsistentRead=True,
        )
        item = response.get("Item")
        if not isinstance(item, dict):
            return None
        return {name: self._deserializer.deserialize(value) for name, value in item.items()}

    def _serialize_item(self, item: dict[str, object]) -> dict[str, object]:
        return {name: self._serializer.serialize(value) for name, value in item.items()}

    def _serialize_values(self, values: dict[str, object]) -> dict[str, object]:
        return self._serialize_item(values)

    @staticmethod
    def _build_audit_event(
        *,
        user_id: str,
        event_id: str,
        correlation_id: str,
        occurred_at: str,
        expires_at: int,
    ) -> dict[str, object]:
        sort_key = f"TS#{occurred_at}#EVENT#{event_id}"
        return {
            "PK": f"RESOURCE#USER#{user_id}",
            "SK": sort_key,
            "eventId": event_id,
            "eventType": "USER_ACTIVATED",
            "resourceType": "USER",
            "resourceId": user_id,
            "actorId": user_id,
            "occurredAt": occurred_at,
            "result": "SUCCESS",
            "correlationId": correlation_id,
            "changes": {"status": {"from": "INVITED", "to": "ACTIVE"}},
            "GSI1PK": f"ACTOR#{user_id}",
            "GSI1SK": sort_key,
            "GSI2PK": f"CORRELATION#{correlation_id}",
            "GSI2SK": sort_key,
            "GSI3PK": f"PERIOD#{occurred_at[:7]}",
            "GSI3SK": sort_key,
            "expiresAt": expires_at,
        }
