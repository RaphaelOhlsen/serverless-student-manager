import json
from typing import Any, cast

import pytest
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from users_api.app import lambda_handler
from users_api.errors import ActivationConflictError, ActivationForbiddenError
from users_api.routes import activation

KEY = "22222222-2222-4222-8222-222222222222"


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

    def activate_current_user(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return {"userId": "user-1", "role": "ADMIN", "status": "ACTIVE", "authVersion": 1}


def event() -> dict[str, Any]:
    return {
        "version": "2.0",
        "routeKey": "POST /users/me/activation",
        "rawPath": "/users/me/activation",
        "rawQueryString": "",
        "headers": {"idempotency-key": KEY},
        "requestContext": {
            "accountId": "123456789012",
            "apiId": "api",
            "domainName": "api.example",
            "domainPrefix": "api",
            "http": {
                "method": "POST",
                "path": "/users/me/activation",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "pytest",
            },
            "requestId": "request-1",
            "routeKey": "POST /users/me/activation",
            "stage": "$default",
            "time": "02/Sep/2026:12:00:00 +0000",
            "timeEpoch": 1788350400000,
            "authorizer": {
                "jwt": {
                    "claims": {"sub": "sub-1", "token_use": "access"},
                    "scopes": [],
                }
            },
        },
        "isBase64Encoded": False,
    }


def resolve(service: FakeService, request: dict[str, Any]) -> dict[str, Any]:
    resolver = APIGatewayHttpResolver()
    activation.register_activation_routes(resolver, service)
    return resolver.resolve(request, cast(LambdaContext, FakeContext()))


def test_successful_route_uses_only_authorizer_identity() -> None:
    service = FakeService()
    response = resolve(service, event())
    assert response["statusCode"] == 200
    assert json.loads(response["body"])["status"] == "ACTIVE"
    assert service.calls == [
        {"cognito_sub": "sub-1", "idempotency_key": KEY, "request_id": "request-1"}
    ]


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(rawQueryString="unexpected=true"),
        lambda value: value.update(body="{}"),
        lambda value: value.update(headers={}),
        lambda value: value.update(headers={"Idempotency-Key": "NOT-A-UUID"}),
    ],
)
def test_invalid_request_returns_safe_400(change: Any) -> None:
    request = event()
    change(request)
    response = resolve(FakeService(), request)
    assert response["statusCode"] == 400
    assert json.loads(response["body"]) == {
        "error": "INVALID_REQUEST",
        "message": "Invalid activation request",
    }


@pytest.mark.parametrize(
    "claims",
    [{"sub": "sub-1", "token_use": "id"}, {"token_use": "access"}],
)
def test_invalid_authorizer_identity_returns_401(claims: dict[str, str]) -> None:
    request = event()
    request["requestContext"]["authorizer"]["jwt"]["claims"] = claims
    assert resolve(FakeService(), request)["statusCode"] == 401


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (ActivationForbiddenError(), 403),
        (ActivationConflictError(), 409),
        (RuntimeError("sensitive"), 500),
    ],
)
def test_domain_and_unexpected_errors_are_sanitized(error: Exception, status: int) -> None:
    response = resolve(FakeService(error), event())
    assert response["statusCode"] == status
    assert "sensitive" not in response["body"]


def test_lambda_handler_routes_activation(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeService()
    monkeypatch.setattr(activation, "get_activation_service", lambda: service)
    response = lambda_handler(event(), cast(LambdaContext, FakeContext()))
    assert response["statusCode"] == 200
