import json
from typing import Any, cast

import pytest
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from users_api.errors import AdminUserForbiddenError, AdminUserNotFoundError
from users_api.routes.admin_users import register_admin_user_routes


class FakeService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, dict[str, object]]] = []

    def list_users(self, *, cognito_sub: str, **kwargs: object) -> dict[str, object]:
        self.calls.append((cognito_sub, kwargs))
        if self.error:
            raise self.error
        return {"items": [], "nextCursor": None}

    def get_user(self, *, cognito_sub: str, user_id: str) -> dict[str, object]:
        self.calls.append((cognito_sub, {"user_id": user_id}))
        if self.error:
            raise self.error
        return {"userId": user_id}


def event(path: str, route_key: str, query: str = "") -> dict[str, Any]:
    return {
        "version": "2.0",
        "routeKey": route_key,
        "rawPath": path,
        "rawQueryString": query,
        "headers": {},
        "requestContext": {
            "http": {"method": "GET", "path": path},
            "routeKey": route_key,
            "stage": "$default",
            "authorizer": {"jwt": {"claims": {"sub": "admin-sub", "token_use": "access"}}},
        },
        "isBase64Encoded": False,
    }


def resolve(service: FakeService, request: dict[str, Any]) -> dict[str, Any]:
    resolver = APIGatewayHttpResolver()
    register_admin_user_routes(resolver, service)
    return resolver.resolve(request, cast(LambdaContext, object()))


def test_list_parses_exact_contract_and_defaults() -> None:
    service = FakeService()
    response = resolve(
        service,
        event(
            "/users",
            "GET /users",
            "limit=100&namePrefix=Ana&role=ADMIN&status=ACTIVE&cursor=abc",
        ),
    )
    assert response["statusCode"] == 200
    assert service.calls == [
        (
            "admin-sub",
            {
                "limit": 100,
                "name_prefix": "Ana",
                "email": None,
                "role": "ADMIN",
                "status": "ACTIVE",
                "cursor": "abc",
            },
        )
    ]


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=true", "x=1", "role=A&role=B"])
def test_list_rejects_invalid_query(query: str) -> None:
    response = resolve(FakeService(), event("/users", "GET /users", query))
    assert response["statusCode"] == 400


def test_detail_maps_success_not_found_forbidden_and_safe_technical_error() -> None:
    request = event("/users/user-1", "GET /users/{userId}")
    assert resolve(FakeService(), request)["statusCode"] == 200
    not_found = resolve(FakeService(AdminUserNotFoundError()), request)
    assert not_found["statusCode"] == 404
    forbidden = resolve(FakeService(AdminUserForbiddenError()), request)
    assert forbidden["statusCode"] == 403
    technical = resolve(FakeService(RuntimeError("secret@example.test")), request)
    assert technical["statusCode"] == 500
    assert "secret@example.test" not in technical["body"]


def test_missing_or_non_access_identity_is_unauthorized() -> None:
    request = event("/users", "GET /users")
    request["requestContext"]["authorizer"]["jwt"]["claims"]["token_use"] = "id"
    response = resolve(FakeService(), request)
    assert response["statusCode"] == 401
    assert json.loads(response["body"])["error"] == "UNAUTHORIZED"
