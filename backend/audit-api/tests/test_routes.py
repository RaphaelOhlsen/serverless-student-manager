import json
from dataclasses import replace
from decimal import Decimal
from typing import Any, cast

import pytest
from audit_api.authorization import AdminAuthorizationService
from audit_api.errors import InvalidAuditCursorError
from audit_api.query import MAX_CURSOR_BYTES, AccessPath, AuditQuery
from audit_api.query_engine import AuditPage, AuditQueryEngine
from audit_api.repository import AuditEventRepository
from audit_api.routes.audit_events import register_audit_event_routes
from audit_api.service import AuditQueryService
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.utilities.typing import LambdaContext

PUBLIC_EVENT = {
    "eventId": "event-1",
    "eventType": "STUDENT_UPDATED",
    "resourceType": "STUDENT",
    "resourceId": "student-1",
    "actorId": "admin-1",
    "occurredAt": "2026-09-20T10:00:00.000Z",
    "result": "SUCCESS",
    "correlationId": "correlation-1",
}


class FakeContext:
    function_name = "AuditApi"
    memory_limit_in_mb = 512
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:AuditApi"
    aws_request_id = "lambda-request"
    log_group_name = "/aws/lambda/AuditApi"
    log_stream_name = "stream"

    def get_remaining_time_in_millis(self) -> int:
        return 30_000


class FakeService:
    def __init__(self, page: AuditPage | None = None, error: Exception | None = None) -> None:
        self.page = page or AuditPage(items=[PUBLIC_EVENT], next_cursor="next-cursor")
        self.error = error
        self.calls: list[tuple[str, AuditQuery]] = []

    def execute(self, cognito_sub: str, query: AuditQuery) -> AuditPage:
        self.calls.append((cognito_sub, query))
        if self.error is not None:
            raise self.error
        return self.page


class FakeEngine:
    def __init__(self, page: AuditPage | None = None, error: Exception | None = None) -> None:
        self.page = page or AuditPage(items=[PUBLIC_EVENT], next_cursor=None)
        self.error = error
        self.queries: list[AuditQuery] = []

    def execute(self, query: AuditQuery) -> AuditPage:
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return self.page


