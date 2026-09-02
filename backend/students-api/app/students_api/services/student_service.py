from typing import Any, Protocol

from students_api.cursor import CursorPosition, decode_cursor, encode_cursor, normalize_name
from students_api.errors import InvalidListRequestError, StudentNotFoundError
from students_api.repositories.student_repository import StudentPage


class StudentRepositoryProtocol(Protocol):
    def get_by_id(self, student_id: str) -> dict[str, Any] | None: ...

    def list_students(
        self,
        *,
        status: str,
        name_prefix: str | None,
        limit: int,
        position: CursorPosition | None,
    ) -> StudentPage: ...


class AuthorizationProtocol(Protocol):
    def authorize_list_students(self, cognito_sub: str | None) -> None: ...


class StudentService:
    def __init__(
        self,
        repository: StudentRepositoryProtocol,
        authorization: AuthorizationProtocol | None = None,
    ) -> None:
        self._repository = repository
        self._authorization = authorization

    def get_student(self, student_id: str) -> dict[str, Any]:
        student = self._repository.get_by_id(student_id)

        if student is None:
            raise StudentNotFoundError

        return student

    def list_students(
        self,
        *,
        cognito_sub: str | None,
        limit: int,
        status: str,
        name_prefix: str | None,
        cursor: str | None,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 100 or status not in {"ACTIVE", "INACTIVE", "ALL"}:
            raise InvalidListRequestError
        if self._authorization is None:
            raise RuntimeError("Authorization service is required")
        self._authorization.authorize_list_students(cognito_sub)

        normalized_prefix = None
        if name_prefix is not None:
            if not 1 <= len(name_prefix) <= 150:
                raise InvalidListRequestError
            normalized_prefix = normalize_name(name_prefix)
            if not normalized_prefix:
                raise InvalidListRequestError

        position = decode_cursor(cursor, status, normalized_prefix) if cursor else None
        page = self._repository.list_students(
            status=status,
            name_prefix=normalized_prefix,
            limit=limit,
            position=position,
        )
        next_cursor = (
            encode_cursor(status, normalized_prefix, page.next_position)
            if page.next_position is not None
            else None
        )
        items = [
            {
                "studentId": item["studentId"],
                "registrationNumber": item["registrationNumber"],
                "fullName": item["fullName"],
                "status": item["status"],
            }
            for item in page.items
        ]
        return {"items": items, "nextCursor": next_cursor, "hasMore": next_cursor is not None}
