from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4, uuid5

from students_api.errors import (
    StudentEmailAlreadyExistsError,
    StudentNotFoundError,
    StudentUpdateInvariantError,
    StudentUpdateUnresolvedError,
    StudentVersionConflictError,
)
from students_api.idempotency import UpdateIdempotencyRecord
from students_api.repositories.update_transaction import (
    MUTABLE_FIELDS,
    PUBLIC_FIELDS,
    UpdateTransactionContext,
)
from students_api.validation import UpdateStudentInput


class UpdateRepositoryProtocol(Protocol):
    def get_profile_consistent(self, student_id: str) -> dict[str, object] | None: ...

    def update_student(
        self,
        *,
        current: dict[str, Any],
        target: dict[str, Any],
        expected_version: int,
        context: UpdateTransactionContext,
        idempotency_table_name: str,
    ) -> None: ...


class UpdateAuthorizationProtocol(Protocol):
    def authorize_update_student(self, cognito_sub: str | None) -> str: ...


class UpdateIdempotencyProtocol(Protocol):
    def acquire(
        self,
        *,
        environment: str,
        actor_id: str,
        idempotency_key: str,
        student_id: str,
        payload: dict[str, str | int],
    ) -> UpdateIdempotencyRecord: ...

    def complete_noop(
        self,
        record: UpdateIdempotencyRecord,
        response: dict[str, object],
    ) -> dict[str, object]: ...

    def resolve(self, record: UpdateIdempotencyRecord) -> UpdateIdempotencyRecord: ...

    def release(self, record: UpdateIdempotencyRecord) -> None: ...


class UpdateStudentService:
    def __init__(
        self,
        repository: UpdateRepositoryProtocol,
        authorization: UpdateAuthorizationProtocol,
        idempotency: UpdateIdempotencyProtocol,
        *,
        environment: str,
        audit_retention_days: int,
        idempotency_table_name: str,
        clock: Callable[[], datetime] | None = None,
        identifier_factory: Callable[[], UUID] | None = None,
    ) -> None:
        self._repository = repository
        self._authorization = authorization
        self._idempotency = idempotency
        self._environment = environment
        self._audit_retention_days = audit_retention_days
        self._idempotency_table_name = idempotency_table_name
        self._clock = clock or (lambda: datetime.now(UTC))
        self._identifier_factory = identifier_factory or uuid4

    def update_student(
        self,
        *,
        cognito_sub: str | None,
        idempotency_key: str,
        request_id: str | None,
        student_id: str,
        patch: UpdateStudentInput,
    ) -> dict[str, object]:
        actor_id = self._authorization.authorize_update_student(cognito_sub)
        record = self._idempotency.acquire(
            environment=self._environment,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            student_id=student_id,
            payload=patch.payload(),
        )
        if record.response is not None:
            return record.response

        try:
            current = self._repository.get_profile_consistent(student_id)
        except Exception:
            self._idempotency.release(record)
            raise
        if current is None:
            self._release_and_raise(record, StudentNotFoundError())
        assert current is not None
        try:
            self._validate_current(current, student_id)
        except StudentUpdateInvariantError:
            self._idempotency.release(record)
            raise
        if current["version"] != patch.expected_version:
            self._release_and_raise(record, StudentVersionConflictError())

        target, changed_fields = self._target_and_changes(current, patch)
        response = self._public_response(current)
        if not changed_fields:
            return self._idempotency.complete_noop(record, response)

        now = self._clock().astimezone(UTC)
        occurred_at = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        response.update(target)
        response.update(version=patch.expected_version + 1, updatedAt=occurred_at)
        context = UpdateTransactionContext(
            actor_id=actor_id,
            correlation_id=request_id or str(self._identifier_factory()),
            event_id=str(self._identifier_factory()),
            occurred_at=occurred_at,
            audit_expires_at=int((now + timedelta(days=self._audit_retention_days)).timestamp()),
            idempotency_id=record.idempotency_id,
            request_hash=record.request_hash,
            client_request_token=self._client_request_token(record),
        )
        try:
            self._repository.update_student(
                current=current,
                target=target,
                expected_version=patch.expected_version,
                context=context,
                idempotency_table_name=self._idempotency_table_name,
            )
        except StudentUpdateUnresolvedError as error:
            recovered = self._idempotency.resolve(record)
            if recovered.response is None:
                raise StudentUpdateInvariantError from error
            return recovered.response
        except (StudentVersionConflictError, StudentEmailAlreadyExistsError) as error:
            self._release_and_raise(record, error)
        return response

    def _release_and_raise(
        self,
        record: UpdateIdempotencyRecord,
        error: Exception,
    ) -> None:
        self._idempotency.release(record)
        raise error

    @staticmethod
    def _validate_current(current: dict[str, object], student_id: str) -> None:
        required = set(PUBLIC_FIELDS) | {"createdBy", "updatedBy"}
        if (
            not required <= set(current)
            or current.get("studentId") != student_id
            or type(current.get("version")) is not int
            or any(
                not isinstance(current.get(field), str)
                for field in set(PUBLIC_FIELDS) - {"version"}
            )
            or not isinstance(current.get("createdBy"), str)
            or not isinstance(current.get("updatedBy"), str)
        ):
            raise StudentUpdateInvariantError

    @staticmethod
    def _target_and_changes(
        current: dict[str, object], patch: UpdateStudentInput
    ) -> tuple[dict[str, Any], list[str]]:
        provided = patch.payload()
        target = {field: current[field] for field in MUTABLE_FIELDS}
        for field in MUTABLE_FIELDS:
            value = provided.get(field)
            if value is not None:
                target[field] = value
        changed = [field for field in MUTABLE_FIELDS if target[field] != current[field]]
        return target, changed

    @staticmethod
    def _public_response(current: dict[str, object]) -> dict[str, object]:
        return {field: current[field] for field in PUBLIC_FIELDS}

    @staticmethod
    def _client_request_token(record: UpdateIdempotencyRecord) -> str:
        # The scoped durable id and request hash contain no PII and distinguish actors/requests.
        return str(uuid5(UUID(int=0), f"{record.idempotency_id}#{record.request_hash}"))
