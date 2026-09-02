from typing import Any, Protocol
from uuid import UUID

from aws_lambda_powertools.event_handler import (
    APIGatewayHttpResolver,
    Response,
    content_types,
)

from users_api.dependencies import get_activation_service
from users_api.errors import (
    ActivationConflictError,
    ActivationForbiddenError,
    ActivationUnauthorizedError,
)


class ActivationServiceProtocol(Protocol):
    def activate_current_user(
        self,
        *,
        cognito_sub: str,
        idempotency_key: str,
        request_id: str | None,
    ) -> dict[str, object]: ...


def register_activation_routes(
    app: APIGatewayHttpResolver,
    service: ActivationServiceProtocol | None = None,
) -> None:
    @app.post("/users/me/activation")
    def activate_current_user() -> dict[str, object] | Response[dict[str, str]]:
        event = app.current_event.raw_event
        try:
            cognito_sub, key, request_id = _parse_request(event)
            active_service = service if service is not None else get_activation_service()
            return active_service.activate_current_user(
                cognito_sub=cognito_sub,
                idempotency_key=key,
                request_id=request_id,
            )
        except ValueError:
            return _error_response(400, "INVALID_REQUEST", "Invalid activation request")
        except ActivationUnauthorizedError:
            return _error_response(401, "UNAUTHORIZED", "Unauthorized")
        except ActivationForbiddenError:
            return _error_response(403, "FORBIDDEN", "Forbidden")
        except ActivationConflictError:
            return _error_response(409, "ACTIVATION_CONFLICT", "Activation cannot be completed")
        except Exception:
            return _error_response(500, "INTERNAL_ERROR", "Unexpected internal error")


def _parse_request(event: dict[str, Any]) -> tuple[str, str, str | None]:
    if event.get("rawQueryString") not in {None, ""}:
        raise ValueError
    if event.get("body") not in {None, ""}:
        raise ValueError

    headers = event.get("headers")
    if not isinstance(headers, dict):
        raise ValueError
    normalized_headers = {str(name).lower(): value for name, value in headers.items()}
    key = normalized_headers.get("idempotency-key")
    if not isinstance(key, str) or not _is_canonical_uuid(key):
        raise ValueError

    request_context = event.get("requestContext")
    if not isinstance(request_context, dict):
        raise ActivationUnauthorizedError
    authorizer = request_context.get("authorizer")
    if not isinstance(authorizer, dict):
        raise ActivationUnauthorizedError
    jwt = authorizer.get("jwt")
    if not isinstance(jwt, dict):
        raise ActivationUnauthorizedError
    claims = jwt.get("claims")
    if not isinstance(claims, dict) or claims.get("token_use") != "access":
        raise ActivationUnauthorizedError
    cognito_sub = claims.get("sub")
    if not isinstance(cognito_sub, str) or not cognito_sub:
        raise ActivationUnauthorizedError

    request_id = request_context.get("requestId")
    return cognito_sub, key, request_id if isinstance(request_id, str) else None


def _is_canonical_uuid(value: str) -> bool:
    try:
        return str(UUID(value)) == value
    except (ValueError, AttributeError):
        return False


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
