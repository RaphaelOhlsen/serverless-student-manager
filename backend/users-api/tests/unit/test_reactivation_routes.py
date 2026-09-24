import json
from typing import Any, cast

import boto3  # type: ignore[import-untyped]
import pytest
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from users_api import dependencies
from users_api.app import lambda_handler
from users_api.errors import (
    AdminUserForbiddenError,
    AdminUserNotFoundError,
    IdempotencyKeyReusedError,
    InvalidAdminUserWriteRequestError,
    OperationInProgressError,
    UserReactivationReconciliationError,
    UserStateConflictError,
    UserVersionConflictError,
)
from users_api.routes import admin_users
from users_api.validation import parse_reactivation_body, validate_idempotency_key

KEY = "55555555-5555-4555-8555-555555555555"
PUBLIC_USER: dict[str, object] = {
    "userId": "user-1",
    "fullName": "Synthetic User",
    "email": "synthetic@example.test",
    "role": "OPERATOR",
    "status": "ACTIVE",
    "version": 2,
    "createdAt": "2026-09-01T12:00:00.000Z",
    "updatedAt": "2026-09-24T12:00:00.000Z",
}


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

    def reactivate_user(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        if self.error is not None:
            raise self.error
        validate_idempotency_key(kwargs["idempotency_key"])
        body = kwargs["body"]
        if not isinstance(body, str):
            raise InvalidAdminUserWriteRequestError
        parse_reactivation_body(body)
        return dict(PUBLIC_USER)


def event() -> dict[str, Any]:
    path = "/users/user-1/reactivation"
    return {
        "version": "2.0",
        "routeKey": "POST /users/{userId}/reactivation",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"Idempotency-Key": KEY},
        "body": '{"expectedVersion":1}',
        "requestContext": {
            "http": {"method": "POST", "path": path},
            "routeKey": "POST /users/{userId}/reactivation",
            "requestId": "request-1",
            "stage": "$default",
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "admin-sub",
                        "token_use": "access",
                        "role": "OPERATOR",
                        "status": "INACTIVE",
                    }
                }
            },
        },
        "isBase64Encoded": False,
    }


def resolve(service: FakeService, request: dict[str, Any]) -> dict[str, Any]:
    resolver = APIGatewayHttpResolver()
    admin_users.register_admin_user_routes(resolver, reactivation_service=service)
    return resolver.resolve(request, cast(LambdaContext, FakeContext()))


def test_reactivation_route_returns_public_user_and_passes_exact_context() -> None:
    service = FakeService()

    response = resolve(service, event())

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == PUBLIC_USER
    assert set(json.loads(response["body"])) == {
        "userId",
        "fullName",
        "email",
        "role",
        "status",
        "version",
        "createdAt",
        "updatedAt",
    }
    assert "authVersion" not in response["body"]
    assert "cognitoSub" not in response["body"]
    assert service.calls == [
        {
            "cognito_sub": "admin-sub",
            "user_id": "user-1",
            "idempotency_key": KEY,
            "request_id": "request-1",
            "body": '{"expectedVersion":1}',
        }
    ]


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(rawQueryString="x=1"),
        lambda value: value.update(isBase64Encoded=True),
        lambda value: value.update(body=None),
        lambda value: value.update(headers={}),
        lambda value: value.update(headers={"Idempotency-Key": "not-a-uuid"}),
        lambda value: value.update(body='{"expectedVersion":true}'),
        lambda value: value.update(body='{"expectedVersion":1,"extra":true}'),
    ],
)
def test_reactivation_route_rejects_invalid_envelope_or_contract(change: Any) -> None:
    request = event()
    change(request)

    response = resolve(FakeService(), request)

    assert response["statusCode"] == 400
    assert json.loads(response["body"]) == {
        "error": "INVALID_REQUEST",
        "message": "Invalid user reactivation request",
    }


def test_reactivation_route_rejects_invalid_access_identity() -> None:
    request = event()
    request["requestContext"]["authorizer"]["jwt"]["claims"] = {
        "token_use": "id",
        "sub": "admin-sub",
    }

    response = resolve(FakeService(), request)

    assert response["statusCode"] == 401
    assert json.loads(response["body"]) == {
        "error": "UNAUTHORIZED",
        "message": "Unauthorized",
    }


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
        (
            UserReactivationReconciliationError("AdminEnableUser secret@example.test"),
            503,
            "USER_REACTIVATION_RECONCILIATION_REQUIRED",
        ),
        (
            RuntimeError("TransactionCanceled activeAdminCount secret@example.test"),
            500,
            "INTERNAL_ERROR",
        ),
    ],
)
def test_reactivation_route_maps_errors_without_internal_leakage(
    error: Exception,
    status: int,
    code: str,
) -> None:
    response = resolve(FakeService(error), event())

    assert response["statusCode"] == status
    assert json.loads(response["body"])["error"] == code
    assert "secret@example.test" not in response["body"]
    assert "AdminEnableUser" not in response["body"]
    assert "activeAdminCount" not in response["body"]
    assert "TransactionCanceled" not in response["body"]


def test_lambda_handler_knows_local_reactivation_route(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeService()
    monkeypatch.setattr(admin_users, "get_reactivation_service", lambda: service)

    response = lambda_handler(event(), cast(LambdaContext, FakeContext()))

    assert response["statusCode"] == 200


def test_reactivation_dependency_wiring_creates_dynamodb_and_cognito_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_services: list[str] = []
    resource_services: list[str] = []

    class Resource:
        @staticmethod
        def Table(name: str) -> object:
            assert name == "idempotency"
            return object()

    def client(service_name: str) -> object:
        client_services.append(service_name)
        return object()

    def resource(service_name: str) -> Resource:
        resource_services.append(service_name)
        return Resource()

    monkeypatch.setattr(boto3, "client", client)
    monkeypatch.setattr(boto3, "resource", resource)
    monkeypatch.setattr(dependencies, "get_idempotency_table_name", lambda: "idempotency")
    monkeypatch.setattr(dependencies, "get_users_table_name", lambda: "users")
    monkeypatch.setattr(dependencies, "get_audit_table_name", lambda: "audit")
    monkeypatch.setattr(dependencies, "get_user_pool_id", lambda: "user-pool")
    monkeypatch.setattr(dependencies, "get_environment", lambda: "dev")
    monkeypatch.setattr(dependencies, "get_audit_retention_days", lambda: 365)
    dependencies.get_reactivation_service.cache_clear()
    try:
        assert dependencies.get_reactivation_service() is not None
    finally:
        dependencies.get_reactivation_service.cache_clear()

    assert client_services == ["dynamodb", "cognito-idp"]
    assert resource_services == ["dynamodb"]
