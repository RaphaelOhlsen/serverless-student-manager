from typing import Any, Protocol
from urllib.parse import parse_qsl
from uuid import UUID, uuid4

from aws_lambda_powertools.event_handler import (
    APIGatewayHttpResolver,
    Response,
    content_types,
)

from students_api.dependencies import get_create_student_service, get_student_service
from students_api.errors import (
    ForbiddenError,
    IdempotencyKeyReusedError,
    InvalidCreateStudentRequestError,
    InvalidListRequestError,
    OperationInProgressError,
    RegistrationNumberAlreadyExistsError,
    StudentEmailAlreadyExistsError,
    StudentNotFoundError,
    StudentUniquenessConflictError,
)
from students_api.validation import CreateStudentInput, parse_create_student_body


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


class CreateStudentServiceProtocol(Protocol):
    def create_student(
        self,
        *,
        cognito_sub: str | None,
        idempotency_key: str,
        request_id: str | None,
        student: CreateStudentInput,
    ) -> dict[str, object]: ...


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
    create_service: CreateStudentServiceProtocol | None = None,
) -> None:
    @app.post("/students")
    def create_student() -> Response[dict[str, object]]:
        event = app.current_event.raw_event
        correlation_id = _request_id(event)
        try:
            cognito_sub, key, student = _parse_create_request(event)
            active_service = (
                create_service if create_service is not None else get_create_student_service()
            )
            result = active_service.create_student(
                cognito_sub=cognito_sub,
                idempotency_key=key,
                request_id=correlation_id,
                student=student,
            )
            return Response(
                status_code=201,
                content_type=content_types.APPLICATION_JSON,
                body=result,
            )
        except InvalidCreateStudentRequestError:
            return _canonical_error_response(
                400, "INVALID_REQUEST", "Invalid student creation request", correlation_id
            )
        except ForbiddenError:
            return _canonical_error_response(403, "FORBIDDEN", "Forbidden", correlation_id)
        except RegistrationNumberAlreadyExistsError:
            return _canonical_error_response(
                409,
                "REGISTRATION_NUMBER_ALREADY_EXISTS",
                "Registration number already exists",
                correlation_id,
            )
        except StudentEmailAlreadyExistsError:
            return _canonical_error_response(
                409,
                "STUDENT_EMAIL_ALREADY_EXISTS",
                "Student email already exists",
                correlation_id,
            )
        except StudentUniquenessConflictError:
            return _canonical_error_response(
                409,
                "STUDENT_UNIQUENESS_CONFLICT",
                "Student uniqueness conflict",
                correlation_id,
            )
        except IdempotencyKeyReusedError:
            return _canonical_error_response(
                409, "IDEMPOTENCY_KEY_REUSED", "Idempotency key reused", correlation_id
            )
        except OperationInProgressError:
            return _canonical_error_response(
                409, "OPERATION_IN_PROGRESS", "Operation in progress", correlation_id
            )
        except Exception:
            return _canonical_error_response(
                500, "INTERNAL_ERROR", "Unexpected internal error", correlation_id
            )

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
    if not isinstance(claims, dict) or claims.get("token_use") not in {None, "access"}:
        return None
    subject = claims.get("sub")
    return subject if isinstance(subject, str) else None


def _parse_create_request(
    event: dict[str, Any],
) -> tuple[str | None, str, CreateStudentInput]:
    if event.get("rawQueryString") not in {None, ""} or event.get("isBase64Encoded") is True:
        raise InvalidCreateStudentRequestError
    headers = event.get("headers")
    if not isinstance(headers, dict):
        raise InvalidCreateStudentRequestError
    normalized_headers = {str(name).lower(): value for name, value in headers.items()}
    content_type = normalized_headers.get("content-type")
    if (
        not isinstance(content_type, str)
        or content_type.split(";", 1)[0].strip().lower() != "application/json"
    ):
        raise InvalidCreateStudentRequestError
    key = normalized_headers.get("idempotency-key")
    if not isinstance(key, str) or not _is_canonical_uuid(key):
        raise InvalidCreateStudentRequestError
    body = event.get("body")
    if not isinstance(body, str):
        raise InvalidCreateStudentRequestError
    return _authenticated_access_sub(event), key, parse_create_student_body(body)


def _authenticated_access_sub(event: dict[str, Any]) -> str | None:
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
    if not isinstance(claims, dict) or claims.get("token_use") != "access":
        return None
    subject = claims.get("sub")
    return subject if isinstance(subject, str) and subject else None


def _request_id(event: dict[str, Any]) -> str:
    request_context = event.get("requestContext")
    if isinstance(request_context, dict):
        request_id = request_context.get("requestId")
        if isinstance(request_id, str) and request_id:
            return request_id
    return str(uuid4())


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


def _canonical_error_response(
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
