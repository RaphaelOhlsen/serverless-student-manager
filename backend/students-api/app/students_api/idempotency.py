import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from aws_lambda_powertools.utilities.idempotency import (
    BasePersistenceLayer,
    IdempotencyConfig,
    idempotent_function,
)
from aws_lambda_powertools.utilities.idempotency.exceptions import (
    IdempotencyAlreadyInProgressError,
    IdempotencyValidationError,
)
from aws_lambda_powertools.utilities.typing import LambdaContext
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from students_api.errors import (
    IdempotencyKeyReusedError,
    OperationInProgressError,
    StudentLifecycleInvariantError,
    StudentLifecycleUnresolvedError,
    StudentUpdateInvariantError,
    StudentUpdateUnresolvedError,
)

_lambda_context: LambdaContext | None = None
_configs: list[IdempotencyConfig] = []
_PUBLIC_STUDENT_RESPONSE_FIELDS = {
    "studentId",
    "registrationNumber",
    "fullName",
    "studentEmail",
    "phone",
    "birthDate",
    "status",
    "version",
    "createdAt",
    "updatedAt",
}


def set_lambda_context(context: LambdaContext) -> None:
    global _lambda_context
    _lambda_context = context
    for config in _configs:
        config.register_lambda_context(context)


class CreateStudentIdempotency:
    def __init__(self, persistence: BasePersistenceLayer) -> None:
        self._config = IdempotencyConfig(
            event_key_jmespath="[environment, actorId, operation, idempotencyKey]",
            payload_validation_jmespath="payload",
            expires_after_seconds=86400,
            hash_function="sha256",
            raise_on_no_idempotency_key=True,
        )
        if _lambda_context is not None:
            self._config.register_lambda_context(_lambda_context)
        _configs.append(self._config)
        self._execute = idempotent_function(
            data_keyword_argument="data",
            persistence_store=persistence,
            config=self._config,
            key_prefix="create-student",
        )(self._invoke)

    def execute(
        self,
        *,
        data: dict[str, Any],
        action: Callable[[], dict[str, object]],
    ) -> dict[str, object]:
        try:
            result = self._execute(data=data, action=action)
        except IdempotencyValidationError:
            raise IdempotencyKeyReusedError from None
        except IdempotencyAlreadyInProgressError:
            raise OperationInProgressError from None
        if not isinstance(result, dict):
            raise RuntimeError("Idempotency returned an invalid response")
        return result

    @staticmethod
    def _invoke(
        *,
        data: dict[str, Any],
        action: Callable[[], dict[str, object]],
    ) -> dict[str, object]:
        del data
        return action()


class IdempotencyClient(Protocol):
    def put_item(self, **kwargs: object) -> dict[str, Any]: ...

    def get_item(self, **kwargs: object) -> dict[str, Any]: ...

    def update_item(self, **kwargs: object) -> dict[str, Any]: ...

    def delete_item(self, **kwargs: object) -> dict[str, Any]: ...


@dataclass(frozen=True)
class UpdateIdempotencyRecord:
    idempotency_id: str
    request_hash: str
    response: dict[str, object] | None = None


