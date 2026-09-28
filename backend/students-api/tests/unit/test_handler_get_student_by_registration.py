import json
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
from aws_lambda_powertools.utilities.typing import LambdaContext
from students_api.app import lambda_handler
from students_api.routes import students as student_routes

EVENTS_DIR = Path(__file__).resolve().parents[1] / "events"


class FakeLambdaContext:
    function_name = "StudentsApi"
    memory_limit_in_mb = 512
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:StudentsApi"
    aws_request_id = "handler-registration-test-request"
    log_group_name = "/aws/lambda/StudentsApi"
    log_stream_name = "handler-registration-test"

    def get_remaining_time_in_millis(self) -> int:
        return 30_000


class FakeStudentService:
    def __init__(self) -> None:
        self.detail_call: dict[str, str | None] | None = None
        self.registration_call: dict[str, str | None] | None = None

    def get_student(
        self,
        *,
        cognito_sub: str | None,
        student_id: str,
    ) -> dict[str, Any]:
        self.detail_call = {"cognito_sub": cognito_sub, "student_id": student_id}
        raise AssertionError("registration route dispatched through student detail")

    def get_student_by_registration(
        self,
        *,
        cognito_sub: str | None,
        registration_number: str,
    ) -> dict[str, Any]:
        self.registration_call = {
            "cognito_sub": cognito_sub,
            "registration_number": registration_number,
        }
        return {
            "studentId": "student-123",
            "registrationNumber": "AB-1234",
            "fullName": "Maria Silva",
            "studentEmail": "maria@example.com",
            "phone": "+5527999999999",
            "birthDate": "2000-05-10",
            "status": "ACTIVE",
            "version": Decimal("2"),
            "createdAt": "2026-09-10T12:07:54.388Z",
            "updatedAt": "2026-09-11T16:36:38.541Z",
        }


def load_event() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((EVENTS_DIR / "get-student-by-registration.json").read_text(encoding="utf-8")),
    )


def test_lambda_handler_dispatches_registration_lookup_without_detail_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeStudentService()
    monkeypatch.setattr(student_routes, "get_student_service", lambda: service)

    response = lambda_handler(load_event(), cast(LambdaContext, FakeLambdaContext()))

    assert response["statusCode"] == 200
    assert service.registration_call == {
        "cognito_sub": "subject-1",
        "registration_number": "ab-1234",
    }
    assert service.detail_call is None
    assert json.loads(cast(str, response["body"]))["registrationNumber"] == "AB-1234"
