from typing import Any

from students_api.repositories.student_repository import StudentRepository


class FakeDynamoDBTable:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.last_key: dict[str, str] | None = None

    def get_item(self, *, Key: dict[str, str]) -> dict[str, Any]:
        self.last_key = Key
        return self.response


def test_get_by_id_uses_student_profile_key() -> None:
    table = FakeDynamoDBTable(
        {
            "Item": {
                "PK": "STUDENT#student-123",
                "SK": "PROFILE",
                "studentId": "student-123",
                "fullName": "Maria Silva",
            }
        }
    )

    repository = StudentRepository(table)

    student = repository.get_by_id("student-123")

    assert table.last_key == {
        "PK": "STUDENT#student-123",
        "SK": "PROFILE",
    }
    assert student is not None
    assert student["studentId"] == "student-123"


def test_get_by_id_returns_none_when_student_does_not_exist() -> None:
    table = FakeDynamoDBTable({})

    repository = StudentRepository(table)

    student = repository.get_by_id("missing-student")

    assert table.last_key == {
        "PK": "STUDENT#missing-student",
        "SK": "PROFILE",
    }
    assert student is None
