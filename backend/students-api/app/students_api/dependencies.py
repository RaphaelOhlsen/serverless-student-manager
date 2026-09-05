from functools import lru_cache
from typing import Any

import boto3  # type: ignore[import-untyped]
from aws_lambda_powertools.utilities.idempotency import DynamoDBPersistenceLayer

from students_api.authorization import AuthorizationService
from students_api.config import (
    get_audit_retention_days,
    get_audit_table_name,
    get_environment,
    get_idempotency_table_name,
    get_students_table_name,
    get_users_table_name,
)
from students_api.idempotency import CreateStudentIdempotency
from students_api.repositories.student_repository import StudentRepository
from students_api.services.create_student_service import CreateStudentService
from students_api.services.student_service import StudentService


@lru_cache
def get_student_service() -> StudentService:
    dynamodb = boto3.resource("dynamodb")
    students_table: Any = dynamodb.Table(get_students_table_name())
    users_table: Any = dynamodb.Table(get_users_table_name())

    repository = StudentRepository(students_table)
    authorization = AuthorizationService(users_table)

    return StudentService(repository, authorization)


@lru_cache
def get_create_student_service() -> CreateStudentService:
    dynamodb_client = boto3.client("dynamodb")
    dynamodb_resource = boto3.resource("dynamodb")
    students_table: Any = dynamodb_resource.Table(get_students_table_name())
    users_table: Any = dynamodb_resource.Table(get_users_table_name())
    repository = StudentRepository(
        students_table,
        client=dynamodb_client,
        students_table_name=get_students_table_name(),
        audit_table_name=get_audit_table_name(),
    )
    persistence = DynamoDBPersistenceLayer(
        table_name=get_idempotency_table_name(),
        boto3_client=dynamodb_client,
    )
    return CreateStudentService(
        repository,
        AuthorizationService(users_table),
        CreateStudentIdempotency(persistence),
        environment=get_environment(),
        audit_retention_days=get_audit_retention_days(),
    )
