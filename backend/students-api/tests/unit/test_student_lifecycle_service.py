from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from students_api.errors import (
    OperationInProgressError,
    StudentLifecycleConditionError,
    StudentLifecycleInvariantError,
    StudentLifecycleUnresolvedError,
    StudentNotFoundError,
    StudentVersionConflictError,
)
from students_api.idempotency import LifecycleIdempotencyRecord
from students_api.services.student_lifecycle_service import StudentLifecycleService
from students_api.validation import DeactivateStudentInput, ReactivateStudentInput

CURRENT: dict[str, object] = {
    "studentId": "student-1",
    "registrationNumber": "MAT-1",
    "fullName": "Maria Silva",
    "studentEmail": "maria@example.invalid",
    "phone": "+12025550123",
    "birthDate": "2000-01-01",
    "status": "ACTIVE",
    "version": 3,
    "createdAt": "2020-01-01T00:00:00.000Z",
    "createdBy": "creator",
    "updatedAt": "2025-01-01T00:00:00.000Z",
    "updatedBy": "previous",
}
DEACTIVATE_RECORD = LifecycleIdempotencyRecord(
    "deactivate-student", "deactivate-student#scoped", "request-hash"
)


class Authorization:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def authorize_student_lifecycle(self, cognito_sub: str | None) -> str:
        self.calls.append("authorize")
        assert cognito_sub == "subject-1"
        return "actor-1"


class Idempotency:
    def __init__(
        self,
        calls: list[str],
        record: LifecycleIdempotencyRecord = DEACTIVATE_RECORD,
    ) -> None:
        self.calls = calls
        self.record = record
        self.acquisition: dict[str, Any] | None = None
        self.completed: dict[str, object] | None = None
        self.recovery: LifecycleIdempotencyRecord | Exception = record

    def acquire(self, **kwargs: Any) -> LifecycleIdempotencyRecord:
        self.calls.append("acquire")
        self.acquisition = kwargs
        return self.record

    def complete_noop(
        self, record: LifecycleIdempotencyRecord, response: dict[str, object]
    ) -> dict[str, object]:
        self.calls.append("complete_noop")
        self.completed = response
        return response

    def resolve(self, record: LifecycleIdempotencyRecord) -> LifecycleIdempotencyRecord:
        self.calls.append("resolve")
        if isinstance(self.recovery, Exception):
            raise self.recovery
        return self.recovery

    def release(self, record: LifecycleIdempotencyRecord) -> None:
        self.calls.append("release")


