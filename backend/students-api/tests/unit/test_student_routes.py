import json
from typing import Any, cast

import pytest
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from students_api.errors import (
    ForbiddenError,
    IdempotencyKeyReusedError,
    OperationInProgressError,
    RegistrationNumberAlreadyExistsError,
    StudentEmailAlreadyExistsError,
    StudentNotFoundError,
    StudentUniquenessConflictError,
)
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


class FakeCreateStudentService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.call: dict[str, Any] | None = None

    def create_student(self, **kwargs: Any) -> dict[str, object]:
        self.call = kwargs
        if self.error is not None:
            raise self.error
        student = kwargs["student"]
        return {
            "studentId": "11111111-1111-4111-8111-111111111111",
            "registrationNumber": student.registration_number,
            "fullName": student.full_name,
            "studentEmail": student.student_email,
            "phone": student.phone,
            "birthDate": student.birth_date,
            "status": "ACTIVE",
            "version": 1,
            "createdAt": "2026-09-04T12:30:00.000Z",
            "updatedAt": "2026-09-04T12:30:00.000Z",
        }


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


def make_create_event() -> dict[str, Any]:
    event = make_event("")
    event["routeKey"] = "POST /students"
    event["rawPath"] = "/students"
    event["headers"] = {
        "content-type": "application/json",
        "idempotency-key": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    }
    event["body"] = json.dumps(
        {
            "fullName": "Maria da Silva",
            "registrationNumber": "MAT-0001",
            "studentEmail": "maria@example.com",
            "phone": "+5527999999999",
            "birthDate": "2010-05-21",
        }
    )
    event["requestContext"]["routeKey"] = "POST /students"
    event["requestContext"]["http"]["method"] = "POST"
    event["requestContext"]["http"]["path"] = "/students"
    event["requestContext"]["authorizer"] = {
        "jwt": {"claims": {"sub": "subject-1", "token_use": "access"}}
    }
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


def test_create_student_returns_exact_201_contract() -> None:
    create_service = FakeCreateStudentService()
    app = APIGatewayHttpResolver()
    register_student_routes(app, FakeStudentService(None), create_service)

    response = app.resolve(make_create_event(), TEST_CONTEXT)
    body = json.loads(response["body"])

    assert response["statusCode"] == 201
    assert body == {
        "studentId": "11111111-1111-4111-8111-111111111111",
        "registrationNumber": "MAT-0001",
        "fullName": "Maria da Silva",
        "studentEmail": "maria@example.com",
        "phone": "+5527999999999",
        "birthDate": "2010-05-21",
        "status": "ACTIVE",
        "version": 1,
        "createdAt": "2026-09-04T12:30:00.000Z",
        "updatedAt": "2026-09-04T12:30:00.000Z",
    }
    assert type(body["version"]) is int
    assert create_service.call is not None
    assert create_service.call["cognito_sub"] == "subject-1"
    assert create_service.call["idempotency_key"] == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert create_service.call["request_id"] == "unit-test-request"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda event: event["headers"].pop("content-type"),
        lambda event: event["headers"].update({"content-type": "text/plain"}),
        lambda event: event["headers"].pop("idempotency-key"),
        lambda event: event["headers"].update({"idempotency-key": "not-a-uuid"}),
        lambda event: event.update({"rawQueryString": "unexpected=true"}),
        lambda event: event.update({"body": "not-json"}),
    ],
)
def test_create_student_rejects_invalid_http_request(mutation: Any) -> None:
    event = make_create_event()
    mutation(event)
    app = APIGatewayHttpResolver()
    register_student_routes(app, FakeStudentService(None), FakeCreateStudentService())

    response = app.resolve(event, TEST_CONTEXT)

    assert response["statusCode"] == 400
    assert json.loads(response["body"]) == {
        "code": "INVALID_REQUEST",
        "message": "Invalid student creation request",
        "correlationId": "unit-test-request",
        "details": [],
    }


@pytest.mark.parametrize(
    "error,status,code",
    [
        (ForbiddenError(), 403, "FORBIDDEN"),
        (RegistrationNumberAlreadyExistsError(), 409, "REGISTRATION_NUMBER_ALREADY_EXISTS"),
        (StudentEmailAlreadyExistsError(), 409, "STUDENT_EMAIL_ALREADY_EXISTS"),
        (StudentUniquenessConflictError(), 409, "STUDENT_UNIQUENESS_CONFLICT"),
        (IdempotencyKeyReusedError(), 409, "IDEMPOTENCY_KEY_REUSED"),
        (OperationInProgressError(), 409, "OPERATION_IN_PROGRESS"),
        (RuntimeError("private storage detail"), 500, "INTERNAL_ERROR"),
    ],
)
def test_create_student_returns_safe_domain_and_internal_errors(
    error: Exception, status: int, code: str
) -> None:
    app = APIGatewayHttpResolver()
    register_student_routes(app, FakeStudentService(None), FakeCreateStudentService(error))

    response = app.resolve(make_create_event(), TEST_CONTEXT)
    body = json.loads(response["body"])

    assert response["statusCode"] == status
    assert body["code"] == code
    assert body["correlationId"] == "unit-test-request"
    assert "private storage detail" not in response["body"]
