from typing import Any, Protocol
from uuid import uuid4

from aws_lambda_powertools.event_handler import (
    APIGatewayHttpResolver,
    Response,
    content_types,
)

from audit_api.dependencies import get_audit_query_service
from audit_api.errors import (
    AuditForbiddenError,
    InvalidAuditCursorError,
    InvalidAuditQueryRequestError,
)
from audit_api.query import AuditQuery, parse_audit_query
from audit_api.query_engine import AuditPage
from audit_api.serializer import serialize_public_event


class AuditQueryServiceProtocol(Protocol):
    def execute(self, cognito_sub: str, query: AuditQuery) -> AuditPage: ...


def register_audit_event_routes(
    app: APIGatewayHttpResolver,
    service: AuditQueryServiceProtocol | None = None,
) -> None:
    @app.get("/audit-events")
    def get_audit_events() -> Response[dict[str, object]]:
        event = app.current_event.raw_event
        correlation_id = _request_id(event)
        try:
            query = parse_audit_query(event)
            cognito_sub = _authenticated_access_sub(event)
            active_service = service if service is not None else get_audit_query_service()
            page = active_service.execute(cognito_sub, query)
            public_items = [serialize_public_event(item) for item in page.items]
            return Response(
                status_code=200,
                content_type=content_types.APPLICATION_JSON,
                body={"items": public_items, "nextCursor": page.next_cursor},
            )
        except InvalidAuditQueryRequestError:
            return _error_response(
                400, "INVALID_REQUEST", "Invalid audit query request", correlation_id
            )
        except InvalidAuditCursorError:
            return _error_response(
                400, "INVALID_CURSOR", "Invalid audit query cursor", correlation_id
            )
        except AuditForbiddenError:
            return _error_response(403, "FORBIDDEN", "Forbidden", correlation_id)
        except Exception:
            return _error_response(
                500, "INTERNAL_ERROR", "Unexpected internal error", correlation_id
            )


def _authenticated_access_sub(event: dict[str, Any]) -> str:
    request_context = event.get("requestContext")
    if not isinstance(request_context, dict):
        raise AuditForbiddenError
    authorizer = request_context.get("authorizer")
    if not isinstance(authorizer, dict):
        raise AuditForbiddenError
    jwt = authorizer.get("jwt")
    if not isinstance(jwt, dict):
        raise AuditForbiddenError
    claims = jwt.get("claims")
    if not isinstance(claims, dict) or claims.get("token_use") != "access":
        raise AuditForbiddenError
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject or subject != subject.strip():
        raise AuditForbiddenError
    return subject


def _request_id(event: dict[str, Any]) -> str:
    request_context = event.get("requestContext")
    if isinstance(request_context, dict):
        request_id = request_context.get("requestId")
        if isinstance(request_id, str) and request_id:
            return request_id
    return str(uuid4())


def _error_response(
    status_code: int,
    code: str,
    message: str,
    correlation_id: str,
) -> Response[dict[str, object]]:
    return Response(
        status_code=status_code,
        content_type=content_types.APPLICATION_JSON,
        body={
            "code": code,
            "message": message,
            "correlationId": correlation_id,
            "details": [],
        },
    )
