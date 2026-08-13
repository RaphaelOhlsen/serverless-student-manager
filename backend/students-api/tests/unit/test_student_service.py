from typing import Any

import pytest
from students_api.errors import StudentNotFoundError
from students_api.services.student_service import StudentService


class FakeStudentRepository:
    def __init__(self, student: dict[str, Any] | None) -> None:
        self.student = student
        self.requested_student_id: str | None = None

    def get_by_id(self, student_id: str) -> dict[str, Any] | None:
        self.requested_student_id = student_id
        return self.student


def test_get_student_returns_existing_student() -> None:
    repository = FakeStudentRepository(
        {
            "PK": "STUDENT#student-123",
            "SK": "PROFILE",
            "studentId": "student-123",
            "fullName": "Maria Silva",
            "status": "ACTIVE",
        }
    )
    service = StudentService(repository)

    student = service.get_student("student-123")

    assert repository.requested_student_id == "student-123"
    assert student["studentId"] == "student-123"


def test_get_student_raises_not_found_when_student_does_not_exist() -> None:
    repository = FakeStudentRepository(None)
    service = StudentService(repository)

    with pytest.raises(StudentNotFoundError):
        service.get_student("missing-student")
