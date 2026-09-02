import json
from typing import Any, cast

import pytest
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from students_api.errors import StudentNotFoundError
from students_api.routes.students import register_student_routes


class FakeStudentService:
    def __init__(self, student: dict[str, Any] | None) -> None:
        self.student = student
        self.requested_student_id: str | None = None

    def get_student(self, student_id: str) -> dict[str, Any]:
        self.requested_student_id = student_id

        if self.student is None:
            raise StudentNotFoundError

        return self.student

    def list_students(self, **kwargs: Any) -> dict[str, Any]:
        self.list_call = kwargs
        return {"items": [], "nextCursor": None, "hasMore": False}


def make_event(student_id: str) -> dict[str, Any]:
    return {
        "version": "2.0",
        "routeKey": "GET /students/{studentId}",
        "rawPath": f"/students/{student_id}",
        "rawQueryString": "",
        "headers": {},
        "requestContext": {
            "http": {
                "method": "GET",
                "path": f"/students/{student_id}",
            },
            "requestId": "unit-test-request",
            "routeKey": "GET /students/{studentId}",
            "stage": "$default",
        },
        "isBase64Encoded": False,
    }


TEST_CONTEXT = cast(LambdaContext, object())


def make_list_event(raw_query: str = "") -> dict[str, Any]:
    event = make_event("")
    event["routeKey"] = "GET /students"
    event["rawPath"] = "/students"
    event["rawQueryString"] = raw_query
    event["requestContext"]["routeKey"] = "GET /students"
    event["requestContext"]["http"]["path"] = "/students"
    event["requestContext"]["authorizer"] = {"jwt": {"claims": {"sub": "subject-1"}}}
    return event


def test_list_students_parses_defaults_and_authenticated_subject() -> None:
    service = FakeStudentService(None)
    app = APIGatewayHttpResolver()
    register_student_routes(app, service)

    response = app.resolve(make_list_event(), TEST_CONTEXT)

    assert response["statusCode"] == 200
    assert service.list_call == {
        "cognito_sub": "subject-1",
        "limit": 20,
        "status": "ACTIVE",
        "name_prefix": None,
        "cursor": None,
    }


@pytest.mark.parametrize(
    "query",
    ["limit=0", "limit=101", "limit=1.5", "status=active", "unknown=x", "limit=1&limit=2"],
)
def test_list_students_rejects_invalid_or_duplicate_parameters(query: str) -> None:
    service = FakeStudentService(None)
    app = APIGatewayHttpResolver()
    register_student_routes(app, service)

    response = app.resolve(make_list_event(query), TEST_CONTEXT)

    assert response["statusCode"] == 400
    assert json.loads(response["body"])["error"] == "INVALID_REQUEST"


def test_get_student_returns_200_without_dynamodb_keys() -> None:
    service = FakeStudentService(
        {
            "PK": "STUDENT#student-123",
            "SK": "PROFILE",
            "studentId": "student-123",
            "fullName": "Maria Silva",
            "status": "ACTIVE",
        }
    )
    app = APIGatewayHttpResolver()
    register_student_routes(app, service)

    response = app.resolve(make_event("student-123"), TEST_CONTEXT)
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert service.requested_student_id == "student-123"
    assert body["studentId"] == "student-123"
    assert body["fullName"] == "Maria Silva"
    assert body["status"] == "ACTIVE"
    assert "PK" not in body
    assert "SK" not in body


def test_get_student_returns_404_when_student_does_not_exist() -> None:
    service = FakeStudentService(None)
    app = APIGatewayHttpResolver()
    register_student_routes(app, service)

    response = app.resolve(make_event("missing-student"), TEST_CONTEXT)
    body = json.loads(response["body"])

    assert response["statusCode"] == 404
    assert body == {
        "error": "STUDENT_NOT_FOUND",
        "message": "Student not found",
    }
