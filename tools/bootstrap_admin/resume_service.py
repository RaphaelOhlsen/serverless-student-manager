from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from tools.bootstrap_admin.aws_errors import (
    get_aws_error_code,
    is_ambiguous_dynamodb_write_error,
)
from tools.bootstrap_admin.clock import Clock, format_utc_rfc3339_millis, to_epoch_seconds
from tools.bootstrap_admin.ids import IdGenerator, validate_uuid4
from tools.bootstrap_admin.resume_context import (
    ResumeInvitationContext,
    parse_resume_invitation_context,
)
from tools.bootstrap_admin.resume_discovery import ResumeDiscoveryResult
from tools.bootstrap_admin.resume_idempotency import (
    build_resume_invitation_started_record,
    validate_resume_invitation_existing_record,
)
from tools.bootstrap_admin.service_models import (
    ResumeInvitationResult,
    ResumeInvitationTerminalState,
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


class InvitationSender(Protocol):
    def resend_invitation(self, *, user_pool_id: str, user_id: str) -> None: ...


class ResumeDiscovery(Protocol):
    def discover(self, *, resume_operation_id: str) -> ResumeDiscoveryResult: ...


@dataclass(frozen=True)
class ResumeInvitationServiceConfig:
    environment: str
    user_pool_id: str

    def __post_init__(self) -> None:
        if self.environment == "":
            raise ValueError("environment must be a non-empty string")
        if self.user_pool_id == "":
            raise ValueError("user_pool_id must be a non-empty string")


class ResumeInvitationService:
    def __init__(
        self,
        *,
        config: ResumeInvitationServiceConfig,
        clock: Clock,
        id_generator: IdGenerator,
        idempotency_repository: IdempotencyRepository,
        invitation_sender: InvitationSender,
        discovery: ResumeDiscovery,
    ) -> None:
        self._config = config
        self._clock = clock
        self._id_generator = id_generator
        self._idempotency_repository = idempotency_repository
        self._invitation_sender = invitation_sender
        self._discovery = discovery

    def resume_first_admin_invitation(
        self,
        *,
        operation_id: str,
        actor_id: str,
    ) -> ResumeInvitationResult:
        validate_uuid4(operation_id)
        if actor_id == "":
            raise ValueError("actor_id must be a non-empty string")

        record_id = (
            f"NONHTTP#{self._config.environment}#resume-first-admin-invitation#"
            f"first-admin#{operation_id}"
        )
        existing = self._idempotency_repository.get(record_id)
        if existing is not None:
            context = self._parse_and_validate(existing, operation_id=operation_id)
            return self._continue(context, replayed=True)

        correlation_id = validate_uuid4(self._id_generator.new_uuid4())
        base = self._clock.now()
        created_at = format_utc_rfc3339_millis(base)
        expiration = to_epoch_seconds(base + timedelta(hours=24))
        started_record = build_resume_invitation_started_record(
            environment=self._config.environment,
            operation_id=operation_id,
            correlation_id=correlation_id,
            actor_id=actor_id,
            created_at=created_at,
            expiration=expiration,
        )
        attempted_context = self._parse_and_validate(
            started_record,
            operation_id=operation_id,
        )

        try:
            self._idempotency_repository.create_started(started_record)
        except Exception as create_error:
            if not self._should_reconcile_write_error(create_error):
                raise
            context = self._reconcile_create_error(
                create_error,
                record_id=record_id,
                operation_id=operation_id,
            )
            replayed = not self._has_same_start_metadata(
                context,
                attempted_context,
            )
            return self._continue(context, replayed=replayed)

        return self._continue(attempted_context, replayed=False)

    def _continue(
        self,
        context: ResumeInvitationContext,
        *,
        replayed: bool,
    ) -> ResumeInvitationResult:
        if context.state == "COMPLETED":
            return self._result(context, state="COMPLETED", replayed=replayed)
        if context.state == "RECONCILIATION_REQUIRED":
            return self._result(
                context,
                state="RECONCILIATION_REQUIRED",
                replayed=replayed,
            )

        discovery = self._discovery.discover(
            resume_operation_id=context.operation_id,
        )
        if discovery.status == "RECONCILIATION_REQUIRED":
            return self._transition_to_result(
                context,
                state="RECONCILIATION_REQUIRED",
                replayed=replayed,
            )
        if discovery.status == "ACTIVE_CONSISTENT":
            return self._transition_to_result(
                context,
                state="COMPLETED",
                replayed=replayed,
            )

        target = discovery.target
        assert target is not None
        try:
            self._invitation_sender.resend_invitation(
                user_pool_id=self._config.user_pool_id,
                user_id=target.user_id,
            )
        except Exception as resend_error:
            if get_aws_error_code(resend_error) != "UserNotFoundException":
                raise
            return self._transition_to_result(
                context,
                state="RECONCILIATION_REQUIRED",
                replayed=replayed,
            )

        return self._transition_to_result(
            context,
            state="COMPLETED",
            replayed=replayed,
        )

    def _transition_to_result(
        self,
        context: ResumeInvitationContext,
        *,
        state: ResumeInvitationTerminalState,
        replayed: bool,
    ) -> ResumeInvitationResult:
        self._transition(
            context,
            next_state=state,
        )
        return self._result(context, state=state, replayed=replayed)

    def _transition(
        self,
        context: ResumeInvitationContext,
        *,
        next_state: ResumeInvitationTerminalState,
    ) -> None:
        updated_at = format_utc_rfc3339_millis(self._clock.now())
        try:
            self._idempotency_repository.transition_state(
                record_id=context.record_id,
                operation="resume-first-admin-invitation",
                current_state="STARTED",
                next_state=next_state,
                updated_at=updated_at,
            )
        except Exception as transition_error:
            if not self._should_reconcile_write_error(transition_error):
                raise
            self._reconcile_transition_error(
                transition_error,
                record_id=context.record_id,
                operation_id=context.operation_id,
                next_state=next_state,
            )

    def _reconcile_create_error(
        self,
        create_error: Exception,
        *,
        record_id: str,
        operation_id: str,
    ) -> ResumeInvitationContext:
        record = self._idempotency_repository.get(record_id)
        if record is None:
            raise create_error
        return self._parse_and_validate(record, operation_id=operation_id)

    def _reconcile_transition_error(
        self,
        transition_error: Exception,
        *,
        record_id: str,
        operation_id: str,
        next_state: ResumeInvitationTerminalState,
    ) -> None:
        record = self._idempotency_repository.get(record_id)
        if record is None:
            raise transition_error
        context = self._parse_and_validate(record, operation_id=operation_id)
        if context.state != next_state:
            raise transition_error

    def _parse_and_validate(
        self,
        record: dict[str, object],
        *,
        operation_id: str,
    ) -> ResumeInvitationContext:
        context = parse_resume_invitation_context(
            record,
            expected_environment=self._config.environment,
            expected_operation_id=operation_id,
        )
        validate_resume_invitation_existing_record(record)
        return context

    @staticmethod
    def _has_same_start_metadata(
        persisted: ResumeInvitationContext,
        attempted: ResumeInvitationContext,
    ) -> bool:
        return (
            persisted.correlation_id == attempted.correlation_id
            and persisted.actor_id == attempted.actor_id
            and persisted.created_at == attempted.created_at
            and persisted.expiration == attempted.expiration
        )

    @staticmethod
    def _should_reconcile_write_error(error: BaseException) -> bool:
        return get_aws_error_code(
            error
        ) == "ConditionalCheckFailedException" or is_ambiguous_dynamodb_write_error(error)

    @staticmethod
    def _result(
        context: ResumeInvitationContext,
        *,
        state: ResumeInvitationTerminalState,
        replayed: bool,
    ) -> ResumeInvitationResult:
        return ResumeInvitationResult(
            operation_id=context.operation_id,
            state=state,
            replayed=replayed,
        )
