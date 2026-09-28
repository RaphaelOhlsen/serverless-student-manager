from typing import Any, cast

import pytest
from students_api.cursor import CursorPosition, decode_cursor
from students_api.errors import ForbiddenError, StudentNotFoundError
from students_api.repositories.student_repository import StudentPage
from students_api.services.student_service import StudentService


class FakeStudentRepository:
    def __init__(self, student: dict[str, Any] | None, calls: list[str] | None = None) -> None:
        self.student = student
        self.calls = calls if calls is not None else []
        self.requested_student_id: str | None = None
        self.read_count = 0

    def get_by_id(self, student_id: str) -> dict[str, Any] | None:
        self.calls.append("get")
        self.read_count += 1
        self.requested_student_id = student_id
        return self.student

    def list_students(self, **kwargs: Any) -> StudentPage:
        self.list_call = kwargs
        return StudentPage(
            items=[
                {
                    "PK": "STUDENT#student-1",
                    "studentId": "student-1",
                    "registrationNumber": "MAT-1",
                    "fullName": "Ana Silva",
                    "status": "ACTIVE",
                    "studentEmail": "private@example.com",
                }
            ],
            next_position=CursorPosition("student-1", "ana silva"),
        )


class FakeRegistrationRepository(FakeStudentRepository):
    def __init__(
        self,
        student: dict[str, Any] | None,
        calls: list[str] | None = None,
        error: Exception | None = None,
    ) -> None:
        super().__init__(student, calls)
        self.error = error
        self.requested_registration: str | None = None

    def get_by_registration(self, registration_number: str) -> dict[str, Any] | None:
        self.calls.append("lookup_registration")
        self.read_count += 1
        self.requested_registration = registration_number
        if self.error is not None:
            raise self.error
        return self.student


class AllowAuthorization:
    def __init__(
        self,
        calls: list[str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls = calls if calls is not None else []
        self.error = error
        self.subject: str | None = None

    def authorize_list_students(self, cognito_sub: str | None) -> None:
        self.calls.append("authorize")
        self.subject = cognito_sub
        if self.error is not None:
            raise self.error


def test_get_student_returns_existing_student() -> None:
    calls: list[str] = []
    repository = FakeStudentRepository(
        {
            "PK": "STUDENT#student-123",
            "SK": "PROFILE",
            "studentId": "student-123",
            "fullName": "Maria Silva",
            "status": "ACTIVE",
        },
        calls,
    )
    authorization = AllowAuthorization(calls)
    service = StudentService(repository, authorization)

    student = service.get_student(cognito_sub="subject-1", student_id="student-123")

    assert calls == ["authorize", "get"]
    assert authorization.subject == "subject-1"
    assert repository.requested_student_id == "student-123"
    assert student["studentId"] == "student-123"


def test_get_student_raises_not_found_when_student_does_not_exist() -> None:
    calls: list[str] = []
    repository = FakeStudentRepository(None, calls)
    service = StudentService(repository, AllowAuthorization(calls))

    with pytest.raises(StudentNotFoundError):
        service.get_student(cognito_sub="subject-1", student_id="missing-student")

    assert calls == ["authorize", "get"]


def test_get_student_does_not_read_student_when_authorization_fails() -> None:
    calls: list[str] = []
    repository = FakeStudentRepository({"studentId": "student-123"}, calls)
    authorization = AllowAuthorization(calls, ForbiddenError())
    service = StudentService(repository, authorization)

    with pytest.raises(ForbiddenError):
        service.get_student(cognito_sub="subject-1", student_id="student-123")

    assert calls == ["authorize"]
    assert repository.read_count == 0


def test_list_students_authorizes_normalizes_and_returns_public_envelope() -> None:
    repository = FakeStudentRepository(None)
    authorization = AllowAuthorization()
    service = StudentService(repository, authorization)

    result = service.list_students(
        cognito_sub="subject-1",
        limit=20,
        status="ACTIVE",
        name_prefix="  ANA  ",
        cursor=None,
    )

    assert authorization.subject == "subject-1"
    assert repository.list_call["name_prefix"] == "ana"
    assert result["items"] == [
        {
            "studentId": "student-1",
            "registrationNumber": "MAT-1",
            "fullName": "Ana Silva",
            "status": "ACTIVE",
        }
    ]
    assert result["hasMore"] is True
    assert decode_cursor(result["nextCursor"], "ACTIVE", "ana") == CursorPosition(
        "student-1", "ana silva"
    )


def lookup_by_registration(
    service: StudentService,
    *,
    cognito_sub: str | None = "subject-1",
    registration_number: str = "AB-1234",
) -> dict[str, Any]:
    lookup = getattr(service, "get_student_by_registration", None)
    assert callable(lookup), "student service registration lookup API is missing"
    return cast(
        dict[str, Any],
        lookup(cognito_sub=cognito_sub, registration_number=registration_number),
    )


@pytest.mark.parametrize("status", ["ACTIVE", "INACTIVE"])
def test_get_student_by_registration_returns_detail_representation(status: str) -> None:
    calls: list[str] = []
    profile = {
        "studentId": "student-123",
        "registrationNumber": "AB-1234",
        "fullName": "Maria Silva",
        "studentEmail": "maria@example.com",
        "phone": "+5527999999999",
        "birthDate": "2000-05-10",
        "status": status,
        "version": 2,
        "createdAt": "2026-09-10T12:07:54.388Z",
        "updatedAt": "2026-09-11T16:36:38.541Z",
    }
    repository = FakeRegistrationRepository(profile, calls)
    authorization = AllowAuthorization(calls)
    service = StudentService(repository, authorization)

    result = lookup_by_registration(service, registration_number=" ab-1234 ")

    assert result == profile
    assert calls == ["authorize", "lookup_registration"]
    assert authorization.subject == "subject-1"
    assert repository.requested_registration == "AB-1234"


def test_get_student_by_registration_raises_not_found_for_absent_reservation() -> None:
    service = StudentService(FakeRegistrationRepository(None), AllowAuthorization())

    with pytest.raises(StudentNotFoundError):
        lookup_by_registration(service)


def test_get_student_by_registration_rejects_invalid_registration() -> None:
    repository = FakeRegistrationRepository(None)
    service = StudentService(repository, AllowAuthorization())

    with pytest.raises(ValueError):
        lookup_by_registration(service, registration_number="AB_1234")

    assert repository.read_count == 0


def test_get_student_by_registration_preserves_repository_invariant_failure() -> None:
    corruption = RuntimeError("orphaned registration reservation")
    service = StudentService(
        FakeRegistrationRepository(None, error=corruption), AllowAuthorization()
    )

    with pytest.raises(RuntimeError) as raised:
        lookup_by_registration(service)

    assert raised.value is corruption
    assert not isinstance(raised.value, StudentNotFoundError)


def test_get_student_by_registration_does_not_read_when_authorization_fails() -> None:
    calls: list[str] = []
    repository = FakeRegistrationRepository({"studentId": "student-123"}, calls)
    authorization = AllowAuthorization(calls, ForbiddenError())
    service = StudentService(repository, authorization)

    with pytest.raises(ForbiddenError):
        lookup_by_registration(service)

    assert calls == ["authorize"]
    assert repository.read_count == 0
