from functools import lru_cache
from typing import Any

import boto3  # type: ignore[import-untyped]

from users_api.config import (
    get_audit_retention_days,
    get_audit_table_name,
    get_environment,
    get_idempotency_table_name,
    get_user_pool_id,
    get_users_table_name,
)
from users_api.repositories.cognito_repository import CognitoRepository
from users_api.repositories.idempotency_repository import IdempotencyRepository
from users_api.repositories.user_repository import UserRepository
from users_api.services.activation_service import ActivationService


@lru_cache
def get_activation_service() -> ActivationService:
    dynamodb_client = boto3.client("dynamodb")
    dynamodb_resource = boto3.resource("dynamodb")
    idempotency_table: Any = dynamodb_resource.Table(get_idempotency_table_name())
    cognito_client = boto3.client("cognito-idp")

    return ActivationService(
        UserRepository(
            dynamodb_client,
            get_users_table_name(),
            get_audit_table_name(),
        ),
        CognitoRepository(cognito_client, get_user_pool_id()),
        IdempotencyRepository(idempotency_table),
        environment=get_environment(),
        audit_retention_days=get_audit_retention_days(),
    )