class Repository:
    def __init__(
        self,
        calls: list[str],
        profiles: list[dict[str, object] | None] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls = calls
        self.profiles = profiles or [CURRENT]
        self.error = error
        self.transition: Any = None

    def get_profile_consistent(self, student_id: str) -> dict[str, object] | None:
        self.calls.append("get")
        assert student_id == "student-1"
        return self.profiles.pop(0)

    def transition_student_lifecycle(self, **kwargs: Any) -> None:
        self.calls.append("transition")
        self.transition = kwargs["transition"]
        if self.error is not None:
            raise self.error


def make_service(
    repository: Repository,
    idempotency: Idempotency,
    calls: list[str],
) -> StudentLifecycleService:
    return StudentLifecycleService(
        repository,
        Authorization(calls),
        idempotency,
        environment="dev",
        audit_retention_days=90,
        idempotency_table_name="idempotency",
        clock=lambda: datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
        identifier_factory=lambda: UUID("11111111-1111-4111-8111-111111111111"),
    )


def deactivate(service: StudentLifecycleService, version: int = 3) -> dict[str, object]:
    return service.deactivate_student(
        cognito_sub="subject-1",
        idempotency_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        request_id="request-1",
        student_id="student-1",
        request=DeactivateStudentInput(version, "Motivo sintético seguro"),
    )


def reactivate(service: StudentLifecycleService, version: int = 3) -> dict[str, object]:
    return service.reactivate_student(
        cognito_sub="subject-1",
        idempotency_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        request_id="request-1",
        student_id="student-1",
        request=ReactivateStudentInput(version),
    )


@pytest.mark.parametrize("operation", ["deactivate", "reactivate"])
def test_effective_transition_builds_gate2_input(operation: str) -> None:
    calls: list[str] = []
    current = CURRENT if operation == "deactivate" else {**CURRENT, "status": "INACTIVE"}
    record = (
        DEACTIVATE_RECORD
        if operation == "deactivate"
        else LifecycleIdempotencyRecord(
            "reactivate-student", "reactivate-student#scoped", "request-hash"
        )
    )
    repository = Repository(calls, [current])
    idempotency = Idempotency(calls, record)
    target = make_service(repository, idempotency, calls)

    result = deactivate(target) if operation == "deactivate" else reactivate(target)

    assert calls == ["authorize", "acquire", "get", "transition"]
    assert repository.transition is not None
    transition = repository.transition
    expected_target = "INACTIVE" if operation == "deactivate" else "ACTIVE"
    expected_source = "ACTIVE" if operation == "deactivate" else "INACTIVE"
    assert transition.source_status == expected_source
    assert transition.target_status == expected_target
    assert transition.expected_version == 3
    assert transition.public_response == result
    assert result["status"] == expected_target
    assert result["version"] == 4
    assert result["updatedAt"] == "2026-09-11T12:00:00.000Z"
    assert "reason" not in result
    assert transition.audit_event.reason == (
        "Motivo sintético seguro" if operation == "deactivate" else None
    )
    assert transition.idempotency.idempotency_id == record.idempotency_id
    assert str(UUID(transition.idempotency.client_request_token)) == (
        transition.idempotency.client_request_token
    )
    assert idempotency.acquisition is not None
    assert idempotency.acquisition["operation"] == f"{operation}-student"
    expected_payload: dict[str, str | int] = {"expectedVersion": 3}
    if operation == "deactivate":
        expected_payload["reason"] = "Motivo sintético seguro"
    assert idempotency.acquisition["payload"] == expected_payload


def test_completed_replay_precedes_student_read_and_version_check() -> None:
    calls: list[str] = []
    stored = {"studentId": "student-1", "version": 1}
    record = LifecycleIdempotencyRecord(
        "deactivate-student", "deactivate-student#scoped", "hash", stored
    )
    repository = Repository(calls, [{**CURRENT, "version": 99}])

    assert deactivate(make_service(repository, Idempotency(calls, record), calls), 1) == stored
    assert calls == ["authorize", "acquire"]


@pytest.mark.parametrize(
    ("operation", "current"),
    [
        ("deactivate", CURRENT),
        ("deactivate", {**CURRENT, "status": "INACTIVE"}),
        ("reactivate", {**CURRENT, "status": "INACTIVE"}),
        ("reactivate", CURRENT),
    ],
)
def test_stale_version_precedes_transition_and_noop(
    operation: str, current: dict[str, object]
) -> None:
    calls: list[str] = []
    idempotency = Idempotency(calls)
    service = make_service(Repository(calls, [current]), idempotency, calls)

    with pytest.raises(StudentVersionConflictError):
        deactivate(service, 2) if operation == "deactivate" else reactivate(service, 2)
    assert calls == ["authorize", "acquire", "get", "release"]


@pytest.mark.parametrize(
    ("operation", "current"),
    [
        ("deactivate", {**CURRENT, "status": "INACTIVE"}),
        ("reactivate", CURRENT),
    ],
)
def test_current_target_state_is_idempotent_noop(
    operation: str, current: dict[str, object]
) -> None:
    calls: list[str] = []
    repository = Repository(calls, [current])
    idempotency = Idempotency(calls)
    service = make_service(repository, idempotency, calls)

    result = deactivate(service) if operation == "deactivate" else reactivate(service)

    assert calls == ["authorize", "acquire", "get", "complete_noop"]
    assert result["version"] == 3
    assert result["updatedAt"] == CURRENT["updatedAt"]
    assert repository.transition is None
    assert idempotency.completed == result


def test_missing_student_releases_claim() -> None:
    calls: list[str] = []
    with pytest.raises(StudentNotFoundError):
        deactivate(make_service(Repository(calls, [None]), Idempotency(calls), calls))
    assert calls == ["authorize", "acquire", "get", "release"]


@pytest.mark.parametrize(
    ("second", "expected"),
    [
        ({**CURRENT, "version": 4, "status": "INACTIVE"}, StudentVersionConflictError),
        ({**CURRENT, "status": "INACTIVE"}, StudentLifecycleInvariantError),
        (None, StudentLifecycleInvariantError),
    ],
)
def test_profile_condition_is_classified_by_consistent_reread(
    second: dict[str, object] | None, expected: type[Exception]
) -> None:
    calls: list[str] = []
    repository = Repository(
        calls,
        [CURRENT, second],
        error=StudentLifecycleConditionError(),
    )
    with pytest.raises(expected):
        deactivate(make_service(repository, Idempotency(calls), calls))
    assert calls == ["authorize", "acquire", "get", "transition", "get", "release"]


def test_unresolved_transaction_recovers_completed_without_profile_reread() -> None:
    calls: list[str] = []
    repository = Repository(calls, error=StudentLifecycleUnresolvedError())
    idempotency = Idempotency(calls)
    stored = {"studentId": "student-1", "version": 4}
    idempotency.recovery = LifecycleIdempotencyRecord("deactivate-student", "id", "hash", stored)

    assert deactivate(make_service(repository, idempotency, calls)) == stored
    assert calls == ["authorize", "acquire", "get", "transition", "resolve"]


def test_unresolved_inprogress_is_not_reclassified_from_student() -> None:
    calls: list[str] = []
    repository = Repository(calls, error=StudentLifecycleUnresolvedError())
    idempotency = Idempotency(calls)
    idempotency.recovery = OperationInProgressError()

    with pytest.raises(OperationInProgressError):
        deactivate(make_service(repository, idempotency, calls))
    assert calls == ["authorize", "acquire", "get", "transition", "resolve"]


def test_definitive_transaction_invariant_releases_matching_claim() -> None:
    calls: list[str] = []
    repository = Repository(calls, error=StudentLifecycleInvariantError())
    with pytest.raises(StudentLifecycleInvariantError):
        deactivate(make_service(repository, Idempotency(calls), calls))
    assert calls == ["authorize", "acquire", "get", "transition", "release"]


def test_client_token_is_stable_and_scoped_without_reason() -> None:
    calls: list[str] = []
    first_repository = Repository(calls)
    deactivate(make_service(first_repository, Idempotency(calls), calls))
    second_repository = Repository([])
    deactivate(make_service(second_repository, Idempotency([]), []))
    assert first_repository.transition is not None and second_repository.transition is not None
    first = first_repository.transition.idempotency.client_request_token
    second = second_repository.transition.idempotency.client_request_token
    assert first == second
    assert "Motivo" not in first
    other = StudentLifecycleService._client_request_token(
        LifecycleIdempotencyRecord("deactivate-student", "other", "request-hash")
    )
    other_request = StudentLifecycleService._client_request_token(
        LifecycleIdempotencyRecord(
            "deactivate-student", DEACTIVATE_RECORD.idempotency_id, "other-request-hash"
        )
    )
    assert len({first, other, other_request}) == 3
