import json
from typing import Any, cast

import pytest
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from students_api.errors import (
    ForbiddenError,
    IdempotencyKeyReusedError,
    OperationInProgressError,
    StudentNotFoundError,
    StudentVersionConflictError,
)
from students_api.routes.students import register_student_routes

CONTEXT = cast(LambdaContext, object())


class LifecycleService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def deactivate_student(self, **kwargs: Any) -> dict[str, object]:
        return self._result("deactivate", kwargs, "INACTIVE")

    def reactivate_student(self, **kwargs: Any) -> dict[str, object]:
        return self._result("reactivate", kwargs, "ACTIVE")

    def _result(self, operation: str, kwargs: dict[str, Any], status: str) -> dict[str, object]:
        self.calls.append((operation, kwargs))
        if self.error is not None:
            raise self.error
        return {
            "studentId": kwargs["student_id"],
            "registrationNumber": "MAT-1",
            "fullName": "Aluno Teste",
            "studentEmail": "student@example.invalid",
            "phone": "+12025550123",
            "birthDate": "2000-01-01",
            "status": status,
            "version": 4,
            "createdAt": "2020-01-01T00:00:00.000Z",
            "updatedAt": "2026-09-11T12:00:00.000Z",
        }


def event(operation: str, body: str | None = None) -> dict[str, Any]:
    noun = "deactivation" if operation == "deactivate" else "reactivation"
    payload = (
        {"expectedVersion": 3, "reason": "Motivo sintético seguro"}
        if operation == "deactivate"
        else {"expectedVersion": 3}
    )
    return {
        "version": "2.0",
        "routeKey": f"POST /students/{{studentId}}/{noun}",
        "rawPath": f"/students/student-1/{noun}",
        "rawQueryString": "",
        "headers": {
            "content-type": "application/json",
            "idempotency-key": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        },
        "body": body if body is not None else json.dumps(payload),
        "requestContext": {
            "http": {"method": "POST", "path": f"/students/student-1/{noun}"},
            "requestId": "request-1",
            "routeKey": f"POST /students/{{studentId}}/{noun}",
            "stage": "$default",
            "authorizer": {"jwt": {"claims": {"sub": "subject-1", "token_use": "access"}}},
        },
        "isBase64Encoded": False,
    }


def resolve(
    service: LifecycleService, operation: str, request: dict[str, Any] | None = None
) -> dict[str, Any]:
    app = APIGatewayHttpResolver()
    register_student_routes(app, lifecycle_service=service)
    return app.resolve(request or event(operation), CONTEXT)


@pytest.mark.parametrize("operation", ["deactivate", "reactivate"])
def test_lifecycle_route_returns_public_student_and_delegates(operation: str) -> None:
    service = LifecycleService()
    response = resolve(service, operation)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert set(body) == {
        "studentId",
        "registrationNumber",
        "fullName",
        "studentEmail",
        "phone",
        "birthDate",
        "status",
        "version",
        "createdAt",
        "updatedAt",
    }
    assert "reason" not in body
    assert service.calls[0][0] == operation
    call = service.calls[0][1]
    assert call["cognito_sub"] == "subject-1"
    assert call["student_id"] == "student-1"
    assert call["request_id"] == "request-1"
    assert call["idempotency_key"] == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert call["request"].expected_version == 3
    if operation == "deactivate":
        assert call["request"].reason == "Motivo sintético seguro"


@pytest.mark.parametrize("operation", ["deactivate", "reactivate"])
@pytest.mark.parametrize(
    "mutation",
    [
        lambda request: request["headers"].pop("content-type"),
        lambda request: request["headers"].update({"content-type": "text/plain"}),
        lambda request: request["headers"].pop("idempotency-key"),
        lambda request: request["headers"].update({"idempotency-key": "not-a-uuid"}),
        lambda request: request.update({"rawQueryString": "unexpected=true"}),
        lambda request: request.update({"isBase64Encoded": True}),
        lambda request: request.update({"body": "{"}),
        lambda request: request.update({"body": '{"expectedVersion":3,"expectedVersion":4}'}),
        lambda request: request.update({"body": '{"expectedVersion":true}'}),
    ],
)
def test_lifecycle_routes_reject_invalid_http_and_body(operation: str, mutation: Any) -> None:
    request = event(operation)
    mutation(request)
    response = resolve(LifecycleService(), operation, request)
    assert response["statusCode"] == 400
    assert json.loads(response["body"])["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize("operation", ["deactivate", "reactivate"])
@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (ForbiddenError(), 403, "FORBIDDEN"),
        (StudentNotFoundError(), 404, "STUDENT_NOT_FOUND"),
        (StudentVersionConflictError(), 409, "STUDENT_VERSION_CONFLICT"),
        (IdempotencyKeyReusedError(), 409, "IDEMPOTENCY_KEY_REUSED"),
        (OperationInProgressError(), 409, "OPERATION_IN_PROGRESS"),
        (RuntimeError("private lifecycle detail"), 500, "INTERNAL_ERROR"),
    ],
)
def test_lifecycle_routes_map_errors_without_leaking_details(
    operation: str, error: Exception, status: int, code: str
) -> None:
    response = resolve(LifecycleService(error), operation)
    assert response["statusCode"] == status
    body = json.loads(response["body"])
    assert body["code"] == code
    assert body["correlationId"] == "request-1"
    assert "private lifecycle detail" not in response["body"]
