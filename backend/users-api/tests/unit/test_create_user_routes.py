import json
from typing import Any, cast

import pytest
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from users_api.app import lambda_handler
from users_api.errors import (
    AdminUserForbiddenError,
    IdempotencyKeyReusedError,
    InvalidAdminUserWriteRequestError,
    InvitationDeliveryFailedError,
    InvitationDeliveryUncertainError,
    OperationInProgressError,
    UserCreateReconciliationError,
    UserEmailAlreadyExistsError,
)
from users_api.routes import admin_users

KEY = "44444444-4444-4444-8444-444444444444"


class FakeContext:
    function_name = "UsersApi"
    memory_limit_in_mb = 512
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:UsersApi"
    aws_request_id = "lambda-request"
    log_group_name = "/aws/lambda/UsersApi"
    log_stream_name = "stream"

    def get_remaining_time_in_millis(self) -> int:
        return 30_000


class FakeCreateService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def create_user(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return {
            "userId": "user-1",
            "fullName": "Admin Example",
            "email": "admin@example.test",
            "role": "ADMIN",
            "status": "INVITED",
            "version": 1,
            "createdAt": "2026-09-14T12:00:00.000Z",
            "updatedAt": "2026-09-14T12:00:00.000Z",
        }


def event() -> dict[str, Any]:
    return {
        "version": "2.0",
        "routeKey": "POST /users",
        "rawPath": "/users",
        "rawQueryString": "",
        "headers": {"Idempotency-Key": KEY},
        "body": '{"fullName":"Admin Example","email":"admin@example.test","role":"ADMIN"}',
        "requestContext": {
            "http": {"method": "POST", "path": "/users"},
            "routeKey": "POST /users",
            "requestId": "request-1",
            "stage": "$default",
            "authorizer": {"jwt": {"claims": {"sub": "admin-sub", "token_use": "access"}}},
        },
        "isBase64Encoded": False,
    }


def resolve(service: FakeCreateService, request: dict[str, Any]) -> dict[str, Any]:
    resolver = APIGatewayHttpResolver()
    admin_users.register_admin_user_routes(resolver, create_service=service)
    return resolver.resolve(request, cast(LambdaContext, FakeContext()))


def test_create_route_returns_201_and_passes_only_required_context() -> None:
    service = FakeCreateService()
    response = resolve(service, event())

    assert response["statusCode"] == 201
    assert json.loads(response["body"])["status"] == "INVITED"
    assert service.calls == [
        {
            "cognito_sub": "admin-sub",
            "idempotency_key": KEY,
            "request_id": "request-1",
            "body": event()["body"],
        }
    ]


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(rawQueryString="x=1"),
        lambda value: value.update(isBase64Encoded=True),
        lambda value: value.update(body=None),
        lambda value: value.update(headers={}),
    ],
)
def test_create_route_rejects_invalid_envelope(change: Any) -> None:
    request = event()
    change(request)
    response = resolve(FakeCreateService(), request)
    assert response["statusCode"] == 400
    assert json.loads(response["body"])["error"] == "INVALID_REQUEST"


def test_create_route_rejects_non_access_identity() -> None:
    request = event()
    request["requestContext"]["authorizer"]["jwt"]["claims"]["token_use"] = "id"
    response = resolve(FakeCreateService(), request)
    assert response["statusCode"] == 401


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (InvalidAdminUserWriteRequestError(), 400, "INVALID_REQUEST"),
        (AdminUserForbiddenError(), 403, "FORBIDDEN"),
        (UserEmailAlreadyExistsError(), 409, "EMAIL_ALREADY_EXISTS"),
        (IdempotencyKeyReusedError(), 409, "IDEMPOTENCY_KEY_REUSED"),
        (OperationInProgressError(), 409, "OPERATION_IN_PROGRESS"),
        (InvitationDeliveryFailedError(), 503, "INVITATION_DELIVERY_FAILED"),
        (InvitationDeliveryUncertainError(), 503, "INVITATION_DELIVERY_UNCERTAIN"),
        (UserCreateReconciliationError(), 500, "INTERNAL_ERROR"),
        (RuntimeError("secret@example.test"), 500, "INTERNAL_ERROR"),
    ],
)
def test_create_route_maps_errors_without_provider_or_pii_leakage(
    error: Exception,
    status: int,
    code: str,
) -> None:
    response = resolve(FakeCreateService(error), event())
    assert response["statusCode"] == status
    assert json.loads(response["body"])["error"] == code
    assert "secret@example.test" not in response["body"]


def test_lambda_handler_knows_local_create_route(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeCreateService()
    monkeypatch.setattr(admin_users, "get_create_user_service", lambda: service)
    response = lambda_handler(event(), cast(LambdaContext, FakeContext()))
    assert response["statusCode"] == 201
