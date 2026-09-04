from typing import Any, Protocol

from aws_lambda_powertools.event_handler import (
    APIGatewayHttpResolver,
    Response,
    content_types,
)

from users_api.dependencies import get_self_profile_service
from users_api.errors import SelfProfileForbiddenError, SelfProfileUnauthorizedError


class SelfProfileServiceProtocol(Protocol):
    def get_current_user(self, *, cognito_sub: str) -> dict[str, object]: ...


def register_self_profile_routes(
    app: APIGatewayHttpResolver,
    service: SelfProfileServiceProtocol | None = None,
) -> None:
    @app.get("/users/me")
    def get_current_user() -> dict[str, object] | Response[dict[str, str]]:
        try:
            cognito_sub = _parse_request(app.current_event.raw_event)
            active_service = service if service is not None else get_self_profile_service()
            return active_service.get_current_user(cognito_sub=cognito_sub)
        except ValueError:
            return _error_response(400, "INVALID_REQUEST", "Invalid self-profile request")
        except SelfProfileUnauthorizedError:
            return _error_response(401, "UNAUTHORIZED", "Unauthorized")
        except SelfProfileForbiddenError:
            return _error_response(403, "FORBIDDEN", "Forbidden")
        except Exception:
            return _error_response(500, "INTERNAL_ERROR", "Unexpected internal error")


def _parse_request(event: dict[str, Any]) -> str:
    if event.get("rawQueryString") not in {None, ""}:
        raise ValueError
    if event.get("body") not in {None, ""}:
        raise ValueError

    request_context = event.get("requestContext")
    if not isinstance(request_context, dict):
        raise SelfProfileUnauthorizedError
    authorizer = request_context.get("authorizer")
    if not isinstance(authorizer, dict):
        raise SelfProfileUnauthorizedError
    jwt = authorizer.get("jwt")
    if not isinstance(jwt, dict):
        raise SelfProfileUnauthorizedError
    claims = jwt.get("claims")
    if not isinstance(claims, dict) or claims.get("token_use") != "access":
        raise SelfProfileUnauthorizedError
    cognito_sub = claims.get("sub")
    if not isinstance(cognito_sub, str) or not cognito_sub:
        raise SelfProfileUnauthorizedError
    return cognito_sub


def _error_response(
    status_code: int,
    error: str,
    message: str,
) -> Response[dict[str, str]]:
    return Response(
        status_code=status_code,
        content_type=content_types.APPLICATION_JSON,
        body={"error": error, "message": message},
    )