class UpdateStudentIdempotency:
    """Acquire and resolve durable update-student idempotency records."""

    def __init__(
        self,
        client: IdempotencyClient,
        table_name: str,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._client = client
        self._table_name = table_name
        self._clock = clock or time.time
        self._serializer = TypeSerializer()
        self._deserializer = TypeDeserializer()

    def acquire(
        self,
        *,
        environment: str,
        actor_id: str,
        idempotency_key: str,
        student_id: str,
        payload: dict[str, str | int],
    ) -> UpdateIdempotencyRecord:
        identity = [environment, actor_id, "update-student", idempotency_key]
        idempotency_id = f"update-student#{self._hash(identity)}"
        request_hash = self._hash(
            {
                "operation": "update-student",
                "studentId": student_id,
                "expectedVersion": payload["expectedVersion"],
                "payload": {
                    key: value for key, value in payload.items() if key != "expectedVersion"
                },
            }
        )
        now = int(self._clock())
        record = UpdateIdempotencyRecord(idempotency_id, request_hash)
        try:
            self._client.put_item(
                TableName=self._table_name,
                Item=self._serialize(
                    {
                        "id": idempotency_id,
                        "status": "INPROGRESS",
                        "expiration": now + 86400,
                        "in_progress_expiration": (now + 60) * 1000,
                        "validation": request_hash,
                    }
                ),
                ConditionExpression=("attribute_not_exists(#id) OR #expiration < :now"),
                ExpressionAttributeNames={
                    "#id": "id",
                    "#expiration": "expiration",
                },
                ExpressionAttributeValues=self._serialize({":now": now}),
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise StudentUpdateUnresolvedError from error
            return self.resolve(record)
        except Exception as error:
            raise StudentUpdateUnresolvedError from error
        return record

    def complete_noop(
        self,
        record: UpdateIdempotencyRecord,
        response: dict[str, object],
    ) -> dict[str, object]:
        for attempt in range(2):
            try:
                self._complete_noop_once(record, response)
            except Exception:
                try:
                    recovered = self.resolve(record)
                except OperationInProgressError:
                    if attempt == 0:
                        continue
                    raise
                if recovered.response is None:
                    raise StudentUpdateUnresolvedError from None
                return recovered.response
            return response
        raise StudentUpdateUnresolvedError  # pragma: no cover - loop always returns or raises

    def _complete_noop_once(
        self,
        record: UpdateIdempotencyRecord,
        response: dict[str, object],
    ) -> None:
        self._client.update_item(
            TableName=self._table_name,
            Key=self._serialize({"id": record.idempotency_id}),
            UpdateExpression="SET #status = :completed, #data = :data",
            ConditionExpression="#status = :pending AND #validation = :hash",
            ExpressionAttributeNames={
                "#status": "status",
                "#data": "data",
                "#validation": "validation",
            },
            ExpressionAttributeValues=self._serialize(
                {
                    ":completed": "COMPLETED",
                    ":pending": "INPROGRESS",
                    ":data": self._canonical_json(response),
                    ":hash": record.request_hash,
                }
            ),
        )

    def resolve(self, record: UpdateIdempotencyRecord) -> UpdateIdempotencyRecord:
        try:
            result = self._client.get_item(
                TableName=self._table_name,
                Key=self._serialize({"id": record.idempotency_id}),
                ConsistentRead=True,
            )
        except Exception as error:
            raise StudentUpdateUnresolvedError from error
        raw = result.get("Item")
        if not isinstance(raw, dict):
            raise StudentUpdateInvariantError
        item = self._deserialize(raw)
        if item.get("id") != record.idempotency_id:
            raise StudentUpdateInvariantError
        if item.get("validation") != record.request_hash:
            raise IdempotencyKeyReusedError
        status = item.get("status")
        if status == "INPROGRESS":
            raise OperationInProgressError
        if status != "COMPLETED":
            raise StudentUpdateInvariantError
        data = item.get("data")
        if not isinstance(data, str):
            raise StudentUpdateInvariantError
        try:
            response = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise StudentUpdateInvariantError from None
        if (
            not isinstance(response, dict)
            or set(response) != _PUBLIC_STUDENT_RESPONSE_FIELDS
            or type(response.get("version")) is not int
            or any(
                not isinstance(response.get(field), str)
                for field in _PUBLIC_STUDENT_RESPONSE_FIELDS - {"version"}
            )
        ):
            raise StudentUpdateInvariantError
        return UpdateIdempotencyRecord(
            record.idempotency_id,
            record.request_hash,
            response,
        )

    def release(self, record: UpdateIdempotencyRecord) -> None:
        try:
            self._client.delete_item(
                TableName=self._table_name,
                Key=self._serialize({"id": record.idempotency_id}),
                ConditionExpression="#status = :pending AND #validation = :hash",
                ExpressionAttributeNames={"#status": "status", "#validation": "validation"},
                ExpressionAttributeValues=self._serialize(
                    {":pending": "INPROGRESS", ":hash": record.request_hash}
                ),
            )
        except Exception as error:
            raise StudentUpdateInvariantError from error

    @classmethod
    def _hash(cls, value: object) -> str:
        return hashlib.sha256(cls._canonical_json(value).encode()).hexdigest()

    @staticmethod
    def _canonical_json(value: object) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def _serialize(self, item: dict[str, object]) -> dict[str, object]:
        return {name: self._serializer.serialize(value) for name, value in item.items()}

    def _deserialize(self, item: dict[str, Any]) -> dict[str, object]:
        return {name: self._deserializer.deserialize(value) for name, value in item.items()}


LifecycleOperation = Literal["deactivate-student", "reactivate-student"]


@dataclass(frozen=True)
class LifecycleIdempotencyRecord:
    operation: LifecycleOperation
    idempotency_id: str
    request_hash: str
    response: dict[str, object] | None = None


class StudentLifecycleIdempotency:
    """Durable idempotency for the two explicit student lifecycle operations."""

    def __init__(
        self,
        client: IdempotencyClient,
        table_name: str,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._client = client
        self._table_name = table_name
        self._clock = clock or time.time
        self._serializer = TypeSerializer()
        self._deserializer = TypeDeserializer()

    def acquire(
        self,
        *,
        operation: LifecycleOperation,
        environment: str,
        actor_id: str,
        idempotency_key: str,
        student_id: str,
        payload: dict[str, str | int],
    ) -> LifecycleIdempotencyRecord:
        identity = [environment, actor_id, operation, idempotency_key]
        idempotency_id = f"{operation}#{self._hash(identity)}"
        request_hash = self._hash(
            {
                "operation": operation,
                "studentId": student_id,
                **payload,
            }
        )
        now = int(self._clock())
        record = LifecycleIdempotencyRecord(operation, idempotency_id, request_hash)
        try:
            self._client.put_item(
                TableName=self._table_name,
                Item=self._serialize(
                    {
                        "id": idempotency_id,
                        "status": "INPROGRESS",
                        "expiration": now + 86400,
                        "in_progress_expiration": (now + 60) * 1000,
                        "validation": request_hash,
                    }
                ),
                ConditionExpression="attribute_not_exists(#id) OR #expiration < :now",
                ExpressionAttributeNames={"#id": "id", "#expiration": "expiration"},
                ExpressionAttributeValues=self._serialize({":now": now}),
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise StudentLifecycleUnresolvedError from error
            return self.resolve(record)
        except Exception as error:
            raise StudentLifecycleUnresolvedError from error
        return record

    def complete_noop(
        self,
        record: LifecycleIdempotencyRecord,
        response: dict[str, object],
    ) -> dict[str, object]:
        self._validate_record_identity(record)
        for attempt in range(2):
            try:
                self._complete_noop_once(record, response)
            except Exception:
                try:
                    recovered = self.resolve(record)
                except OperationInProgressError:
                    if attempt == 0:
                        continue
                    raise
                if recovered.response is None:
                    raise StudentLifecycleUnresolvedError from None
                return recovered.response
            return response
        raise StudentLifecycleUnresolvedError  # pragma: no cover

    def _complete_noop_once(
        self,
        record: LifecycleIdempotencyRecord,
        response: dict[str, object],
    ) -> None:
        self._client.update_item(
            TableName=self._table_name,
            Key=self._serialize({"id": record.idempotency_id}),
            UpdateExpression="SET #status = :completed, #data = :data",
            ConditionExpression="#status = :pending AND #validation = :hash",
            ExpressionAttributeNames={
                "#status": "status",
                "#data": "data",
                "#validation": "validation",
            },
            ExpressionAttributeValues=self._serialize(
                {
                    ":completed": "COMPLETED",
                    ":pending": "INPROGRESS",
                    ":data": self._canonical_json(response),
                    ":hash": record.request_hash,
                }
            ),
        )

    def resolve(self, record: LifecycleIdempotencyRecord) -> LifecycleIdempotencyRecord:
        self._validate_record_identity(record)
        try:
            result = self._client.get_item(
                TableName=self._table_name,
                Key=self._serialize({"id": record.idempotency_id}),
                ConsistentRead=True,
            )
        except Exception as error:
            raise StudentLifecycleUnresolvedError from error
        raw = result.get("Item")
        if not isinstance(raw, dict):
            raise StudentLifecycleInvariantError
        item = self._deserialize(raw)
        if item.get("id") != record.idempotency_id:
            raise StudentLifecycleInvariantError
        if item.get("validation") != record.request_hash:
            raise IdempotencyKeyReusedError
        status = item.get("status")
        if status == "INPROGRESS":
            raise OperationInProgressError
        if status != "COMPLETED":
            raise StudentLifecycleInvariantError
        data = item.get("data")
        if not isinstance(data, str):
            raise StudentLifecycleInvariantError
        try:
            response = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise StudentLifecycleInvariantError from None
        if (
            not isinstance(response, dict)
            or set(response) != _PUBLIC_STUDENT_RESPONSE_FIELDS
            or type(response.get("version")) is not int
            or any(
                not isinstance(response.get(field), str)
                for field in _PUBLIC_STUDENT_RESPONSE_FIELDS - {"version"}
            )
        ):
            raise StudentLifecycleInvariantError
        return LifecycleIdempotencyRecord(
            record.operation,
            record.idempotency_id,
            record.request_hash,
            response,
        )

    def release(self, record: LifecycleIdempotencyRecord) -> None:
        self._validate_record_identity(record)
        try:
            self._client.delete_item(
                TableName=self._table_name,
                Key=self._serialize({"id": record.idempotency_id}),
                ConditionExpression="#status = :pending AND #validation = :hash",
                ExpressionAttributeNames={"#status": "status", "#validation": "validation"},
                ExpressionAttributeValues=self._serialize(
                    {":pending": "INPROGRESS", ":hash": record.request_hash}
                ),
            )
        except Exception as error:
            raise StudentLifecycleInvariantError from error

    @classmethod
    def _hash(cls, value: object) -> str:
        return hashlib.sha256(cls._canonical_json(value).encode()).hexdigest()

    @staticmethod
    def _canonical_json(value: object) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def _serialize(self, item: dict[str, object]) -> dict[str, object]:
        return {name: self._serializer.serialize(value) for name, value in item.items()}

    def _deserialize(self, item: dict[str, Any]) -> dict[str, object]:
        return {name: self._deserializer.deserialize(value) for name, value in item.items()}

    @staticmethod
    def _validate_record_identity(record: LifecycleIdempotencyRecord) -> None:
        if not record.idempotency_id.startswith(f"{record.operation}#"):
            raise StudentLifecycleInvariantError
