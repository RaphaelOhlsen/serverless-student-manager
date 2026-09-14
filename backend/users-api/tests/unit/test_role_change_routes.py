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
    LastActiveAdminConflictError,
    OperationInProgressError,
    UserRoleChangeReconciliationError,
    UserVersionConflictError,
)
from users_api.routes import admin_users
from users_api.validation import parse_role_change_body, validate_idempotency_key

KEY = "44444444-4444-4444-8444-444444444444"
PUBLIC_USER: dict[str, object] = {
    "userId": "user-1",
    "fullName": "Synthetic User",
    "email": "synthetic@example.test",
    "role": "ADMIN",
    "status": "ACTIVE",
    "version": 2,
    "createdAt": "2026-09-01T12:00:00.000Z",
    "updatedAt": "2026-09-14T12:00:00.000Z",
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
    def __init__(
        self,
        error: Exception | None = None,
        response: dict[str, object] | None = None,
    ) -> None:
        self.error = error
        self.response = response or PUBLIC_USER
        self.calls: list[dict[str, object]] = []

    def change_role(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        validate_idempotency_key(kwargs["idempotency_key"])
        body = kwargs["body"]
        if not isinstance(body, str):
            raise InvalidAdminUserWriteRequestError
        parse_role_change_body(body)
        return dict(self.response)


def event() -> dict[str, Any]:
    path = "/users/user-1/role-change"
    return {
        "version": "2.0",
        "routeKey": "POST /users/{userId}/role-change",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"Idempotency-Key": KEY},
        "body": '{"expectedVersion":1,"role":"ADMIN"}',
        "requestContext": {
            "http": {"method": "POST", "path": path},
            "routeKey": "POST /users/{userId}/role-change",
            "requestId": "request-1",
            "stage": "$default",
            "authorizer": {"jwt": {"claims": {"sub": "admin-sub", "token_use": "access"}}},
        },
        "isBase64Encoded": False,
    }


def resolve(service: FakeService, request: dict[str, Any]) -> dict[str, Any]:
    resolver = APIGatewayHttpResolver()
    admin_users.register_admin_user_routes(resolver, role_change_service=service)
    return resolver.resolve(request, cast(LambdaContext, FakeContext()))


def test_role_change_route_returns_public_user_and_passes_exact_context() -> None:
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
            "body": '{"expectedVersion":1,"role":"ADMIN"}',
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
        lambda value: value.update(body='{"expectedVersion":true,"role":"ADMIN"}'),
        lambda value: value.update(body='{"expectedVersion":1,"role":"OWNER"}'),
        lambda value: value.update(body='{"expectedVersion":1,"role":"ADMIN","extra":true}'),
    ],
)
def test_role_change_route_rejects_invalid_envelope_or_contract(change: Any) -> None:
    request = event()
    change(request)
    response = resolve(FakeService(), request)
    assert response["statusCode"] == 400
    assert json.loads(response["body"])["error"] == "INVALID_REQUEST"


def test_role_change_route_rejects_non_access_identity() -> None:
    request = event()
    request["requestContext"]["authorizer"]["jwt"]["claims"]["token_use"] = "id"
    response = resolve(FakeService(), request)
    assert response["statusCode"] == 401
    assert json.loads(response["body"])["error"] == "UNAUTHORIZED"


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (InvalidAdminUserWriteRequestError(), 400, "INVALID_REQUEST"),
        (AdminUserForbiddenError(), 403, "FORBIDDEN"),
        (AdminUserNotFoundError(), 404, "USER_NOT_FOUND"),
        (UserVersionConflictError(), 409, "USER_VERSION_CONFLICT"),
        (LastActiveAdminConflictError(), 409, "LAST_ACTIVE_ADMIN_CONFLICT"),
        (IdempotencyKeyReusedError(), 409, "IDEMPOTENCY_KEY_REUSED"),
        (OperationInProgressError(), 409, "OPERATION_IN_PROGRESS"),
        (UserRoleChangeReconciliationError(), 500, "INTERNAL_ERROR"),
        (RuntimeError("provider secret@example.test"), 500, "INTERNAL_ERROR"),
    ],
)
def test_role_change_route_maps_errors_without_internal_leakage(
    error: Exception, status: int, code: str
) -> None:
    response = resolve(FakeService(error), event())
    assert response["statusCode"] == status
    assert json.loads(response["body"])["error"] == code
    assert "secret@example.test" not in response["body"]
    assert "activeAdminCount" not in response["body"]
    assert "TransactionCanceled" not in response["body"]


@pytest.mark.parametrize("scenario", ["operator", "inactive-admin", "self", "self-noop"])
def test_forbidden_role_change_scenarios_are_sanitized(scenario: str) -> None:
    del scenario
    response = resolve(FakeService(AdminUserForbiddenError()), event())
    assert response["statusCode"] == 403
    assert json.loads(response["body"]) == {"error": "FORBIDDEN", "message": "Forbidden"}


def test_noop_and_completed_replay_return_original_public_result() -> None:
    original = {**PUBLIC_USER, "role": "OPERATOR", "version": 1}
    service = FakeService(response=original)
    first = resolve(service, event())
    replay = resolve(service, event())
    assert first["statusCode"] == replay["statusCode"] == 200
    assert json.loads(first["body"]) == json.loads(replay["body"]) == original

    service.response = {**PUBLIC_USER, "role": "ADMIN", "status": "INACTIVE", "version": 9}
    completed_replay = resolve(FakeService(response=original), event())
    assert json.loads(completed_replay["body"]) == original


def test_invalid_empty_path_is_not_registered_as_role_change() -> None:
    request = event()
    request["rawPath"] = "/users//role-change"
    request["requestContext"]["http"]["path"] = "/users//role-change"
    response = resolve(FakeService(), request)
    assert response["statusCode"] == 404


def test_lambda_handler_knows_local_role_change_route(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeService()
    monkeypatch.setattr(admin_users, "get_role_change_service", lambda: service)
    response = lambda_handler(event(), cast(LambdaContext, FakeContext()))
    assert response["statusCode"] == 200


def test_role_change_dependency_wiring_creates_no_cognito_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_services: list[str] = []

    class Resource:
        @staticmethod
        def Table(name: str) -> object:
            assert name == "idempotency"
            return object()

    def client(service_name: str) -> object:
        client_services.append(service_name)
        return object()

    monkeypatch.setattr(
        boto3,
        "client",
        client,
    )
    monkeypatch.setattr(boto3, "resource", lambda service_name: Resource())
    monkeypatch.setattr(dependencies, "get_idempotency_table_name", lambda: "idempotency")
    monkeypatch.setattr(dependencies, "get_users_table_name", lambda: "users")
    monkeypatch.setattr(dependencies, "get_audit_table_name", lambda: "audit")
    monkeypatch.setattr(dependencies, "get_environment", lambda: "dev")
    monkeypatch.setattr(dependencies, "get_audit_retention_days", lambda: 365)
    dependencies.get_role_change_service.cache_clear()
    try:
        assert dependencies.get_role_change_service() is not None
    finally:
        dependencies.get_role_change_service.cache_clear()
    assert client_services == ["dynamodb"]
