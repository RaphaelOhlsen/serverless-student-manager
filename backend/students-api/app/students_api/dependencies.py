from functools import lru_cache
from typing import Any

import boto3  # type: ignore[import-untyped]

from students_api.config import get_students_table_name
from students_api.repositories.student_repository import StudentRepository
from students_api.services.student_service import StudentService


@lru_cache
def get_student_service() -> StudentService:
    dynamodb = boto3.resource("dynamodb")
    table: Any = dynamodb.Table(get_students_table_name())

    repository = StudentRepository(table)

    return StudentService(repository)
