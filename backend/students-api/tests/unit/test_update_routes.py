import json
from typing import Any, cast

import pytest
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from students_api.errors import (
    ForbiddenError,
    IdempotencyKeyReusedError,
    OperationInProgressError,
    StudentEmailAlreadyExistsError,
    StudentNotFoundError,
    StudentVersionConflictError,
)
from students_api.routes.students import register_student_routes

CONTEXT = cast(LambdaContext, object())


class UpdateService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.call: dict[str, Any] | None = None

    def update_student(self, **kwargs: Any) -> dict[str, object]:
        self.call = kwargs
        if self.error is not None:
            raise self.error
        patch = kwargs["patch"]
        return {
            "studentId": kwargs["student_id"],
            "registrationNumber": "MAT-1",
            "fullName": patch.full_name or "Maria Silva",
            "studentEmail": "maria@example.com",
            "phone": "+5511999999999",
            "birthDate": "2000-01-01",
            "status": "ACTIVE",
            "version": 4,
            "createdAt": "2020-01-01T00:00:00.000Z",
            "updatedAt": "2026-09-11T12:00:00.000Z",
        }


def event(body: str | None = None) -> dict[str, Any]:
    return {
        "version": "2.0",
        "routeKey": "PATCH /students/{studentId}",
        "rawPath": "/students/student-1",
        "rawQueryString": "",
        "headers": {
            "content-type": "application/json",
            "idempotency-key": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        },
        "body": body or json.dumps({"expectedVersion": 3, "fullName": "Novo Nome"}),
        "requestContext": {
            "http": {"method": "PATCH", "path": "/students/student-1"},
            "requestId": "request-1",
            "routeKey": "PATCH /students/{studentId}",
            "stage": "$default",
            "authorizer": {"jwt": {"claims": {"sub": "subject-1", "token_use": "access"}}},
        },
        "isBase64Encoded": False,
    }


def resolve(service: UpdateService, request: dict[str, Any] | None = None) -> dict[str, Any]:
    app = APIGatewayHttpResolver()
    register_student_routes(app, update_service=service)
    return app.resolve(request or event(), CONTEXT)


def test_patch_returns_200_and_calls_update_service() -> None:
    service = UpdateService()

    response = resolve(service)

    assert response["statusCode"] == 200
    assert json.loads(response["body"])["version"] == 4
    assert service.call is not None
    assert service.call["cognito_sub"] == "subject-1"
    assert service.call["student_id"] == "student-1"
    assert service.call["request_id"] == "request-1"
    assert service.call["patch"].expected_version == 3
    assert service.call["patch"].full_name == "Novo Nome"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda request: request["headers"].pop("content-type"),
        lambda request: request["headers"].update({"content-type": "text/plain"}),
        lambda request: request["headers"].pop("idempotency-key"),
        lambda request: request["headers"].update({"idempotency-key": "not-a-uuid"}),
        lambda request: request.update({"rawQueryString": "unexpected=true"}),
        lambda request: request.update(
            {"body": '{"expectedVersion":3,"fullName":"A","fullName":"B"}'}
        ),
        lambda request: request.update(
            {"body": '{"expectedVersion":true,"phone":"+5511999999999"}'}
        ),
    ],
)
def test_patch_rejects_invalid_http_or_json_request(mutation: Any) -> None:
    request = event()
    mutation(request)

    response = resolve(UpdateService(), request)

    assert response["statusCode"] == 400
    assert json.loads(response["body"])["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (ForbiddenError(), 403, "FORBIDDEN"),
        (StudentNotFoundError(), 404, "STUDENT_NOT_FOUND"),
        (StudentVersionConflictError(), 409, "STUDENT_VERSION_CONFLICT"),
        (StudentEmailAlreadyExistsError(), 409, "STUDENT_EMAIL_ALREADY_EXISTS"),
        (IdempotencyKeyReusedError(), 409, "IDEMPOTENCY_KEY_REUSED"),
        (OperationInProgressError(), 409, "OPERATION_IN_PROGRESS"),
        (RuntimeError("private persistence detail"), 500, "INTERNAL_ERROR"),
    ],
)
def test_patch_maps_domain_errors_without_leaking_details(
    error: Exception, status: int, code: str
) -> None:
    response = resolve(UpdateService(error))

    assert response["statusCode"] == status
    body = json.loads(response["body"])
    assert body["code"] == code
    assert body["correlationId"] == "request-1"
    assert "private persistence detail" not in response["body"]
