import json
from pathlib import Path
from typing import Any, cast

import pytest
from aws_lambda_powertools.utilities.typing import LambdaContext
from students_api.app import lambda_handler
from students_api.errors import StudentNotFoundError
from students_api.routes import students as student_routes

EVENTS_DIR = Path(__file__).resolve().parents[1] / "events"


class FakeLambdaContext:
    function_name = "StudentsApi"
    memory_limit_in_mb = 512
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:StudentsApi"
    aws_request_id = "handler-test-request"
    log_group_name = "/aws/lambda/StudentsApi"
    log_stream_name = "handler-test"

    def get_remaining_time_in_millis(self) -> int:
        return 30_000


class FakeStudentService:
    def __init__(self, student: dict[str, Any] | None) -> None:
        self.student = student

    def get_student(self, student_id: str) -> dict[str, Any]:
        if self.student is None:
            raise StudentNotFoundError

        return self.student


def load_event() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((EVENTS_DIR / "get-student.json").read_text(encoding="utf-8")),
    )


def test_lambda_handler_get_student_returns_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeStudentService(
        {
            "PK": "STUDENT#student-123",
            "SK": "PROFILE",
            "studentId": "student-123",
            "registrationNumber": "20260001",
            "fullName": "Maria Silva",
            "studentEmail": "maria@example.com",
            "phone": "+5527999999999",
            "birthDate": "2000-05-10",
            "status": "ACTIVE",
            "version": 1,
        }
    )

    monkeypatch.setattr(
        student_routes,
        "get_student_service",
        lambda: service,
    )

    response = lambda_handler(
        load_event(),
        cast(LambdaContext, FakeLambdaContext()),
    )

    assert response["statusCode"] == 200

    body = json.loads(cast(str, response["body"]))

    assert body["studentId"] == "student-123"
    assert body["fullName"] == "Maria Silva"
    assert body["status"] == "ACTIVE"
    assert "PK" not in body
    assert "SK" not in body


def test_lambda_handler_get_student_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeStudentService(None)

    monkeypatch.setattr(
        student_routes,
        "get_student_service",
        lambda: service,
    )

    event = load_event()
    event["rawPath"] = "/students/missing-student"
    event["requestContext"]["http"]["path"] = "/students/missing-student"

    response = lambda_handler(
        event,
        cast(LambdaContext, FakeLambdaContext()),
    )

    assert response["statusCode"] == 404

    body = json.loads(cast(str, response["body"]))

    assert body == {
        "error": "STUDENT_NOT_FOUND",
        "message": "Student not found",
    }
