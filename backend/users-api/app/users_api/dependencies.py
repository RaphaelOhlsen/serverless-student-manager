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
from users_api.repositories.invitation_saga_repository import InvitationSagaRepository
from users_api.repositories.user_repository import UserRepository
from users_api.services.activation_service import ActivationService
from users_api.services.admin_user_service import AdminUserService
from users_api.services.cognito_create_service import CognitoCreateService
from users_api.services.create_user_service import CreateUserService
from users_api.services.deactivation_service import DeactivationService
from users_api.services.reactivation_service import ReactivationService
from users_api.services.resend_invitation_service import ResendInvitationService
from users_api.services.role_change_service import RoleChangeService
from users_api.services.self_profile_service import SelfProfileService
from users_api.services.user_provisioning_service import UserProvisioningService


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


@lru_cache
def get_self_profile_service() -> SelfProfileService:
    dynamodb_client = boto3.client("dynamodb")
    return SelfProfileService(
        UserRepository(
            dynamodb_client,
            get_users_table_name(),
            get_audit_table_name(),
        )
    )


@lru_cache
def get_admin_user_service() -> AdminUserService:
    dynamodb_client = boto3.client("dynamodb")
    return AdminUserService(
        UserRepository(
            dynamodb_client,
            get_users_table_name(),
            get_audit_table_name(),
        )
    )


@lru_cache
def get_create_user_service() -> CreateUserService:
    import time

    dynamodb_client = boto3.client("dynamodb")
    dynamodb_resource = boto3.resource("dynamodb")
    saga_table: Any = dynamodb_resource.Table(get_idempotency_table_name())
    users = UserRepository(
        dynamodb_client,
        get_users_table_name(),
        get_audit_table_name(),
    )
    saga = InvitationSagaRepository(
        saga_table,
        get_idempotency_table_name(),
        clock=time.time,
    )
    cognito = CognitoRepository(boto3.client("cognito-idp"), get_user_pool_id())
    return CreateUserService(
        users,
        saga,
        CognitoCreateService(cognito, saga),
        UserProvisioningService(
            users,
            saga,
            cognito,
            audit_retention_days=get_audit_retention_days(),
        ),
        cognito,
        environment=get_environment(),
    )


@lru_cache
def get_resend_invitation_service() -> ResendInvitationService:
    import time

    dynamodb_client = boto3.client("dynamodb")
    dynamodb_resource = boto3.resource("dynamodb")
    saga_table: Any = dynamodb_resource.Table(get_idempotency_table_name())
    users = UserRepository(
        dynamodb_client,
        get_users_table_name(),
        get_audit_table_name(),
    )
    saga = InvitationSagaRepository(
        saga_table,
        get_idempotency_table_name(),
        clock=time.time,
    )
    cognito = CognitoRepository(boto3.client("cognito-idp"), get_user_pool_id())
    return ResendInvitationService(
        users,
        saga,
        cognito,
        environment=get_environment(),
        audit_retention_days=get_audit_retention_days(),
    )


@lru_cache
def get_role_change_service() -> RoleChangeService:
    import time

    dynamodb_client = boto3.client("dynamodb")
    dynamodb_resource = boto3.resource("dynamodb")
    saga_table: Any = dynamodb_resource.Table(get_idempotency_table_name())
    users = UserRepository(
        dynamodb_client,
        get_users_table_name(),
        get_audit_table_name(),
    )
    saga = InvitationSagaRepository(
        saga_table,
        get_idempotency_table_name(),
        clock=time.time,
    )
    return RoleChangeService(
        users,
        saga,
        environment=get_environment(),
        audit_retention_days=get_audit_retention_days(),
    )


@lru_cache
def get_deactivation_service() -> DeactivationService:
    import time

    dynamodb_client = boto3.client("dynamodb")
    dynamodb_resource = boto3.resource("dynamodb")
    saga_table: Any = dynamodb_resource.Table(get_idempotency_table_name())
    users = UserRepository(
        dynamodb_client,
        get_users_table_name(),
        get_audit_table_name(),
    )
    saga = InvitationSagaRepository(
        saga_table,
        get_idempotency_table_name(),
        clock=time.time,
    )
    cognito = CognitoRepository(boto3.client("cognito-idp"), get_user_pool_id())
    return DeactivationService(
        users,
        saga,
        cognito,
        environment=get_environment(),
        audit_retention_days=get_audit_retention_days(),
    )


@lru_cache
def get_reactivation_service() -> ReactivationService:
    import time

    dynamodb_client = boto3.client("dynamodb")
    dynamodb_resource = boto3.resource("dynamodb")
    saga_table: Any = dynamodb_resource.Table(get_idempotency_table_name())
    users = UserRepository(
        dynamodb_client,
        get_users_table_name(),
        get_audit_table_name(),
    )
    saga = InvitationSagaRepository(
        saga_table,
        get_idempotency_table_name(),
        clock=time.time,
    )
    cognito = CognitoRepository(boto3.client("cognito-idp"), get_user_pool_id())
    return ReactivationService(
        users,
        saga,
        cognito,
        environment=get_environment(),
        audit_retention_days=get_audit_retention_days(),
    )
