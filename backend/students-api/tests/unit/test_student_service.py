from typing import Any

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
