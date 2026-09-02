from typing import Any

from students_api.repositories.student_repository import StudentRepository


class FakeDynamoDBTable:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.last_key: dict[str, str] | None = None
        self.query_response: dict[str, Any] = {}
        self.query_call: dict[str, Any] | None = None

    def get_item(self, *, Key: dict[str, str]) -> dict[str, Any]:
        self.last_key = Key
        return self.response

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.query_call = kwargs
        return self.query_response


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


def test_list_active_students_queries_status_index_with_prefix() -> None:
    from students_api.cursor import CursorPosition

    table = FakeDynamoDBTable({})
    table.query_response = {
        "Items": [{"studentId": "student-2"}],
        "LastEvaluatedKey": {
            "PK": "STUDENT#student-2",
            "SK": "PROFILE",
            "GSI1PK": "STATUS#ACTIVE",
            "GSI1SK": "NAME#ana#STUDENT#student-2",
        },
    }

    page = StudentRepository(table).list_students(
        status="ACTIVE",
        name_prefix="ana",
        limit=20,
        position=CursorPosition("student-1", "ana"),
    )

    assert table.query_call is not None
    assert table.query_call["IndexName"] == "gsi-status-name"
    assert table.query_call["Limit"] == 20
    assert table.query_call["ScanIndexForward"] is True
    assert table.query_call["ExclusiveStartKey"] == {
        "PK": "STUDENT#student-1",
        "SK": "PROFILE",
        "GSI1PK": "STATUS#ACTIVE",
        "GSI1SK": "NAME#ana#STUDENT#student-1",
    }
    assert "ConsistentRead" not in table.query_call
    assert page.next_position == CursorPosition("student-2", "ana")


def test_list_all_students_queries_all_index_without_scan() -> None:
    table = FakeDynamoDBTable({})
    table.query_response = {"Items": []}

    page = StudentRepository(table).list_students(
        status="ALL", name_prefix=None, limit=100, position=None
    )

    assert table.query_call is not None
    assert table.query_call["IndexName"] == "gsi-all-name"
    assert "ExclusiveStartKey" not in table.query_call
    assert page.items == []
    assert page.next_position is None
