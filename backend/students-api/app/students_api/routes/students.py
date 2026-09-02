from typing import Any, Protocol
from urllib.parse import parse_qsl

from aws_lambda_powertools.event_handler import (
    APIGatewayHttpResolver,
    Response,
    content_types,
)

from students_api.dependencies import get_student_service
from students_api.errors import ForbiddenError, InvalidListRequestError, StudentNotFoundError


class StudentServiceProtocol(Protocol):
    def get_student(self, student_id: str) -> dict[str, Any]: ...

    def list_students(
        self,
        *,
        cognito_sub: str | None,
        limit: int,
        status: str,
        name_prefix: str | None,
        cursor: str | None,
    ) -> dict[str, Any]: ...


def _remove_storage_keys(student: dict[str, Any]) -> dict[str, Any]:
    storage_keys = {
        "PK",
        "SK",
        "GSI1PK",
        "GSI1SK",
        "GSI2PK",
        "GSI2SK",
    }

    return {key: value for key, value in student.items() if key not in storage_keys}


def register_student_routes(
    app: APIGatewayHttpResolver,
    service: StudentServiceProtocol | None = None,
) -> None:
    @app.get("/students")
    def list_students() -> dict[str, Any] | Response[dict[str, str]]:
        active_service = service if service is not None else get_student_service()

        try:
            parameters = _parse_list_parameters(app.current_event.raw_event)
            return active_service.list_students(
                cognito_sub=_authenticated_sub(app.current_event.raw_event),
                **parameters,
            )
        except InvalidListRequestError:
            return _error_response(400, "INVALID_REQUEST", "Invalid list request")
        except ForbiddenError:
            return _error_response(403, "FORBIDDEN", "Forbidden")

    @app.get("/students/<student_id>")
    def get_student(
        student_id: str,
    ) -> dict[str, Any] | Response[dict[str, str]]:
        active_service = service if service is not None else get_student_service()

        try:
            student = active_service.get_student(student_id)
        except StudentNotFoundError:
            return Response(
                status_code=404,
                content_type=content_types.APPLICATION_JSON,
                body={
                    "error": "STUDENT_NOT_FOUND",
                    "message": "Student not found",
                },
            )

        return _remove_storage_keys(student)


def _parse_list_parameters(event: dict[str, Any]) -> dict[str, Any]:
    allowed = {"limit", "cursor", "status", "namePrefix"}
    raw_query = event.get("rawQueryString", "")
    if not isinstance(raw_query, str):
        raise InvalidListRequestError
    try:
        pairs = parse_qsl(raw_query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise InvalidListRequestError from None

    parameters: dict[str, str] = {}
    for key, value in pairs:
        if key not in allowed or key in parameters:
            raise InvalidListRequestError
        parameters[key] = value

    raw_limit = parameters.get("limit", "20")
    if not raw_limit.isascii() or not raw_limit.isdecimal():
        raise InvalidListRequestError
    limit = int(raw_limit)
    if not 1 <= limit <= 100:
        raise InvalidListRequestError

    status = parameters.get("status", "ACTIVE")
    if status not in {"ACTIVE", "INACTIVE", "ALL"}:
        raise InvalidListRequestError

    cursor = parameters.get("cursor")
    if cursor == "":
        raise InvalidListRequestError

    return {
        "limit": limit,
        "status": status,
        "name_prefix": parameters.get("namePrefix"),
        "cursor": cursor,
    }


def _authenticated_sub(event: dict[str, Any]) -> str | None:
    request_context = event.get("requestContext")
    if not isinstance(request_context, dict):
        return None
    authorizer = request_context.get("authorizer")
    if not isinstance(authorizer, dict):
        return None
    jwt = authorizer.get("jwt")
    if not isinstance(jwt, dict):
        return None
    claims = jwt.get("claims")
    if not isinstance(claims, dict):
        return None
    subject = claims.get("sub")
    return subject if isinstance(subject, str) else None


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
