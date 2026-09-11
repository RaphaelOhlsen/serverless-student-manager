from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from students_api.errors import (
    OperationInProgressError,
    StudentEmailAlreadyExistsError,
    StudentNotFoundError,
    StudentUpdateUnresolvedError,
    StudentVersionConflictError,
)
from students_api.idempotency import UpdateIdempotencyRecord
from students_api.services.update_student_service import UpdateStudentService
from students_api.validation import UpdateStudentInput

CURRENT: dict[str, object] = {
    "studentId": "student-1",
    "registrationNumber": "MAT-1",
    "fullName": "Maria Silva",
    "studentEmail": "maria@example.com",
    "phone": "+5511999999999",
    "birthDate": "2000-01-01",
    "status": "INACTIVE",
    "version": 3,
    "createdAt": "2020-01-01T00:00:00.000Z",
    "createdBy": "creator",
    "updatedAt": "2025-01-01T00:00:00.000Z",
    "updatedBy": "previous",
}
RECORD = UpdateIdempotencyRecord("update-student#scoped", "request-hash")


class Authorization:
    def authorize_update_student(self, cognito_sub: str | None) -> str:
        assert cognito_sub == "subject-1"
        return "actor-1"


class Idempotency:
    def __init__(self, record: UpdateIdempotencyRecord = RECORD) -> None:
        self.record = record
        self.calls: list[str] = []
        self.payload: dict[str, str | int] | None = None
        self.completed: dict[str, object] | None = None
        self.recovery: UpdateIdempotencyRecord | Exception = record

    def acquire(self, **kwargs: Any) -> UpdateIdempotencyRecord:
        self.calls.append("acquire")
        self.payload = kwargs["payload"]
        return self.record

    def complete_noop(
        self, record: UpdateIdempotencyRecord, response: dict[str, object]
    ) -> dict[str, object]:
        self.calls.append("complete_noop")
        self.completed = response
        return response

    def resolve(self, record: UpdateIdempotencyRecord) -> UpdateIdempotencyRecord:
        self.calls.append("resolve")
        if isinstance(self.recovery, Exception):
            raise self.recovery
        return self.recovery

    def release(self, record: UpdateIdempotencyRecord) -> None:
        self.calls.append("release")


class Repository:
    def __init__(
        self,
        current: dict[str, object] | None = CURRENT,
        error: Exception | None = None,
    ) -> None:
        self.current = current
        self.error = error
        self.calls: list[str] = []
        self.update: dict[str, Any] | None = None

    def get_profile_consistent(self, student_id: str) -> dict[str, object] | None:
        self.calls.append("get")
        assert student_id == "student-1"
        return self.current

    def update_student(self, **kwargs: Any) -> None:
        self.calls.append("update")
        self.update = kwargs
        if self.error is not None:
            raise self.error


def service(
    repository: Repository,
    idempotency: Idempotency,
) -> UpdateStudentService:
    identifiers = iter(
        [
            UUID("11111111-1111-4111-8111-111111111111"),
            UUID("22222222-2222-4222-8222-222222222222"),
        ]
    )
    return UpdateStudentService(
        repository,
        Authorization(),
        idempotency,
        environment="dev",
        audit_retention_days=90,
        idempotency_table_name="idempotency",
        clock=lambda: datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
        identifier_factory=lambda: next(identifiers),
    )


def update(
    target: UpdateStudentService,
    patch: UpdateStudentInput,
) -> dict[str, object]:
    return target.update_student(
        cognito_sub="subject-1",
        idempotency_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        request_id="request-1",
        student_id="student-1",
        patch=patch,
    )


def test_completed_replay_returns_before_current_student_read() -> None:
    original = {"studentId": "student-1", "version": 2}
    repository = Repository({**CURRENT, "version": 9})
    idempotency = Idempotency(UpdateIdempotencyRecord("id", "hash", original))

    result = update(service(repository, idempotency), UpdateStudentInput(1, full_name="Old"))

    assert result == original
    assert idempotency.calls == ["acquire"]
    assert repository.calls == []


