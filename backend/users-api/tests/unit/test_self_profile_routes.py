import json
from typing import Any, cast

import pytest
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from users_api.errors import SelfProfileForbiddenError
from users_api.routes.self_profile import register_self_profile_routes


class FakeService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[str] = []

    def get_current_user(self, *, cognito_sub: str) -> dict[str, object]:
        self.calls.append(cognito_sub)
        if self.error is not None:
            raise self.error
        return {
            "userId": "user-1",
            "fullName": "User One",
            "email": "user@example.test",
            "role": "ADMIN",
            "status": "INVITED",
            "authVersion": 1,
        }


def event() -> dict[str, Any]:
    return {
        "version": "2.0",
        "routeKey": "GET /users/me",
        "rawPath": "/users/me",
        "rawQueryString": "",
        "headers": {},
        "requestContext": {
            "http": {"method": "GET", "path": "/users/me"},
            "routeKey": "GET /users/me",
            "stage": "$default",
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
    register_self_profile_routes(resolver, service)
    return resolver.resolve(request, cast(LambdaContext, object()))


def test_returns_exact_contract_using_only_authenticated_subject() -> None:
    service = FakeService()

    response = resolve(service, event())
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body == {
        "userId": "user-1",
        "fullName": "User One",
        "email": "user@example.test",
        "role": "ADMIN",
        "status": "INVITED",
        "authVersion": 1,
    }
    assert type(body["authVersion"]) is int
    assert service.calls == ["sub-1"]


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(body="{}"),
        lambda value: value.update(rawQueryString="unexpected=true"),
    ],
)
def test_rejects_body_or_query_parameters(change: Any) -> None:
    request = event()
    change(request)

    response = resolve(FakeService(), request)

    assert response["statusCode"] == 400
    assert json.loads(response["body"]) == {
        "error": "INVALID_REQUEST",
        "message": "Invalid self-profile request",
    }


def test_returns_safe_forbidden_response() -> None:
    response = resolve(FakeService(SelfProfileForbiddenError("sensitive")), event())

    assert response["statusCode"] == 403
    assert json.loads(response["body"]) == {
        "error": "FORBIDDEN",
        "message": "Forbidden",
    }
    assert "sensitive" not in response["body"]


def test_returns_safe_internal_error() -> None:
    response = resolve(FakeService(RuntimeError("sensitive")), event())

    assert response["statusCode"] == 500
    assert json.loads(response["body"]) == {
        "error": "INTERNAL_ERROR",
        "message": "Unexpected internal error",
    }
    assert "sensitive" not in response["body"]
