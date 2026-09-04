from typing import Any

from boto3.dynamodb.types import TypeDeserializer  # type: ignore[import-untyped]
from students_api.repositories.student_repository import StudentRepository


class FakeDynamoDBTable:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.last_key: dict[str, str] | None = None
        self.query_response: dict[str, Any] = {}
        self.query_call: dict[str, Any] | None = None

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        self.last_key = kwargs["Key"]
        return self.response

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.query_call = kwargs
        return self.query_response


class FakeDynamoDBClient:
    def __init__(self) -> None:
        self.transaction: dict[str, Any] | None = None
        self.get_calls: list[dict[str, Any]] = []
        self.items: dict[tuple[str, str, str], dict[str, Any]] = {}

    def transact_write_items(self, **kwargs: Any) -> dict[str, Any]:
        self.transaction = kwargs
        return {}

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        self.get_calls.append(kwargs)
        deserializer = TypeDeserializer()
        key = {name: deserializer.deserialize(value) for name, value in kwargs["Key"].items()}
        item = self.items.get((kwargs["TableName"], key["PK"], key["SK"]))
        return {"Item": item} if item is not None else {}


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


def test_create_student_writes_four_conditioned_items_in_fixed_order() -> None:
    client = FakeDynamoDBClient()
    repository = StudentRepository(
        FakeDynamoDBTable({}),
        client=client,
        students_table_name="Students",
        audit_table_name="Audit",
    )
    profile: dict[str, object] = {"PK": "STUDENT#1", "SK": "PROFILE", "version": 1}
    registration: dict[str, object] = {
        "PK": "UNIQUE#REGISTRATION#MAT-1",
        "SK": "UNIQUE",
        "studentId": "1",
    }
    email: dict[str, object] = {
        "PK": "UNIQUE#EMAIL#a@example.com",
        "SK": "UNIQUE",
        "studentId": "1",
    }
    audit: dict[str, object] = {
        "PK": "RESOURCE#STUDENT#1",
        "SK": "TS#now#EVENT#1",
        "correlationId": "r",
    }

    repository.create_student(
        profile=profile,
        registration=registration,
        email=email,
        audit=audit,
        client_request_token="11111111-1111-4111-8111-111111111111",
    )

    assert client.transaction is not None
    assert client.transaction["ClientRequestToken"] == "11111111-1111-4111-8111-111111111111"
    puts = [item["Put"] for item in client.transaction["TransactItems"]]
    assert [put["TableName"] for put in puts] == ["Students", "Students", "Students", "Audit"]
    assert all(
        put["ConditionExpression"] == "attribute_not_exists(PK) AND attribute_not_exists(SK)"
        for put in puts
    )
    deserializer = TypeDeserializer()
    assert [
        {name: deserializer.deserialize(value) for name, value in put["Item"].items()}["PK"]
        for put in puts
    ] == [profile["PK"], registration["PK"], email["PK"], audit["PK"]]


def test_reconciliation_reads_are_consistent_and_use_exact_tables() -> None:
    client = FakeDynamoDBClient()
    repository = StudentRepository(
        FakeDynamoDBTable({}),
        client=client,
        students_table_name="Students",
        audit_table_name="Audit",
    )

    assert repository.get_profile_consistent("1") is None
    assert repository.get_registration_reservation("MAT-1") is None
    assert repository.get_email_reservation("a@example.com") is None
    assert repository.get_audit_event("RESOURCE#STUDENT#1", "TS#now#EVENT#1") is None

    assert [call["TableName"] for call in client.get_calls] == [
        "Students",
        "Students",
        "Students",
        "Audit",
    ]
    assert all(call["ConsistentRead"] is True for call in client.get_calls)