@pytest.mark.parametrize(
    ("current", "patch", "error"),
    [
        (None, UpdateStudentInput(3, full_name="Outro Nome"), StudentNotFoundError),
        (
            CURRENT,
            UpdateStudentInput(2, full_name="Maria Silva"),
            StudentVersionConflictError,
        ),
    ],
)
def test_definitive_pretransaction_failures_release_acquisition(
    current: dict[str, object] | None,
    patch: UpdateStudentInput,
    error: type[Exception],
) -> None:
    idempotency = Idempotency()
    with pytest.raises(error):
        update(service(Repository(current), idempotency), patch)
    assert idempotency.calls == ["acquire", "release"]


def test_noop_preserves_public_state_and_completes_idempotency() -> None:
    repository = Repository()
    idempotency = Idempotency()

    result = update(
        service(repository, idempotency),
        UpdateStudentInput(3, student_email="maria@example.com"),
    )

    assert result["version"] == 3
    assert result["updatedAt"] == CURRENT["updatedAt"]
    assert "updatedBy" not in result
    assert repository.calls == ["get"]
    assert idempotency.calls == ["acquire", "complete_noop"]


def test_effective_update_resolves_only_present_fields_and_calls_gate2_primitive() -> None:
    repository = Repository()
    idempotency = Idempotency()

    result = update(
        service(repository, idempotency),
        UpdateStudentInput(3, full_name="Novo Nome", phone="+5521999999999"),
    )

    assert repository.calls == ["get", "update"]
    assert repository.update is not None
    assert repository.update["target"] == {
        "fullName": "Novo Nome",
        "studentEmail": CURRENT["studentEmail"],
        "phone": "+5521999999999",
        "birthDate": CURRENT["birthDate"],
    }
    context = repository.update["context"]
    assert context.actor_id == "actor-1"
    assert context.correlation_id == "request-1"
    assert str(UUID(context.client_request_token)) == context.client_request_token
    assert "Novo Nome" not in context.client_request_token
    assert result["version"] == 4
    assert result["updatedAt"] == "2026-09-11T12:00:00.000Z"
    assert idempotency.payload == {
        "expectedVersion": 3,
        "fullName": "Novo Nome",
        "phone": "+5521999999999",
    }


def test_client_request_token_is_stable_and_scoped() -> None:
    first_repository = Repository()
    update(
        service(first_repository, Idempotency()),
        UpdateStudentInput(3, phone="+5521999999999"),
    )
    second_repository = Repository()
    update(
        service(second_repository, Idempotency()),
        UpdateStudentInput(3, phone="+5521999999999"),
    )
    assert first_repository.update is not None and second_repository.update is not None
    first = first_repository.update["context"].client_request_token
    second = second_repository.update["context"].client_request_token
    assert first == second
    other = UpdateStudentService._client_request_token(
        UpdateIdempotencyRecord("update-student#other-actor", "request-hash")
    )
    assert other != first


def test_unresolved_transaction_recovers_completed_response() -> None:
    repository = Repository(error=StudentUpdateUnresolvedError())
    idempotency = Idempotency()
    stored = {"studentId": "student-1", "version": 4}
    idempotency.recovery = UpdateIdempotencyRecord("id", "hash", stored)

    result = update(
        service(repository, idempotency),
        UpdateStudentInput(3, phone="+5521999999999"),
    )

    assert result == stored
    assert idempotency.calls == ["acquire", "resolve"]


def test_unresolved_inprogress_never_becomes_version_conflict() -> None:
    repository = Repository(error=StudentUpdateUnresolvedError())
    idempotency = Idempotency()
    idempotency.recovery = OperationInProgressError()

    with pytest.raises(OperationInProgressError):
        update(
            service(repository, idempotency),
            UpdateStudentInput(3, phone="+5521999999999"),
        )


@pytest.mark.parametrize("error", [StudentVersionConflictError(), StudentEmailAlreadyExistsError()])
def test_transactional_functional_conflict_releases_idempotency(error: Exception) -> None:
    idempotency = Idempotency()
    with pytest.raises(type(error)):
        update(
            service(Repository(error=error), idempotency),
            UpdateStudentInput(3, phone="+5521999999999"),
        )
    assert idempotency.calls == ["acquire", "release"]
