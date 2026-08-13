from typing import Any, Protocol

from students_api.errors import StudentNotFoundError


class StudentRepositoryProtocol(Protocol):
    def get_by_id(self, student_id: str) -> dict[str, Any] | None: ...


class StudentService:
    def __init__(self, repository: StudentRepositoryProtocol) -> None:
        self._repository = repository

    def get_student(self, student_id: str) -> dict[str, Any]:
        student = self._repository.get_by_id(student_id)

        if student is None:
            raise StudentNotFoundError

        return student
