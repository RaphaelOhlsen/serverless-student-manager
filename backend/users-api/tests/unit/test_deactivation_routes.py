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
    UserDeactivationReconciliationError,
    UserStateConflictError,
    UserVersionConflictError,
)
from users_api.routes import admin_users
from users_api.validation import parse_deactivation_body, validate_idempotency_key

KEY = "55555555-5555-4555-8555-555555555555"
PUBLIC_USER: dict[str, object] = {
    "userId": "user-1",
    "fullName": "Synthetic User",
    "email": "synthetic@example.test",
    "role": "OPERATOR",
    "status": "INACTIVE",
    "version": 2,
    "createdAt": "2026-09-01T12:00:00.000Z",
    "updatedAt": "2026-09-22T12:00:00.000Z",
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

    def deactivate_user(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        validate_idempotency_key(kwargs["idempotency_key"])
        body = kwargs["body"]
        if not isinstance(body, str):
            raise InvalidAdminUserWriteRequestError
        parse_deactivation_body(body)
        return dict(self.response)


def event() -> dict[str, Any]:
    path = "/users/user-1/deactivation"
    return {
        "version": "2.0",
        "routeKey": "POST /users/{userId}/deactivation",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"Idempotency-Key": KEY},
        "body": '{"expectedVersion":1}',
        "requestContext": {
            "http": {"method": "POST", "path": path},
            "routeKey": "POST /users/{userId}/deactivation",
            "requestId": "request-1",
            "stage": "$default",
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "admin-sub",
                        "token_use": "access",
                        "role": "OPERATOR",
                        "status": "INACTIVE",
                        "cognito:groups": ["operators"],
                    }
                }
            },
        },
        "isBase64Encoded": False,
    }


def resolve(service: FakeService, request: dict[str, Any]) -> dict[str, Any]:
    resolver = APIGatewayHttpResolver()
    admin_users.register_admin_user_routes(resolver, deactivation_service=service)
    return resolver.resolve(request, cast(LambdaContext, FakeContext()))


def test_deactivation_route_returns_terminal_public_user_and_passes_exact_context() -> None:
    service = FakeService()
    response = resolve(service, event())

    assert response["statusCode"] == 200
    assert response["headers"]["Content-Type"] == "application/json"
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


def test_deactivation_route_treats_token_claims_as_actor_identity_only() -> None:
    service = FakeService()
    response = resolve(service, event())

    assert response["statusCode"] == 200
    assert service.calls[0]["cognito_sub"] == "admin-sub"
    assert set(service.calls[0]) == {
        "cognito_sub",
        "user_id",
        "idempotency_key",
        "request_id",
        "body",
    }


def test_deactivation_route_accepts_case_insensitive_idempotency_header() -> None:
    request = event()
    request["headers"] = {"idempotency-key": KEY}

    response = resolve(FakeService(), request)

    assert response["statusCode"] == 200


def test_deactivation_route_passes_missing_request_id_as_none() -> None:
    request = event()
    del request["requestContext"]["requestId"]
    service = FakeService()

    response = resolve(service, request)

    assert response["statusCode"] == 200
    assert service.calls[0]["request_id"] is None


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(rawQueryString="x=1"),
        lambda value: value.update(isBase64Encoded=True),
        lambda value: value.update(body=None),
        lambda value: value.update(body=""),
        lambda value: value.update(headers={}),
        lambda value: value.update(headers={"Idempotency-Key": "not-a-uuid"}),
        lambda value: value.update(body="not-json"),
        lambda value: value.update(body='{"expectedVersion":1,"extra":true}'),
        lambda value: value.update(body='{"expectedVersion":1,"expectedVersion":2}'),
        lambda value: value.update(body='{"expectedVersion":true}'),
        lambda value: value.update(body='{"expectedVersion":"1"}'),
        lambda value: value.update(body='{"expectedVersion":1.0}'),
        lambda value: value.update(body='{"expectedVersion":0}'),
        lambda value: value.update(body='{"expectedVersion":-1}'),
    ],
)
def test_deactivation_route_rejects_invalid_envelope_or_contract(change: Any) -> None:
    request = event()
    change(request)

    response = resolve(FakeService(), request)

    assert response["statusCode"] == 400
    assert json.loads(response["body"]) == {
        "error": "INVALID_REQUEST",
        "message": "Invalid user deactivation request",
    }


