from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import NoReturn, Protocol
from uuid import UUID, uuid4, uuid5

from students_api.errors import (
    StudentLifecycleConditionError,
    StudentLifecycleInvariantError,
    StudentLifecycleUnresolvedError,
    StudentNotFoundError,
    StudentVersionConflictError,
)
from students_api.idempotency import (
    LifecycleIdempotencyRecord,
    LifecycleOperation,
)
from students_api.repositories.lifecycle_transaction import (
    LifecycleAuditEvent,
    LifecycleIdempotencyCompletion,
    LifecycleTransition,
)
from students_api.repositories.update_transaction import PUBLIC_FIELDS
from students_api.validation import DeactivateStudentInput, ReactivateStudentInput


class LifecycleRepositoryProtocol(Protocol):
    def get_profile_consistent(self, student_id: str) -> dict[str, object] | None: ...

    def transition_student_lifecycle(
        self,
        *,
        transition: LifecycleTransition,
        idempotency_table_name: str,
    ) -> None: ...


class LifecycleAuthorizationProtocol(Protocol):
    def authorize_student_lifecycle(self, cognito_sub: str | None) -> str: ...


class LifecycleIdempotencyProtocol(Protocol):
    def acquire(
        self,
        *,
        operation: LifecycleOperation,
        environment: str,
        actor_id: str,
        idempotency_key: str,
        student_id: str,
        payload: dict[str, str | int],
    ) -> LifecycleIdempotencyRecord: ...

    def complete_noop(
        self,
        record: LifecycleIdempotencyRecord,
        response: dict[str, object],
    ) -> dict[str, object]: ...

    def resolve(self, record: LifecycleIdempotencyRecord) -> LifecycleIdempotencyRecord: ...

    def release(self, record: LifecycleIdempotencyRecord) -> None: ...


class StudentLifecycleService:
    def __init__(
        self,
        repository: LifecycleRepositoryProtocol,
        authorization: LifecycleAuthorizationProtocol,
        idempotency: LifecycleIdempotencyProtocol,
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

    def deactivate_student(
        self,
        *,
        cognito_sub: str | None,
        idempotency_key: str,
        request_id: str | None,
        student_id: str,
        request: DeactivateStudentInput,
    ) -> dict[str, object]:
        return self._transition(
            cognito_sub=cognito_sub,
            idempotency_key=idempotency_key,
            request_id=request_id,
            student_id=student_id,
            operation="deactivate-student",
            expected_version=request.expected_version,
            target_status="INACTIVE",
            payload=request.payload(),
            reason=request.reason,
        )

    def reactivate_student(
        self,
        *,
        cognito_sub: str | None,
        idempotency_key: str,
        request_id: str | None,
        student_id: str,
        request: ReactivateStudentInput,
    ) -> dict[str, object]:
        return self._transition(
            cognito_sub=cognito_sub,
            idempotency_key=idempotency_key,
            request_id=request_id,
            student_id=student_id,
            operation="reactivate-student",
            expected_version=request.expected_version,
            target_status="ACTIVE",
            payload=request.payload(),
            reason=None,
        )

    def _transition(
        self,
        *,
        cognito_sub: str | None,
        idempotency_key: str,
        request_id: str | None,
        student_id: str,
        operation: LifecycleOperation,
        expected_version: int,
        target_status: str,
        payload: Mapping[str, str | int],
        reason: str | None,
    ) -> dict[str, object]:
        actor_id = self._authorization.authorize_student_lifecycle(cognito_sub)
        record = self._idempotency.acquire(
            operation=operation,
            environment=self._environment,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            student_id=student_id,
            payload=dict(payload),
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
        except StudentLifecycleInvariantError as error:
            self._release_and_raise(record, error)
        if current["version"] != expected_version:
            self._release_and_raise(record, StudentVersionConflictError())

        response = self._public_response(current)
        if current["status"] == target_status:
            return self._idempotency.complete_noop(record, response)
        source_status = "ACTIVE" if target_status == "INACTIVE" else "INACTIVE"
        if current["status"] != source_status:
            self._release_and_raise(record, StudentLifecycleInvariantError())

        now = self._clock().astimezone(UTC)
        occurred_at = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        response.update(
            status=target_status,
            version=expected_version + 1,
            updatedAt=occurred_at,
        )
        transition = LifecycleTransition(
            student_id=student_id,
            expected_version=expected_version,
            source_status=source_status,
            target_status=target_status,
            public_response=response,
            audit_event=LifecycleAuditEvent(
                actor_id=actor_id,
                correlation_id=request_id or str(self._identifier_factory()),
                event_id=str(self._identifier_factory()),
                occurred_at=occurred_at,
                audit_expires_at=int(
                    (now + timedelta(days=self._audit_retention_days)).timestamp()
                ),
                reason=reason,
            ),
            idempotency=LifecycleIdempotencyCompletion(
                idempotency_id=record.idempotency_id,
                request_hash=record.request_hash,
                client_request_token=self._client_request_token(record),
            ),
        )
        try:
            self._repository.transition_student_lifecycle(
                transition=transition,
                idempotency_table_name=self._idempotency_table_name,
            )
        except StudentLifecycleConditionError:
            self._classify_profile_condition(record, student_id, expected_version)
        except StudentLifecycleInvariantError as error:
            self._release_and_raise(record, error)
        except StudentLifecycleUnresolvedError as error:
            recovered = self._idempotency.resolve(record)
            if recovered.response is None:
                raise StudentLifecycleInvariantError from error
            return recovered.response
        return response

    def _classify_profile_condition(
        self,
        record: LifecycleIdempotencyRecord,
        student_id: str,
        expected_version: int,
    ) -> NoReturn:
        try:
            current = self._repository.get_profile_consistent(student_id)
        except Exception:
            self._release_and_raise(record, StudentLifecycleInvariantError())
        if current is None:
            self._release_and_raise(record, StudentLifecycleInvariantError())
        assert current is not None
        try:
            self._validate_current(current, student_id)
        except StudentLifecycleInvariantError as error:
            self._release_and_raise(record, error)
        if current["version"] != expected_version:
            self._release_and_raise(record, StudentVersionConflictError())
        self._release_and_raise(record, StudentLifecycleInvariantError())

    def _release_and_raise(
        self,
        record: LifecycleIdempotencyRecord,
        error: Exception,
    ) -> NoReturn:
        self._idempotency.release(record)
        raise error

    @staticmethod
    def _validate_current(current: dict[str, object], student_id: str) -> None:
        required = set(PUBLIC_FIELDS) | {"createdBy", "updatedBy"}
        if (
            not required <= set(current)
            or current.get("studentId") != student_id
            or type(current.get("version")) is not int
            or current.get("status") not in {"ACTIVE", "INACTIVE"}
            or any(
                not isinstance(current.get(field), str)
                for field in set(PUBLIC_FIELDS) - {"version"}
            )
            or not isinstance(current.get("createdBy"), str)
            or not isinstance(current.get("updatedBy"), str)
        ):
            raise StudentLifecycleInvariantError

    @staticmethod
    def _public_response(current: dict[str, object]) -> dict[str, object]:
        return {field: current[field] for field in PUBLIC_FIELDS}

    @staticmethod
    def _client_request_token(record: LifecycleIdempotencyRecord) -> str:
        return str(uuid5(UUID(int=0), f"{record.idempotency_id}#{record.request_hash}"))
