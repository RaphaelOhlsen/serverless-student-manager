import json
from typing import Any, cast

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
