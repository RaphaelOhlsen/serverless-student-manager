from typing import Any, Protocol

from aws_lambda_powertools.event_handler import (
    APIGatewayHttpResolver,
    Response,
    content_types,
)

from students_api.dependencies import get_student_service
from students_api.errors import StudentNotFoundError


class StudentServiceProtocol(Protocol):
    def get_student(self, student_id: str) -> dict[str, Any]: ...


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
