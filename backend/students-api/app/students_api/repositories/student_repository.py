from dataclasses import dataclass
from typing import Any, Protocol, cast

from aws_lambda_powertools import Logger
from boto3.dynamodb.conditions import Key  # type: ignore[import-untyped]
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from students_api.config import SERVICE_NAME
from students_api.cursor import CursorPosition
from students_api.repositories.dynamodb_values import normalize_dynamodb_value

logger = Logger(service=SERVICE_NAME)


class DynamoDBTable(Protocol):
    def get_item(self, **kwargs: Any) -> dict[str, Any]: ...

    def query(self, **kwargs: Any) -> dict[str, Any]: ...


class DynamoDBClient(Protocol):
    def get_item(self, **kwargs: object) -> dict[str, Any]: ...

    def transact_write_items(self, **kwargs: object) -> dict[str, Any]: ...


@dataclass(frozen=True)
class StudentPage:
    items: list[dict[str, Any]]
    next_position: CursorPosition | None


class StudentRepository:
    def __init__(
        self,
        table: DynamoDBTable,
        *,
        client: DynamoDBClient | None = None,
        students_table_name: str | None = None,
        audit_table_name: str | None = None,
    ) -> None:
        self._table = table
        self._client = client
        self._students_table_name = students_table_name
        self._audit_table_name = audit_table_name
        self._serializer = TypeSerializer()
        self._deserializer = TypeDeserializer()

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

    def create_student(
        self,
        *,
        profile: dict[str, object],
        registration: dict[str, object],
        email: dict[str, object],
        audit: dict[str, object],
        client_request_token: str,
    ) -> None:
        client, students_table, audit_table = self._write_dependencies()
        items = [
            self._put(students_table, profile),
            self._put(students_table, registration),
            self._put(students_table, email),
            self._put(audit_table, audit),
        ]
        try:
            client.transact_write_items(
                TransactItems=items,
                ClientRequestToken=client_request_token,
            )
        except Exception as error:
            details: dict[str, object] = {
                "stage": "student_creation_transaction",
                "exceptionClass": type(error).__name__,
                "operation": "TransactWriteItems",
                "correlationId": str(audit["correlationId"]),
            }
            if isinstance(error, ClientError):
                details["awsErrorCode"] = str(error.response.get("Error", {}).get("Code", ""))
                details["awsRequestId"] = str(
                    error.response.get("ResponseMetadata", {}).get("RequestId", "")
                )
                reasons = error.response.get("CancellationReasons")
                if isinstance(reasons, list):
                    details["cancellationReasonCodes"] = [
                        {"index": index, "code": str(reason.get("Code", ""))}
                        for index, reason in enumerate(reasons)
                        if isinstance(reason, dict)
                    ]
            logger.error("Student creation transaction failed", extra=details)
            raise

    def get_registration_reservation(self, registration_number: str) -> dict[str, object] | None:
        return self._get_consistent(
            self._required_students_table(),
            {"PK": f"UNIQUE#REGISTRATION#{registration_number}", "SK": "UNIQUE"},
        )

    def get_email_reservation(self, normalized_email: str) -> dict[str, object] | None:
        return self._get_consistent(
            self._required_students_table(),
            {"PK": f"UNIQUE#EMAIL#{normalized_email}", "SK": "UNIQUE"},
        )

    def get_profile_consistent(self, student_id: str) -> dict[str, object] | None:
        return self._get_consistent(
            self._required_students_table(),
            {"PK": f"STUDENT#{student_id}", "SK": "PROFILE"},
        )

    def get_audit_event(self, partition_key: str, sort_key: str) -> dict[str, object] | None:
        _, _, audit_table = self._write_dependencies()
        return self._get_consistent(audit_table, {"PK": partition_key, "SK": sort_key})

    def _get_consistent(
        self,
        table_name: str,
        key: dict[str, object],
    ) -> dict[str, object] | None:
        client, _, _ = self._write_dependencies()
        response = client.get_item(
            TableName=table_name,
            Key=self._serialize_item(key),
            ConsistentRead=True,
        )
        item = response.get("Item")
        if not isinstance(item, dict):
            return None
        return {
            name: normalize_dynamodb_value(self._deserializer.deserialize(value))
            for name, value in item.items()
        }

    def _write_dependencies(self) -> tuple[DynamoDBClient, str, str]:
        if (
            self._client is None
            or self._students_table_name is None
            or self._audit_table_name is None
        ):
            raise RuntimeError("Student write dependencies are required")
        return self._client, self._students_table_name, self._audit_table_name

    def _required_students_table(self) -> str:
        if self._students_table_name is None:
            raise RuntimeError("Students table name is required")
        return self._students_table_name

    def _put(self, table_name: str, item: dict[str, object]) -> dict[str, object]:
        return {
            "Put": {
                "TableName": table_name,
                "Item": self._serialize_item(item),
                "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
            }
        }

    def _serialize_item(self, item: dict[str, object]) -> dict[str, object]:
        return {name: self._serializer.serialize(value) for name, value in item.items()}

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
