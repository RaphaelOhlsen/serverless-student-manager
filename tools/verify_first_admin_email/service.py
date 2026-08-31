from dataclasses import dataclass
from datetime import timedelta
from typing import Literal, Protocol

from tools.bootstrap_admin.aws_errors import (
    get_aws_error_code,
    is_ambiguous_aws_transport_error,
    is_ambiguous_dynamodb_write_error,
)
from tools.bootstrap_admin.clock import Clock, format_utc_rfc3339_millis, to_epoch_seconds
from tools.bootstrap_admin.ids import IdGenerator, validate_uuid4
from tools.verify_first_admin_email.audit import (
    VerifyFirstAdminEmailAuditResult,
    audit_event_matches,
    build_first_admin_email_verification_audit_event,
)
from tools.verify_first_admin_email.context import (
    VerifyFirstAdminEmailContext,
    parse_verify_first_admin_email_context,
)
from tools.verify_first_admin_email.discovery import (
    FirstAdminEmailTarget,
    VerifyFirstAdminEmailDiscoveryResult,
)
from tools.verify_first_admin_email.idempotency import (
    build_verify_first_admin_email_started_record,
    validate_verify_first_admin_email_existing_record,
)

VerifyFirstAdminEmailTerminalState = Literal[
    "COMPLETED",
    "RECONCILIATION_REQUIRED",
]


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
    ) -> None: ...


class Discovery(Protocol):
    def discover(self) -> VerifyFirstAdminEmailDiscoveryResult: ...


class CognitoRepository(Protocol):
    def set_email_verified(self, *, user_pool_id: str, user_id: str) -> None: ...


class AuditRepository(Protocol):
    def put_event(
        self,
        *,
        audit_table_name: str,
        event: dict[str, object],
    ) -> None: ...

    def get_event(
        self,
        *,
        audit_table_name: str,
        user_id: str,
        occurred_at: str,
        event_id: str,
    ) -> dict[str, object] | None: ...


@dataclass(frozen=True)
class VerifyFirstAdminEmailServiceConfig:
    environment: str
    user_pool_id: str
    audit_table_name: str
    audit_retention_days: int

    def __post_init__(self) -> None:
        for field_name, value in (
            ("environment", self.environment),
            ("user_pool_id", self.user_pool_id),
            ("audit_table_name", self.audit_table_name),
        ):
            if value == "":
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.audit_retention_days <= 0:
            raise ValueError("audit_retention_days must be greater than zero")


@dataclass(frozen=True)
class VerifyFirstAdminEmailResult:
    operation_id: str
    state: VerifyFirstAdminEmailTerminalState
    replayed: bool


