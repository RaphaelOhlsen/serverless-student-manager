from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4, uuid5

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from students_api.errors import (
    RegistrationNumberAlreadyExistsError,
    StudentEmailAlreadyExistsError,
    StudentUniquenessConflictError,
)
from students_api.validation import CreateStudentInput


class CreateStudentRepositoryProtocol(Protocol):
    def create_student(
        self,
        *,
        profile: dict[str, object],
        registration: dict[str, object],
        email: dict[str, object],
        audit: dict[str, object],
        client_request_token: str,
    ) -> None: ...

    def get_registration_reservation(
        self, registration_number: str
    ) -> dict[str, object] | None: ...

    def get_email_reservation(self, normalized_email: str) -> dict[str, object] | None: ...

    def get_profile_consistent(self, student_id: str) -> dict[str, object] | None: ...

    def get_audit_event(self, partition_key: str, sort_key: str) -> dict[str, object] | None: ...


class CreateAuthorizationProtocol(Protocol):
    def authorize_create_student(self, cognito_sub: str | None) -> str: ...


class IdempotencyProtocol(Protocol):
    def execute(
        self,
        *,
        data: dict[str, Any],
        action: Callable[[], dict[str, object]],
    ) -> dict[str, object]: ...


class CreateStudentService:
    def __init__(
        self,
        repository: CreateStudentRepositoryProtocol,
        authorization: CreateAuthorizationProtocol,
        idempotency: IdempotencyProtocol,
        *,
        environment: str,
        audit_retention_days: int,
        clock: Callable[[], datetime] | None = None,
        identifier_factory: Callable[[], UUID] | None = None,
    ) -> None:
        self._repository = repository
        self._authorization = authorization
        self._idempotency = idempotency
        self._environment = environment
        self._audit_retention_days = audit_retention_days
        self._clock = clock or (lambda: datetime.now(UTC))
        self._identifier_factory = identifier_factory or uuid4

    def create_student(
        self,
        *,
        cognito_sub: str | None,
        idempotency_key: str,
        request_id: str | None,
        student: CreateStudentInput,
    ) -> dict[str, object]:
        actor_id = self._authorization.authorize_create_student(cognito_sub)
        data: dict[str, Any] = {
            "environment": self._environment,
            "actorId": actor_id,
            "operation": "create-student",
            "idempotencyKey": idempotency_key,
            "payload": student.payload(),
        }
        return self._idempotency.execute(
            data=data,
            action=lambda: self._create_once(
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                request_id=request_id,
                student=student,
            ),
        )

    def _create_once(
        self,
        *,
        actor_id: str,
        idempotency_key: str,
        request_id: str | None,
        student: CreateStudentInput,
    ) -> dict[str, object]:
        now = self._clock().astimezone(UTC)
        occurred_at = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        student_id = str(self._identifier_factory())
        event_id = str(self._identifier_factory())
        correlation_id = request_id or str(self._identifier_factory())
        response = self._response(student_id, occurred_at, student)
        profile = self._profile(student_id, actor_id, occurred_at, student)
        registration: dict[str, object] = {
            "PK": f"UNIQUE#REGISTRATION#{student.registration_number}",
            "SK": "UNIQUE",
            "studentId": student_id,
        }
        email: dict[str, object] = {
            "PK": f"UNIQUE#EMAIL#{student.student_email}",
            "SK": "UNIQUE",
            "studentId": student_id,
        }
        audit = self._audit_event(
            student_id=student_id,
            actor_id=actor_id,
            event_id=event_id,
            correlation_id=correlation_id,
            occurred_at=occurred_at,
            expires_at=int((now + timedelta(days=self._audit_retention_days)).timestamp()),
        )
        token_source = f"HTTP#{self._environment}#{actor_id}#create-student#{idempotency_key}"
        token = str(uuid5(UUID(int=0), token_source))

        try:
            self._repository.create_student(
                profile=profile,
                registration=registration,
                email=email,
                audit=audit,
                client_request_token=token,
            )
        except ClientError as error:
            if self._error_code(error) == "TransactionCanceledException":
                self._raise_transaction_conflict(error, student)
            if self._reconciles_all(profile, registration, email, audit):
                return response
            raise
        except Exception:
            if self._reconciles_all(profile, registration, email, audit):
                return response
            raise
        return response

    def _raise_transaction_conflict(
        self,
        error: ClientError,
        student: CreateStudentInput,
    ) -> None:
        reasons = error.response.get("CancellationReasons")
        if reasons is None:
            self._raise_confirmed_uniqueness_conflict(student, {1, 2})
        if not isinstance(reasons, list) or len(reasons) != 4:
            raise RuntimeError("Transaction cancellation reason is ambiguous")
        codes = [reason.get("Code") if isinstance(reason, dict) else None for reason in reasons]
        condition_failures = {
            index for index, code in enumerate(codes) if code == "ConditionalCheckFailed"
        }
        if not condition_failures or not condition_failures.issubset({1, 2}):
            raise RuntimeError("Transaction cancellation is not a uniqueness conflict")
        if any(code not in {"None", "ConditionalCheckFailed"} for code in codes):
            raise RuntimeError("Transaction cancellation is ambiguous")

        self._raise_confirmed_uniqueness_conflict(student, condition_failures)

    def _raise_confirmed_uniqueness_conflict(
        self,
        student: CreateStudentInput,
        possible_failures: set[int],
    ) -> None:

        registration = self._repository.get_registration_reservation(student.registration_number)
        email = self._repository.get_email_reservation(student.student_email)
        registration_conflict = 1 in possible_failures and registration is not None
        email_conflict = 2 in possible_failures and email is not None
        if registration_conflict and email_conflict:
            raise StudentUniquenessConflictError
        if registration_conflict:
            raise RegistrationNumberAlreadyExistsError
        if email_conflict:
            raise StudentEmailAlreadyExistsError
        raise RuntimeError("Transaction uniqueness conflict could not be confirmed")

    def _reconciles_all(
        self,
        profile: dict[str, object],
        registration: dict[str, object],
        email: dict[str, object],
        audit: dict[str, object],
    ) -> bool:
        try:
            actual_profile = self._repository.get_profile_consistent(str(profile["studentId"]))
            actual_registration = self._repository.get_registration_reservation(
                str(profile["registrationNumber"])
            )
            actual_email = self._repository.get_email_reservation(str(profile["normalizedEmail"]))
            actual_audit = self._repository.get_audit_event(str(audit["PK"]), str(audit["SK"]))
        except Exception:
            return False
        return (
            self._contains(actual_profile, profile)
            and self._contains(actual_registration, registration)
            and self._contains(actual_email, email)
            and self._contains(actual_audit, audit)
        )

    @staticmethod
    def _contains(actual: dict[str, object] | None, expected: dict[str, object]) -> bool:
        return actual is not None and all(
            actual.get(key) == value for key, value in expected.items()
        )

    @staticmethod
    def _profile(
        student_id: str,
        actor_id: str,
        occurred_at: str,
        student: CreateStudentInput,
    ) -> dict[str, object]:
        student_key = f"STUDENT#{student_id}"
        name_key = f"NAME#{student.normalized_name}#{student_key}"
        return {
            "PK": student_key,
            "SK": "PROFILE",
            "studentId": student_id,
            "registrationNumber": student.registration_number,
            "fullName": student.full_name,
            "normalizedName": student.normalized_name,
            "studentEmail": student.student_email,
            "normalizedEmail": student.student_email,
            "phone": student.phone,
            "birthDate": student.birth_date,
            "status": "ACTIVE",
            "version": 1,
            "createdAt": occurred_at,
            "createdBy": actor_id,
            "updatedAt": occurred_at,
            "updatedBy": actor_id,
            "GSI1PK": "STATUS#ACTIVE",
            "GSI1SK": name_key,
            "GSI2PK": "ALL",
            "GSI2SK": name_key,
        }

    @staticmethod
    def _audit_event(
        *,
        student_id: str,
        actor_id: str,
        event_id: str,
        correlation_id: str,
        occurred_at: str,
        expires_at: int,
    ) -> dict[str, object]:
        sort_key = f"TS#{occurred_at}#EVENT#{event_id}"
        return {
            "PK": f"RESOURCE#STUDENT#{student_id}",
            "SK": sort_key,
            "eventId": event_id,
            "eventType": "STUDENT_CREATED",
            "resourceType": "STUDENT",
            "resourceId": student_id,
            "actorId": actor_id,
            "occurredAt": occurred_at,
            "result": "SUCCESS",
            "correlationId": correlation_id,
            "changes": {
                "status": {"from": None, "to": "ACTIVE"},
                "version": {"from": None, "to": 1},
            },
            "GSI1PK": f"ACTOR#{actor_id}",
            "GSI1SK": sort_key,
            "GSI2PK": f"CORRELATION#{correlation_id}",
            "GSI2SK": sort_key,
            "GSI3PK": f"PERIOD#{occurred_at[:7]}",
            "GSI3SK": sort_key,
            "expiresAt": expires_at,
        }

    @staticmethod
    def _response(
        student_id: str,
        occurred_at: str,
        student: CreateStudentInput,
    ) -> dict[str, object]:
        return {
            "studentId": student_id,
            "registrationNumber": student.registration_number,
            "fullName": student.full_name,
            "studentEmail": student.student_email,
            "phone": student.phone,
            "birthDate": student.birth_date,
            "status": "ACTIVE",
            "version": 1,
            "createdAt": occurred_at,
            "updatedAt": occurred_at,
        }

    @staticmethod
    def _error_code(error: ClientError) -> str:
        return str(error.response.get("Error", {}).get("Code", ""))