class GuardedUsersTable:
    def __init__(self, role: str = "ADMIN", status: str = "ACTIVE") -> None:
        self.role = role
        self.status = status
        self.inconsistent = False
        self.calls: list[dict[str, object]] = []

    def get_item(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        key = kwargs["Key"]
        assert isinstance(key, dict)
        if key["SK"] == "AUTHORIZATION":
            item = {
                "PK": "COGNITO#admin-sub",
                "SK": "AUTHORIZATION",
                "userId": "user-1",
                "cognitoSub": "admin-sub",
                "role": self.role,
                "status": self.status,
                "authVersion": Decimal("2"),
            }
        else:
            item = {
                "PK": "USER#user-1",
                "SK": "PROFILE",
                "userId": "user-1",
                "cognitoSub": "admin-sub",
                "role": "OPERATOR" if self.inconsistent else self.role,
                "status": self.status,
                "authVersion": Decimal("2"),
            }
        return {"Item": item}

    def put_item(self, **kwargs: object) -> None:
        raise AssertionError("DynamoDB writes are forbidden")

    def update_item(self, **kwargs: object) -> None:
        raise AssertionError("DynamoDB writes are forbidden")

    def delete_item(self, **kwargs: object) -> None:
        raise AssertionError("DynamoDB writes are forbidden")


class GuardedAuditTable:
    def __init__(self) -> None:
        self.query_calls: list[dict[str, object]] = []

    def query(self, **kwargs: object) -> dict[str, object]:
        self.query_calls.append(kwargs)
        occurred_at = "2026-09-20T10:00:00.000Z"
        sort_key = f"TS#{occurred_at}#EVENT#event-1"
        return {
            "Items": [
                {
                    "PK": "RESOURCE#STUDENT#student-1",
                    "SK": sort_key,
                    "GSI3PK": "PERIOD#2026-09",
                    "GSI3SK": sort_key,
                    **PUBLIC_EVENT,
                    "changes": {"private": True},
                }
            ]
        }

    def scan(self, **kwargs: object) -> None:
        raise AssertionError("Scan is forbidden")

    def get_item(self, **kwargs: object) -> None:
        raise AssertionError("audit hydration is forbidden")

    def put_item(self, **kwargs: object) -> None:
        raise AssertionError("audit writes are forbidden")

    def update_item(self, **kwargs: object) -> None:
        raise AssertionError("audit writes are forbidden")

    def delete_item(self, **kwargs: object) -> None:
        raise AssertionError("audit writes are forbidden")


def event(raw_query: str | None = None) -> dict[str, Any]:
    query = raw_query or ("from=2026-09-01T00%3A00%3A00Z&to=2026-09-30T23%3A59%3A59.999Z&limit=2")
    return {
        "version": "2.0",
        "routeKey": "GET /audit-events",
        "rawPath": "/audit-events",
        "rawQueryString": query,
        "headers": {},
        "requestContext": {
            "http": {"method": "GET", "path": "/audit-events"},
            "routeKey": "GET /audit-events",
            "requestId": "request-1",
            "stage": "$default",
            "authorizer": {"jwt": {"claims": {"sub": "admin-sub", "token_use": "access"}}},
        },
        "isBase64Encoded": False,
    }


def resolve(service: object, request: dict[str, Any] | None = None) -> dict[str, Any]:
    resolver = APIGatewayHttpResolver()
    register_audit_event_routes(resolver, cast(Any, service))
    return resolver.resolve(request or event(), cast(LambdaContext, FakeContext()))


def error_body(response: dict[str, Any]) -> dict[str, object]:
    body = json.loads(response["body"])
    assert set(body) == {"code", "message", "correlationId", "details"}
    assert body["correlationId"] == "request-1"
    assert body["details"] == []
    return cast(dict[str, object], body)


def test_admin_query_returns_exact_public_envelope_and_delegates_query() -> None:
    private = {**PUBLIC_EVENT, "changes": {"private": True}, "PK": "internal"}
    service = FakeService(AuditPage(items=[cast(Any, private)], next_cursor="opaque"))

    response = resolve(service)

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"items": [PUBLIC_EVENT], "nextCursor": "opaque"}
    assert service.calls[0][0] == "admin-sub"
    query = service.calls[0][1]
    assert query.limit == 2
    assert query.access_path is AccessPath.PERIOD


def test_empty_result_is_200_with_null_cursor() -> None:
    response = resolve(FakeService(AuditPage(items=[], next_cursor=None)))

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"items": [], "nextCursor": None}


@pytest.mark.parametrize(
    "raw_query",
    [
        "to=2026-09-30T00%3A00%3A00Z",
        "from=bad&to=2026-09-30T00%3A00%3A00Z",
        "from=2026-09-01T00%3A00%3A00Z&to=2026-09-30T00%3A00%3A00Z&unknown=x",
        ("from=2026-09-01T00%3A00%3A00Z&to=2026-09-30T00%3A00%3A00Z&limit=10&limit=20"),
    ],
)
def test_invalid_or_repeated_query_is_400_invalid_request(raw_query: str) -> None:
    service = FakeService()

    response = resolve(service, event(raw_query))

    assert response["statusCode"] == 400
    assert error_body(response)["code"] == "INVALID_REQUEST"
    assert service.calls == []


def test_invalid_cursor_is_400_with_sanitized_error() -> None:
    response = resolve(FakeService(error=InvalidAuditCursorError("physical details")))

    assert response["statusCode"] == 400
    body = error_body(response)
    assert body["code"] == "INVALID_CURSOR"
    assert "physical" not in response["body"]