class VerifyFirstAdminEmailService:
    def __init__(
        self,
        *,
        config: VerifyFirstAdminEmailServiceConfig,
        clock: Clock,
        id_generator: IdGenerator,
        idempotency_repository: IdempotencyRepository,
        discovery: Discovery,
        cognito_repository: CognitoRepository,
        audit_repository: AuditRepository,
    ) -> None:
        self._config = config
        self._clock = clock
        self._id_generator = id_generator
        self._idempotency_repository = idempotency_repository
        self._discovery = discovery
        self._cognito_repository = cognito_repository
        self._audit_repository = audit_repository

    def verify_first_admin_email(
        self,
        *,
        operation_id: str,
        actor_id: str,
    ) -> VerifyFirstAdminEmailResult:
        validate_uuid4(operation_id)
        if actor_id == "":
            raise ValueError("actor_id must be a non-empty string")

        record_id = (
            f"NONHTTP#{self._config.environment}#verify-first-admin-email#"
            f"first-admin#{operation_id}"
        )
        existing = self._idempotency_repository.get(record_id)
        if existing is not None:
            context = self._parse_and_validate(existing, operation_id=operation_id)
            return self._continue(context, replayed=True)

        event_id = validate_uuid4(self._id_generator.new_uuid4())
        correlation_id = validate_uuid4(self._id_generator.new_uuid4())
        base = self._clock.now()
        occurred_at = format_utc_rfc3339_millis(base)
        started_record = build_verify_first_admin_email_started_record(
            environment=self._config.environment,
            operation_id=operation_id,
            event_id=event_id,
            correlation_id=correlation_id,
            actor_id=actor_id,
            occurred_at=occurred_at,
            audit_expires_at=to_epoch_seconds(
                base + timedelta(days=self._config.audit_retention_days)
            ),
            created_at=occurred_at,
            expiration=to_epoch_seconds(base + timedelta(hours=24)),
        )
        context = self._parse_and_validate(started_record, operation_id=operation_id)
        try:
            self._idempotency_repository.create_started(started_record)
        except Exception as create_error:
            if not self._should_reconcile_dynamodb_write(create_error):
                raise
            persisted = self._idempotency_repository.get(record_id)
            if persisted is None:
                raise create_error
            context = self._parse_and_validate(persisted, operation_id=operation_id)
            return self._continue(context, replayed=True)
        return self._continue(context, replayed=False)

    def _continue(
        self,
        context: VerifyFirstAdminEmailContext,
        *,
        replayed: bool,
    ) -> VerifyFirstAdminEmailResult:
        if context.state == "COMPLETED":
            return self._result(context, state="COMPLETED", replayed=replayed)
        if context.state == "RECONCILIATION_REQUIRED":
            return self._result(
                context,
                state="RECONCILIATION_REQUIRED",
                replayed=replayed,
            )

        discovery = self._discovery.discover()
        if discovery.status == "RECONCILIATION_REQUIRED":
            if discovery.authoritative_user_id is not None:
                return self._finish_with_audit(
                    context,
                    user_id=discovery.authoritative_user_id,
                    audit_result="FAILURE",
                    replayed=replayed,
                )
            return self._transition_to_result(
                context,
                state="RECONCILIATION_REQUIRED",
                replayed=replayed,
            )

        target = discovery.target
        assert target is not None

        if replayed:
            audit_result = self._terminal_state_from_existing_audit(context, target=target)
            if audit_result is not None:
                return self._transition_to_result(
                    context,
                    state=audit_result,
                    replayed=True,
                )

        if discovery.status == "ALREADY_VERIFIED":
            return self._finish_with_audit(
                context,
                user_id=target.user_id,
                audit_result="SUCCESS",
                replayed=replayed,
            )

        mutation_error: Exception | None = None
        try:
            self._cognito_repository.set_email_verified(
                user_pool_id=self._config.user_pool_id,
                user_id=target.user_id,
            )
        except Exception as error:
            if get_aws_error_code(error) == "AliasExistsException":
                return self._finish_with_audit(
                    context,
                    user_id=target.user_id,
                    audit_result="FAILURE",
                    replayed=replayed,
                )
            if not self._should_reconcile_cognito_write(error):
                raise
            mutation_error = error

        try:
            read_back = self._discovery.discover()
        except Exception:
            return self._finish_with_audit(
                context,
                user_id=target.user_id,
                audit_result="FAILURE",
                replayed=replayed,
            )
        if read_back.status == "RECONCILIATION_REQUIRED":
            if read_back.authoritative_user_id is None:
                return self._transition_to_result(
                    context,
                    state="RECONCILIATION_REQUIRED",
                    replayed=replayed,
                )
            return self._finish_with_audit(
                context,
                user_id=read_back.authoritative_user_id,
                audit_result="FAILURE",
                replayed=replayed,
            )
        if read_back.target != target:
            return self._finish_with_audit(
                context,
                user_id=target.user_id,
                audit_result="FAILURE",
                replayed=replayed,
            )
        if read_back.status == "NEEDS_VERIFICATION":
            if mutation_error is not None:
                raise mutation_error
            raise RuntimeError("email verification was not confirmed")
        return self._finish_with_audit(
            context,
            user_id=target.user_id,
            audit_result="SUCCESS",
            replayed=replayed,
        )

    def _terminal_state_from_existing_audit(
        self,
        context: VerifyFirstAdminEmailContext,
        *,
        target: FirstAdminEmailTarget,
    ) -> VerifyFirstAdminEmailTerminalState | None:
        actual = self._audit_repository.get_event(
            audit_table_name=self._config.audit_table_name,
            user_id=target.user_id,
            occurred_at=context.occurred_at,
            event_id=context.event_id,
        )
        if actual is None:
            return None
        success = self._build_audit_event(
            context,
            user_id=target.user_id,
            result="SUCCESS",
        )
        if audit_event_matches(expected=success, actual=actual):
            return "COMPLETED"
        failure = self._build_audit_event(
            context,
            user_id=target.user_id,
            result="FAILURE",
        )
        if audit_event_matches(expected=failure, actual=actual):
            return "RECONCILIATION_REQUIRED"
        return "RECONCILIATION_REQUIRED"

    def _finish_with_audit(
        self,
        context: VerifyFirstAdminEmailContext,
        *,
        user_id: str,
        audit_result: VerifyFirstAdminEmailAuditResult,
        replayed: bool,
    ) -> VerifyFirstAdminEmailResult:
        expected = self._build_audit_event(
            context,
            user_id=user_id,
            result=audit_result,
        )
        put_error: Exception | None = None
        try:
            self._audit_repository.put_event(
                audit_table_name=self._config.audit_table_name,
                event=expected,
            )
        except Exception as error:
            if audit_result == "FAILURE" and not self._should_reconcile_dynamodb_write(error):
                return self._transition_to_result(
                    context,
                    state="RECONCILIATION_REQUIRED",
                    replayed=replayed,
                )
            if not self._should_reconcile_dynamodb_write(error):
                raise
            put_error = error

        try:
            actual = self._audit_repository.get_event(
                audit_table_name=self._config.audit_table_name,
                user_id=user_id,
                occurred_at=context.occurred_at,
                event_id=context.event_id,
            )
        except Exception:
            if audit_result == "FAILURE":
                return self._transition_to_result(
                    context,
                    state="RECONCILIATION_REQUIRED",
                    replayed=replayed,
                )
            raise
        confirmed = actual is not None and audit_event_matches(expected=expected, actual=actual)
        if put_error is not None and actual is None and audit_result == "SUCCESS":
            raise put_error
        if audit_result == "SUCCESS" and not confirmed:
            return self._transition_to_result(
                context,
                state="RECONCILIATION_REQUIRED",
                replayed=replayed,
            )
        return self._transition_to_result(
            context,
            state="COMPLETED" if audit_result == "SUCCESS" else "RECONCILIATION_REQUIRED",
            replayed=replayed,
        )

    @staticmethod
    def _build_audit_event(
        context: VerifyFirstAdminEmailContext,
        *,
        user_id: str,
        result: VerifyFirstAdminEmailAuditResult,
    ) -> dict[str, object]:
        return build_first_admin_email_verification_audit_event(
            user_id=user_id,
            actor_id=context.actor_id,
            event_id=context.event_id,
            operation_id=context.operation_id,
            correlation_id=context.correlation_id,
            occurred_at=context.occurred_at,
            result=result,
            expires_at=context.audit_expires_at,
        )

    def _transition_to_result(
        self,
        context: VerifyFirstAdminEmailContext,
        *,
        state: VerifyFirstAdminEmailTerminalState,
        replayed: bool,
    ) -> VerifyFirstAdminEmailResult:
        try:
            self._idempotency_repository.transition_state(
                record_id=context.record_id,
                operation="verify-first-admin-email",
                current_state="STARTED",
                next_state=state,
                updated_at=format_utc_rfc3339_millis(self._clock.now()),
            )
        except Exception as transition_error:
            if not self._should_reconcile_dynamodb_write(transition_error):
                raise
            persisted = self._idempotency_repository.get(context.record_id)
            if persisted is None:
                raise transition_error
            reconciled = self._parse_and_validate(
                persisted,
                operation_id=context.operation_id,
            )
            if reconciled.state != state:
                raise transition_error
        return self._result(context, state=state, replayed=replayed)

    @staticmethod
    def _should_reconcile_dynamodb_write(error: BaseException) -> bool:
        return get_aws_error_code(
            error
        ) == "ConditionalCheckFailedException" or is_ambiguous_dynamodb_write_error(error)

    @staticmethod
    def _should_reconcile_cognito_write(error: BaseException) -> bool:
        return get_aws_error_code(
            error
        ) == "InternalErrorException" or is_ambiguous_aws_transport_error(error)

    def _parse_and_validate(
        self,
        record: dict[str, object],
        *,
        operation_id: str,
    ) -> VerifyFirstAdminEmailContext:
        context = parse_verify_first_admin_email_context(
            record,
            expected_environment=self._config.environment,
            expected_operation_id=operation_id,
        )
        validate_verify_first_admin_email_existing_record(record)
        return context

    @staticmethod
    def _result(
        context: VerifyFirstAdminEmailContext,
        *,
        state: VerifyFirstAdminEmailTerminalState,
        replayed: bool,
    ) -> VerifyFirstAdminEmailResult:
        return VerifyFirstAdminEmailResult(
            operation_id=context.operation_id,
            state=state,
            replayed=replayed,
        )
