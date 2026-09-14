import json
from typing import Any, cast

import pytest
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from users_api.app import lambda_handler
from users_api.errors import (
    AdminUserForbiddenError,
    AdminUserNotFoundError,
    IdempotencyKeyReusedError,
    InvalidAdminUserWriteRequestError,
    InvitationDeliveryFailedError,
    InvitationDeliveryUncertainError,
    OperationInProgressError,
    UserInvitationReconciliationError,
    UserStateConflictError,
    UserVersionConflictError,
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


class FakeService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def resend_invitation(self, **kwargs: object) -> None:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error


def event() -> dict[str, Any]:
    path = "/users/user-1/invitation/resend"
    return {
        "version": "2.0",
        "routeKey": "POST /users/{userId}/invitation/resend",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"Idempotency-Key": KEY},
        "body": '{"expectedVersion":3}',
        "requestContext": {
            "http": {"method": "POST", "path": path},
            "routeKey": "POST /users/{userId}/invitation/resend",
            "requestId": "request-1",
            "stage": "$default",
            "authorizer": {"jwt": {"claims": {"sub": "admin-sub", "token_use": "access"}}},
        },
        "isBase64Encoded": False,
    }


def resolve(service: FakeService, request: dict[str, Any]) -> dict[str, Any]:
    resolver = APIGatewayHttpResolver()
    admin_users.register_admin_user_routes(resolver, resend_service=service)
    return resolver.resolve(request, cast(LambdaContext, FakeContext()))


def test_resend_route_returns_empty_204_and_passes_context() -> None:
    service = FakeService()
    response = resolve(service, event())

    assert response["statusCode"] == 204
    assert response["body"] is None
    assert service.calls == [
        {
            "cognito_sub": "admin-sub",
            "user_id": "user-1",
            "idempotency_key": KEY,
            "request_id": "request-1",
            "body": '{"expectedVersion":3}',
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
def test_resend_route_rejects_invalid_envelope(change: Any) -> None:
    request = event()
    change(request)
    response = resolve(FakeService(), request)
    assert response["statusCode"] == 400


def test_resend_route_rejects_non_access_identity() -> None:
    request = event()
    request["requestContext"]["authorizer"]["jwt"]["claims"]["token_use"] = "id"
    assert resolve(FakeService(), request)["statusCode"] == 401


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (InvalidAdminUserWriteRequestError(), 400, "INVALID_REQUEST"),
        (AdminUserForbiddenError(), 403, "FORBIDDEN"),
        (AdminUserNotFoundError(), 404, "USER_NOT_FOUND"),
        (UserVersionConflictError(), 409, "USER_VERSION_CONFLICT"),
        (UserStateConflictError(), 409, "USER_STATE_CONFLICT"),
        (IdempotencyKeyReusedError(), 409, "IDEMPOTENCY_KEY_REUSED"),
        (OperationInProgressError(), 409, "OPERATION_IN_PROGRESS"),
        (InvitationDeliveryFailedError(), 503, "INVITATION_DELIVERY_FAILED"),
        (InvitationDeliveryUncertainError(), 503, "INVITATION_DELIVERY_UNCERTAIN"),
        (UserInvitationReconciliationError(), 500, "INTERNAL_ERROR"),
        (RuntimeError("secret@example.test"), 500, "INTERNAL_ERROR"),
    ],
)
def test_resend_route_maps_errors_without_leakage(
    error: Exception,
    status: int,
    code: str,
) -> None:
    response = resolve(FakeService(error), event())
    assert response["statusCode"] == status
    assert json.loads(response["body"])["error"] == code
    assert "secret@example.test" not in response["body"]


def test_lambda_handler_knows_local_resend_route(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeService()
    monkeypatch.setattr(admin_users, "get_resend_invitation_service", lambda: service)
    response = lambda_handler(event(), cast(LambdaContext, FakeContext()))
    assert response["statusCode"] == 204
