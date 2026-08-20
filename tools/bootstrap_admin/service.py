from datetime import timedelta
from typing import Protocol

from tools.bootstrap_admin.audit import build_user_created_audit_event
from tools.bootstrap_admin.clock import Clock, format_utc_rfc3339_millis, to_epoch_seconds
from tools.bootstrap_admin.idempotency import build_started_record
from tools.bootstrap_admin.ids import IdGenerator, validate_uuid4
from tools.bootstrap_admin.models import (
    build_cognito_projection,
    build_first_admin_bootstrap_marker,
    build_unique_email,
    build_user_profile,
)
from tools.bootstrap_admin.normalization import normalize_email, normalize_name
from tools.bootstrap_admin.service_models import (
    BootstrapResult,
    FirstAdminBootstrapConfig,
)


class IdempotencyRepository(Protocol):
    def get(self, record_id: str) -> dict[str, object] | None: ...

    def create_started(self, record: dict[str, object]) -> None: ...

    def transition_state(
        self,
        *,
        record_id: str,
        operation: str,
        current_state: str,
        next_state: str,
        updated_at: str,
        cognito_sub: str | None = None,
    ) -> None: ...


class CognitoRepository(Protocol):
    def create_suppressed_user(
        self,
        *,
        user_pool_id: str,
        user_id: str,
        email: str,
    ) -> str: ...

    def resend_invitation(self, *, user_pool_id: str, user_id: str) -> None: ...


class ProvisioningRepository(Protocol):
    def persist_first_admin_with_audit(
        self,
        *,
        users_table_name: str,
        audit_table_name: str,
        user_profile: dict[str, object],
        unique_email: dict[str, object],
        cognito_projection: dict[str, object],
        bootstrap_marker: dict[str, object],
        audit_event: dict[str, object],
        client_request_token: str,
    ) -> None: ...


class FirstAdminBootstrapService:
    def __init__(
        self,
        *,
        config: FirstAdminBootstrapConfig,
        clock: Clock,
        id_generator: IdGenerator,
        idempotency_repository: IdempotencyRepository,
        cognito_repository: CognitoRepository,
        provisioning_repository: ProvisioningRepository,
    ) -> None:
        self._config = config
        self._clock = clock
        self._id_generator = id_generator
        self._idempotency_repository = idempotency_repository
        self._cognito_repository = cognito_repository
        self._provisioning_repository = provisioning_repository

    def bootstrap_first_admin(
        self,
        *,
        full_name: str,
        email: str,
        operation_id: str,
        actor_id: str,
    ) -> BootstrapResult:
        validate_uuid4(operation_id)
        if actor_id == "":
            raise ValueError("actor_id must be a non-empty string")

        normalize_name(full_name)
        normalized_email = normalize_email(email)
        record_id = (
            f"NONHTTP#{self._config.environment}#bootstrap-admin#first-admin#"
            f"{operation_id}"
        )

        if self._idempotency_repository.get(record_id) is not None:
            raise NotImplementedError("replay is not implemented")

        user_id = validate_uuid4(self._id_generator.new_uuid4())
        event_id = validate_uuid4(self._id_generator.new_uuid4())
        correlation_id = validate_uuid4(self._id_generator.new_uuid4())

        base = self._clock.now()
        created_at = format_utc_rfc3339_millis(base)
        occurred_at = created_at
        expiration = to_epoch_seconds(base + timedelta(hours=24))
        audit_expires_at = to_epoch_seconds(
            base + timedelta(days=self._config.audit_retention_days)
        )

        started_record = build_started_record(
            environment=self._config.environment,
            operation_id=operation_id,
            correlation_id=correlation_id,
            user_id=user_id,
            event_id=event_id,
            full_name=full_name,
            normalized_email=normalized_email,
            created_at=created_at,
            occurred_at=occurred_at,
            audit_expires_at=audit_expires_at,
            actor_id=actor_id,
            expiration=expiration,
        )
        self._idempotency_repository.create_started(started_record)

        cognito_sub = self._cognito_repository.create_suppressed_user(
            user_pool_id=self._config.user_pool_id,
            user_id=user_id,
            email=normalized_email,
        )
        self._transition(
            record_id=record_id,
            current_state="STARTED",
            next_state="COGNITO_CREATED",
            cognito_sub=cognito_sub,
        )

        user_profile = build_user_profile(
            user_id=user_id,
            cognito_sub=cognito_sub,
            full_name=full_name,
            email=normalized_email,
            created_at=created_at,
            created_by=actor_id,
        )
        unique_email = build_unique_email(
            user_id=user_id,
            email=normalized_email,
        )
        cognito_projection = build_cognito_projection(
            user_id=user_id,
            cognito_sub=cognito_sub,
        )
        bootstrap_marker = build_first_admin_bootstrap_marker(
            user_id=user_id,
            operation_id=operation_id,
            created_at=created_at,
            created_by=actor_id,
        )
        audit_event = build_user_created_audit_event(
            user_id=user_id,
            actor_id=actor_id,
            event_id=event_id,
            correlation_id=correlation_id,
            occurred_at=occurred_at,
            expires_at=audit_expires_at,
        )
        self._provisioning_repository.persist_first_admin_with_audit(
            users_table_name=self._config.users_table_name,
            audit_table_name=self._config.audit_table_name,
            user_profile=user_profile,
            unique_email=unique_email,
            cognito_projection=cognito_projection,
            bootstrap_marker=bootstrap_marker,
            audit_event=audit_event,
            client_request_token=operation_id,
        )

        self._transition(
            record_id=record_id,
            current_state="COGNITO_CREATED",
            next_state="PERSISTENCE_COMPLETED",
        )
        self._cognito_repository.resend_invitation(
            user_pool_id=self._config.user_pool_id,
            user_id=user_id,
        )
        self._transition(
            record_id=record_id,
            current_state="PERSISTENCE_COMPLETED",
            next_state="INVITATION_SENT",
        )
        self._transition(
            record_id=record_id,
            current_state="INVITATION_SENT",
            next_state="COMPLETED",
        )

        return BootstrapResult(
            operation_id=operation_id,
            user_id=user_id,
            state="COMPLETED",
            replayed=False,
        )

    def _transition(
        self,
        *,
        record_id: str,
        current_state: str,
        next_state: str,
        cognito_sub: str | None = None,
    ) -> None:
        updated_at = format_utc_rfc3339_millis(self._clock.now())
        if cognito_sub is None:
            self._idempotency_repository.transition_state(
                record_id=record_id,
                operation="bootstrap-admin",
                current_state=current_state,
                next_state=next_state,
                updated_at=updated_at,
            )
            return

        self._idempotency_repository.transition_state(
            record_id=record_id,
            operation="bootstrap-admin",
            current_state=current_state,
            next_state=next_state,
            updated_at=updated_at,
            cognito_sub=cognito_sub,
        )