@pytest.mark.parametrize(
    "claims",
    [
        {},
        {"token_use": "access"},
        {"token_use": "access", "sub": ""},
        {"token_use": "id", "sub": "admin-sub"},
        {"token_use": "Access", "sub": "admin-sub"},
    ],
)
def test_deactivation_route_rejects_invalid_access_identity(claims: dict[str, str]) -> None:
    request = event()
    request["requestContext"]["authorizer"]["jwt"]["claims"] = claims

    response = resolve(FakeService(), request)

    assert response["statusCode"] == 401
    assert json.loads(response["body"]) == {
        "error": "UNAUTHORIZED",
        "message": "Unauthorized",
    }


def test_deactivation_route_rejects_missing_jwt_context() -> None:
    request = event()
    request["requestContext"]["authorizer"] = {}

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
        (UserStateConflictError(), 409, "USER_STATE_CONFLICT"),
        (LastActiveAdminConflictError(), 409, "LAST_ACTIVE_ADMIN_CONFLICT"),
        (IdempotencyKeyReusedError(), 409, "IDEMPOTENCY_KEY_REUSED"),
        (OperationInProgressError(), 409, "OPERATION_IN_PROGRESS"),
        (
            UserDeactivationReconciliationError("AdminDisableUser secret@example.test"),
            503,
            "USER_DEACTIVATION_RECONCILIATION_REQUIRED",
        ),
        (
            RuntimeError("TransactionCanceled activeAdminCount secret@example.test"),
            500,
            "INTERNAL_ERROR",
        ),
    ],
)
def test_deactivation_route_maps_errors_without_internal_leakage(
    error: Exception, status: int, code: str
) -> None:
    response = resolve(FakeService(error), event())

    assert response["statusCode"] == status
    assert json.loads(response["body"])["error"] == code
    assert "secret@example.test" not in response["body"]
    assert "AdminDisableUser" not in response["body"]
    assert "activeAdminCount" not in response["body"]
    assert "TransactionCanceled" not in response["body"]
    assert "new Idempotency-Key" not in response["body"]


@pytest.mark.parametrize("scenario", ["operator", "inactive-admin", "self"])
def test_forbidden_deactivation_scenarios_are_sanitized(scenario: str) -> None:
    del scenario
    response = resolve(FakeService(AdminUserForbiddenError()), event())

    assert response["statusCode"] == 403
    assert json.loads(response["body"]) == {"error": "FORBIDDEN", "message": "Forbidden"}


def test_completed_replay_returns_the_original_terminal_response() -> None:
    original = dict(PUBLIC_USER)
    service = FakeService(response=original)

    first = resolve(service, event())
    replay = resolve(service, event())

    assert first["statusCode"] == replay["statusCode"] == 200
    assert json.loads(first["body"]) == json.loads(replay["body"]) == original


def test_invalid_empty_path_is_not_registered_as_deactivation() -> None:
    request = event()
    request["rawPath"] = "/users//deactivation"
    request["requestContext"]["http"]["path"] = "/users//deactivation"

    response = resolve(FakeService(), request)

    assert response["statusCode"] == 404


def test_lambda_handler_knows_local_deactivation_route(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeService()
    monkeypatch.setattr(admin_users, "get_deactivation_service", lambda: service)

    response = lambda_handler(event(), cast(LambdaContext, FakeContext()))

    assert response["statusCode"] == 200


def test_deactivation_dependency_wiring_creates_dynamodb_and_cognito_clients(
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
    dependencies.get_deactivation_service.cache_clear()
    try:
        assert dependencies.get_deactivation_service() is not None
    finally:
        dependencies.get_deactivation_service.cache_clear()

    assert client_services == ["dynamodb", "cognito-idp"]
    assert resource_services == ["dynamodb"]