def test_oversized_cursor_is_400_invalid_cursor_before_service_execution() -> None:
    service = FakeService()
    raw_query = "from=2026-09-01T00%3A00%3A00Z&to=2026-09-30T00%3A00%3A00Z&cursor=" + "a" * (
        MAX_CURSOR_BYTES + 1
    )

    response = resolve(service, event(raw_query))

    assert response["statusCode"] == 400
    assert error_body(response)["code"] == "INVALID_CURSOR"
    assert service.calls == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda request: request["requestContext"].pop("authorizer"),
        lambda request: request["requestContext"].update(authorizer={}),
        lambda request: request["requestContext"].update(authorizer={"jwt": {}}),
        lambda request: request["requestContext"]["authorizer"]["jwt"].update(claims={}),
        lambda request: request["requestContext"]["authorizer"]["jwt"].update(
            claims={"sub": "admin-sub", "token_use": "id"}
        ),
    ],
)
def test_missing_or_malformed_authorizer_context_fails_closed_as_403(mutate: Any) -> None:
    request = event()
    mutate(request)

    response = resolve(FakeService(), request)

    assert response["statusCode"] == 403
    assert error_body(response)["code"] == "FORBIDDEN"


@pytest.mark.parametrize(
    ("role", "status"),
    [("OPERATOR", "ACTIVE"), ("ADMIN", "INACTIVE"), ("ADMIN", "INVITED")],
)
def test_non_active_admin_is_forbidden_through_real_authorization(role: str, status: str) -> None:
    users = GuardedUsersTable(role=role, status=status)
    service = AuditQueryService(AdminAuthorizationService(users), FakeEngine())

    response = resolve(service)

    assert response["statusCode"] == 403
    assert error_body(response)["code"] == "FORBIDDEN"


def test_inconsistent_profile_authorization_is_forbidden() -> None:
    users = GuardedUsersTable()
    users.inconsistent = True
    service = AuditQueryService(AdminAuthorizationService(users), FakeEngine())

    response = resolve(service)

    assert response["statusCode"] == 403
    assert error_body(response)["code"] == "FORBIDDEN"


def test_real_service_authorizes_then_delegates_to_existing_engine() -> None:
    users = GuardedUsersTable()
    engine = FakeEngine(AuditPage(items=[PUBLIC_EVENT], next_cursor="opaque"))
    service = AuditQueryService(AdminAuthorizationService(users), engine)

    response = resolve(service)

    assert response["statusCode"] == 200
    assert len(engine.queries) == 1
    assert len(users.calls) == 2
    assert all(call["ConsistentRead"] is True for call in users.calls)


def test_route_runs_real_query_engine_without_scan_hydration_or_writes() -> None:
    users = GuardedUsersTable()
    audit = GuardedAuditTable()
    service = AuditQueryService(
        AdminAuthorizationService(users),
        AuditQueryEngine(AuditEventRepository(audit)),
    )

    response = resolve(service)

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"items": [PUBLIC_EVENT], "nextCursor": None}
    assert len(audit.query_calls) == 1
    assert audit.query_calls[0]["ScanIndexForward"] is False
    assert audit.query_calls[0]["IndexName"] == "gsi-period-time"


def test_internal_failure_is_sanitized_500() -> None:
    response = resolve(FakeService(error=RuntimeError("table-name PK GSI secret")))

    assert response["statusCode"] == 500
    body = error_body(response)
    assert body["code"] == "INTERNAL_ERROR"
    assert all(value not in response["body"] for value in ("table-name", "PK", "GSI", "secret"))


def test_authorization_storage_failure_is_sanitized_500() -> None:
    class FailingUsersTable:
        def get_item(self, **kwargs: object) -> dict[str, object]:
            raise RuntimeError("users-table internal failure")

    service = AuditQueryService(AdminAuthorizationService(FailingUsersTable()), FakeEngine())

    response = resolve(service)

    assert response["statusCode"] == 500
    assert error_body(response)["code"] == "INTERNAL_ERROR"
    assert "users-table" not in response["body"]


def test_cursor_is_forwarded_to_existing_query_model() -> None:
    service = FakeService()
    request = event("from=2026-09-01T00%3A00%3A00Z&to=2026-09-30T00%3A00%3A00Z&cursor=abc")

    response = resolve(service, request)

    assert response["statusCode"] == 200
    assert service.calls[0][1].cursor == "abc"


def test_route_does_not_mutate_query_object() -> None:
    service = FakeService()
    response = resolve(service)
    original = service.calls[0][1]

    assert response["statusCode"] == 200
    assert replace(original) == original
