from typing import Any, Protocol, TypedDict
from urllib.parse import parse_qsl

from aws_lambda_powertools.event_handler import (
    APIGatewayHttpResolver,
    Response,
    content_types,
)

from users_api.dependencies import get_admin_user_service
from users_api.errors import (
    AdminUserForbiddenError,
    AdminUserNotFoundError,
    AdminUserUnauthorizedError,
    InvalidAdminUserListRequestError,
)


class ListParameters(TypedDict):
    limit: int
    role: str
    status: str
    name_prefix: str | None
    email: str | None
    cursor: str | None


class AdminUserServiceProtocol(Protocol):
    def get_user(self, *, cognito_sub: str, user_id: str) -> dict[str, object]: ...

    def list_users(
        self,
        *,
        cognito_sub: str,
        limit: int,
        role: str,
        status: str,
        name_prefix: str | None,
        email: str | None,
        cursor: str | None,
    ) -> dict[str, object]: ...


def register_admin_user_routes(
    app: APIGatewayHttpResolver,
    service: AdminUserServiceProtocol | None = None,
) -> None:
    @app.get("/users")
    def list_users() -> dict[str, object] | Response[dict[str, str]]:
        try:
            parameters = _parse_list_request(app.current_event.raw_event)
            active_service = service if service is not None else get_admin_user_service()
            return active_service.list_users(
                cognito_sub=_authenticated_sub(app.current_event.raw_event),
                **parameters,
            )
        except InvalidAdminUserListRequestError:
            return _error_response(400, "INVALID_REQUEST", "Invalid users list request")
        except AdminUserUnauthorizedError:
            return _error_response(401, "UNAUTHORIZED", "Unauthorized")
        except AdminUserForbiddenError:
            return _error_response(403, "FORBIDDEN", "Forbidden")
        except Exception:
            return _error_response(500, "INTERNAL_ERROR", "Unexpected internal error")

    @app.get("/users/<user_id>")
    def get_user(user_id: str) -> dict[str, object] | Response[dict[str, str]]:
        try:
            event = app.current_event.raw_event
            _validate_detail_request(event)
            active_service = service if service is not None else get_admin_user_service()
            return active_service.get_user(
                cognito_sub=_authenticated_sub(event),
                user_id=user_id,
            )
        except InvalidAdminUserListRequestError:
            return _error_response(400, "INVALID_REQUEST", "Invalid user detail request")
        except AdminUserUnauthorizedError:
            return _error_response(401, "UNAUTHORIZED", "Unauthorized")
        except AdminUserForbiddenError:
            return _error_response(403, "FORBIDDEN", "Forbidden")
        except AdminUserNotFoundError:
            return _error_response(404, "USER_NOT_FOUND", "User not found")
        except Exception:
            return _error_response(500, "INTERNAL_ERROR", "Unexpected internal error")


def _parse_list_request(event: dict[str, Any]) -> ListParameters:
    if event.get("body") not in {None, ""} or event.get("isBase64Encoded") is True:
        raise InvalidAdminUserListRequestError
    raw_query = event.get("rawQueryString", "")
    if not isinstance(raw_query, str):
        raise InvalidAdminUserListRequestError
    try:
        pairs = parse_qsl(raw_query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise InvalidAdminUserListRequestError from None
    allowed = {"limit", "cursor", "namePrefix", "email", "role", "status"}
    values: dict[str, str] = {}
    for name, value in pairs:
        if name not in allowed or name in values:
            raise InvalidAdminUserListRequestError
        values[name] = value
    raw_limit = values.get("limit", "20")
    if not raw_limit.isascii() or not raw_limit.isdecimal():
        raise InvalidAdminUserListRequestError
    limit = int(raw_limit)
    if not 1 <= limit <= 100:
        raise InvalidAdminUserListRequestError
    cursor = values.get("cursor")
    if cursor == "":
        raise InvalidAdminUserListRequestError
    return {
        "limit": limit,
        "cursor": cursor,
        "name_prefix": values.get("namePrefix"),
        "email": values.get("email"),
        "role": values.get("role", "ALL"),
        "status": values.get("status", "ALL"),
    }


def _validate_detail_request(event: dict[str, Any]) -> None:
    if (
        event.get("rawQueryString") not in {None, ""}
        or event.get("body") not in {None, ""}
        or event.get("isBase64Encoded") is True
    ):
        raise InvalidAdminUserListRequestError


def _authenticated_sub(event: dict[str, Any]) -> str:
    request_context = event.get("requestContext")
    if not isinstance(request_context, dict):
        raise AdminUserUnauthorizedError
    authorizer = request_context.get("authorizer")
    if not isinstance(authorizer, dict):
        raise AdminUserUnauthorizedError
    jwt = authorizer.get("jwt")
    if not isinstance(jwt, dict):
        raise AdminUserUnauthorizedError
    claims = jwt.get("claims")
    if not isinstance(claims, dict) or claims.get("token_use") != "access":
        raise AdminUserUnauthorizedError
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise AdminUserUnauthorizedError
    return subject


def _error_response(status: int, code: str, message: str) -> Response[dict[str, str]]:
    return Response(
        status_code=status,
        content_type=content_types.APPLICATION_JSON,
        body={"error": code, "message": message},
    )
