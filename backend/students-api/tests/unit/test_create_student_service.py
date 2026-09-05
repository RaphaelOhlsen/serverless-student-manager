from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from students_api.errors import (
    RegistrationNumberAlreadyExistsError,
    StudentEmailAlreadyExistsError,
    StudentUniquenessConflictError,
)
from students_api.services.create_student_service import CreateStudentService
from students_api.validation import CreateStudentInput


class FakeAuthorization:
    def authorize_create_student(self, cognito_sub: str | None) -> str:
        assert cognito_sub == "subject-1"
        return "user-1"


class PassthroughIdempotency:
    def __init__(self) -> None:
        self.data: dict[str, Any] | None = None

    def execute(
        self, *, data: dict[str, Any], action: Callable[[], dict[str, object]]
    ) -> dict[str, object]:
        self.data = data
        return action()


class FakeRepository:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.call: dict[str, Any] | None = None
        self.reconciled: dict[str, dict[str, object] | None] = {}

    def create_student(self, **kwargs: Any) -> None:
        self.call = kwargs
        if self.error is not None:
            raise self.error

    def get_registration_reservation(self, registration_number: str) -> dict[str, object] | None:
        return self.reconciled.get("registration")

    def get_email_reservation(self, normalized_email: str) -> dict[str, object] | None:
        return self.reconciled.get("email")

    def get_profile_consistent(self, student_id: str) -> dict[str, object] | None:
        return self.reconciled.get("profile")

    def get_audit_event(self, partition_key: str, sort_key: str) -> dict[str, object] | None:
        return self.reconciled.get("audit")

    def set_coherent_reconciliation(self) -> None:
        assert self.call is not None
        for name in ("profile", "registration", "email", "audit"):
            self.reconciled[name] = self.call[name]


STUDENT = CreateStudentInput(
    full_name="Maria da Silva",
    normalized_name="maria da silva",
    registration_number="MAT-0001",
    student_email="maria@example.com",
    phone="+5527999999999",
    birth_date="2010-05-21",
)


def build_service(
    repository: FakeRepository,
) -> tuple[CreateStudentService, PassthroughIdempotency]:
    idempotency = PassthroughIdempotency()
    identifiers = iter(
        [
            UUID("11111111-1111-4111-8111-111111111111"),
            UUID("22222222-2222-4222-8222-222222222222"),
            UUID("33333333-3333-4333-8333-333333333333"),
        ]
    )
    service = CreateStudentService(
        repository,
        FakeAuthorization(),
        idempotency,
        environment="dev",
        audit_retention_days=90,
        clock=lambda: datetime(2026, 9, 4, 12, 30, tzinfo=UTC),
        identifier_factory=lambda: next(identifiers),
    )
    return service, idempotency


def create(service: CreateStudentService) -> dict[str, object]:
    return service.create_student(
        cognito_sub="subject-1",
        idempotency_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        request_id="request-1",
        student=STUDENT,
    )


def test_success_builds_public_response_and_exact_transaction_artifacts() -> None:
    repository = FakeRepository()
    service, idempotency = build_service(repository)

    result = create(service)

    assert result == {
        "studentId": "11111111-1111-4111-8111-111111111111",
        "registrationNumber": "MAT-0001",
        "fullName": "Maria da Silva",
        "studentEmail": "maria@example.com",
        "phone": "+5527999999999",
        "birthDate": "2010-05-21",
        "status": "ACTIVE",
        "version": 1,
        "createdAt": "2026-09-04T12:30:00.000Z",
        "updatedAt": "2026-09-04T12:30:00.000Z",
    }
    assert type(result["version"]) is int
    assert idempotency.data == {
        "environment": "dev",
        "actorId": "user-1",
        "operation": "create-student",
        "idempotencyKey": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "payload": STUDENT.payload(),
    }
    assert repository.call is not None
    profile = repository.call["profile"]
    assert profile["status"] == "ACTIVE" and profile["version"] == 1
    assert profile["createdAt"] == profile["updatedAt"]
    assert profile["createdBy"] == profile["updatedBy"] == "user-1"
    assert repository.call["registration"] == {
        "PK": "UNIQUE#REGISTRATION#MAT-0001",
        "SK": "UNIQUE",
        "studentId": result["studentId"],
    }
    assert repository.call["email"] == {
        "PK": "UNIQUE#EMAIL#maria@example.com",
        "SK": "UNIQUE",
        "studentId": result["studentId"],
    }
    audit = repository.call["audit"]
    assert audit["eventType"] == "STUDENT_CREATED"
    assert audit["result"] == "SUCCESS"
    assert audit["actorId"] == "user-1"
    assert audit["changes"] == {
        "status": {"from": None, "to": "ACTIVE"},
        "version": {"from": None, "to": 1},
    }
    assert "studentEmail" not in audit and "phone" not in audit and "body" not in audit
    assert (
        str(UUID(repository.call["client_request_token"]))
        == repository.call["client_request_token"]
    )


def transaction_cancelled(*failed_indexes: int, ambiguous: bool = False) -> ClientError:
    reasons = [
        {"Code": "ConditionalCheckFailed" if index in failed_indexes else "None"}
        for index in range(4)
    ]
    if ambiguous:
        reasons[0] = {"Code": "TransactionConflict"}
    return ClientError(
        {
            "Error": {"Code": "TransactionCanceledException", "Message": "cancelled"},
            "CancellationReasons": reasons,
        },
        "TransactWriteItems",
    )


@pytest.mark.parametrize(
    "failed_indexes,registration,email,error_type",
    [
        ((1,), {"studentId": "other"}, None, RegistrationNumberAlreadyExistsError),
        ((2,), None, {"studentId": "other"}, StudentEmailAlreadyExistsError),
        (
            (1, 2),
            {"studentId": "other"},
            {"studentId": "other"},
            StudentUniquenessConflictError,
        ),
    ],
)
def test_transaction_cancellation_maps_uniqueness_conflicts(
    failed_indexes: tuple[int, ...],
    registration: dict[str, object] | None,
    email: dict[str, object] | None,
    error_type: type[Exception],
) -> None:
    repository = FakeRepository(transaction_cancelled(*failed_indexes))
    repository.reconciled = {"registration": registration, "email": email}
    service, _ = build_service(repository)

    with pytest.raises(error_type):
        create(service)


@pytest.mark.parametrize(
    "error",
    [
        transaction_cancelled(0),
        transaction_cancelled(1, ambiguous=True),
        transaction_cancelled(1),
    ],
)
def test_unrecognized_or_unconfirmed_transaction_cancellation_fails_closed(
    error: ClientError,
) -> None:
    service, _ = build_service(FakeRepository(error))

    with pytest.raises(RuntimeError):
        create(service)


def test_missing_cancellation_reasons_map_consistently_confirmed_conflict() -> None:
    error = ClientError(
        {"Error": {"Code": "TransactionCanceledException", "Message": "cancelled"}},
        "TransactWriteItems",
    )
    repository = FakeRepository(error)
    repository.reconciled["registration"] = {"studentId": "other"}
    service, _ = build_service(repository)

    with pytest.raises(RegistrationNumberAlreadyExistsError):
        create(service)


def test_ambiguous_error_is_reconciled_only_when_all_four_artifacts_match() -> None:
    repository = FakeRepository(RuntimeError("ambiguous"))
    original_create = repository.create_student

    def create_and_make_visible(**kwargs: Any) -> None:
        try:
            original_create(**kwargs)
        finally:
            repository.set_coherent_reconciliation()

    repository.create_student = create_and_make_visible  # type: ignore[method-assign]
    service, _ = build_service(repository)

    assert create(service)["studentId"] == "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize("artifact", ["profile", "registration", "email", "audit"])
def test_ambiguous_error_fails_closed_for_missing_or_inconsistent_artifact(
    artifact: str,
) -> None:
    repository = FakeRepository(RuntimeError("ambiguous"))
    original_create = repository.create_student

    def create_with_incomplete_result(**kwargs: Any) -> None:
        try:
            original_create(**kwargs)
        finally:
            repository.set_coherent_reconciliation()
            repository.reconciled[artifact] = None

    repository.create_student = create_with_incomplete_result  # type: ignore[method-assign]
    service, _ = build_service(repository)

    with pytest.raises(RuntimeError, match="ambiguous"):
        create(service)


def test_ambiguous_error_fails_closed_for_inconsistent_audit() -> None:
    repository = FakeRepository(RuntimeError("ambiguous"))
    original_create = repository.create_student

    def create_with_inconsistent_audit(**kwargs: Any) -> None:
        try:
            original_create(**kwargs)
        finally:
            repository.set_coherent_reconciliation()
            repository.reconciled["audit"] = {"eventType": "OTHER"}

    repository.create_student = create_with_inconsistent_audit  # type: ignore[method-assign]
    service, _ = build_service(repository)

    with pytest.raises(RuntimeError, match="ambiguous"):
        create(service)
