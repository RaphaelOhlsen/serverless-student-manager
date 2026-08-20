from dataclasses import replace
from datetime import timedelta
from typing import Protocol

from tools.bootstrap_admin.audit import build_user_created_audit_event
from tools.bootstrap_admin.aws_errors import (
    get_aws_error_code,
    is_ambiguous_aws_transport_error,
    is_ambiguous_dynamodb_write_error,
)
from tools.bootstrap_admin.clock import Clock, format_utc_rfc3339_millis, to_epoch_seconds
from tools.bootstrap_admin.cognito_repository import (
    CognitoCreateResultError,
    CognitoIdentityValidationError,
)
from tools.bootstrap_admin.context import BootstrapContext, parse_bootstrap_context
from tools.bootstrap_admin.idempotency import (
    build_started_record,
    validate_existing_record,
)
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
    BootstrapTerminalState,
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
    def get_existing_user_sub(
        self,
        *,
        user_pool_id: str,
        user_id: str,
        expected_email: str,
    ) -> str: ...

    def create_suppressed_user(
        self,
        *,
        user_pool_id: str,
        user_id: str,
        email: str,
    ) -> str: ...

    def resend_invitation(self, *, user_pool_id: str, user_id: str) -> None: ...

    def delete_user(self, *, user_pool_id: str, user_id: str) -> None: ...

    def disable_user(self, *, user_pool_id: str, user_id: str) -> None: ...


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

    def get_user_profile(
        self,
        *,
        users_table_name: str,
        user_id: str,
    ) -> dict[str, object] | None: ...

    def get_unique_email(
        self,
        *,
        users_table_name: str,
        normalized_email: str,
    ) -> dict[str, object] | None: ...

    def get_cognito_projection(
        self,
        *,
        users_table_name: str,
        cognito_sub: str,
    ) -> dict[str, object] | None: ...

    def get_bootstrap_marker(
        self,
        *,
        users_table_name: str,
    ) -> dict[str, object] | None: ...

    def get_audit_event(
        self,
        *,
        audit_table_name: str,
        user_id: str,
        occurred_at: str,
        event_id: str,
    ) -> dict[str, object] | None: ...


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

        existing = self._idempotency_repository.get(record_id)
        if existing is not None:
            context = parse_bootstrap_context(
                existing,
                expected_environment=self._config.environment,
                expected_operation_id=operation_id,
            )
            validate_existing_record(
                existing,
                full_name=full_name,
                normalized_email=normalized_email,
            )
            return self._replay(
                context,
                full_name=full_name,
                normalized_email=normalized_email,
            )

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

    def _replay(
        self,
        context: BootstrapContext,
        *,
        full_name: str,
        normalized_email: str,
    ) -> BootstrapResult:
        if context.state == "COMPLETED":
            return self._replay_result(context, state="COMPLETED")
        if context.state == "COMPENSATED":
            return self._replay_result(context, state="COMPENSATED")
        if context.state == "RECONCILIATION_REQUIRED":
            return self._replay_result(context, state="RECONCILIATION_REQUIRED")
        if context.state == "INVITATION_SENT":
            self._transition(
                record_id=context.record_id,
                current_state="INVITATION_SENT",
                next_state="COMPLETED",
            )
            return self._replay_result(context, state="COMPLETED")
        if context.state == "PERSISTENCE_COMPLETED":
            return self._complete_after_persistence(context)
        if context.state == "STARTED":
            return self._replay_started(
                context,
                full_name=full_name,
                normalized_email=normalized_email,
            )
        return self._replay_cognito_created(
            context,
            full_name=full_name,
            normalized_email=normalized_email,
        )

    def _replay_cognito_created(
        self,
        context: BootstrapContext,
        *,
        full_name: str,
        normalized_email: str,
    ) -> BootstrapResult:
        cognito_sub = context.cognito_sub
        if cognito_sub is None:
            raise AssertionError("COGNITO_CREATED context requires cognito_sub")

        try:
            existing_sub = self._get_existing_user_sub(
                context,
                normalized_email=normalized_email,
            )
        except CognitoIdentityValidationError:
            return self._mark_reconciliation_required(
                context,
                current_state="COGNITO_CREATED",
            )
        except Exception as read_error:
            if get_aws_error_code(read_error) == "UserNotFoundException":
                return self._reconcile_missing_cognito(
                    context,
                    full_name=full_name,
                    normalized_email=normalized_email,
                    cognito_sub=cognito_sub,
                )
            raise

        if existing_sub != cognito_sub:
            return self._mark_reconciliation_required(
                context,
                current_state="COGNITO_CREATED",
            )

        return self._continue_cognito_created(
            context,
            full_name=full_name,
            normalized_email=normalized_email,
            cognito_sub=cognito_sub,
        )

    def _continue_cognito_created(
        self,
        context: BootstrapContext,
        *,
        full_name: str,
        normalized_email: str,
        cognito_sub: str,
    ) -> BootstrapResult:
        expected_items = self._build_replay_items(
            context,
            full_name=full_name,
            normalized_email=normalized_email,
            cognito_sub=cognito_sub,
        )
        actual_items = self._read_provisioning_items(
            context,
            normalized_email=normalized_email,
            cognito_sub=cognito_sub,
        )
        persistence_state = self._classify_persistence_state(
            context,
            expected_items=expected_items,
            actual_items=actual_items,
        )

        if persistence_state == "ALL_ABSENT":
            try:
                self._persist_replay_items(context, expected_items)
            except Exception as write_error:
                if (
                    get_aws_error_code(write_error) != "TransactionCanceledException"
                    and not is_ambiguous_dynamodb_write_error(write_error)
                ):
                    raise
                actual_items = self._read_provisioning_items(
                    context,
                    normalized_email=normalized_email,
                    cognito_sub=cognito_sub,
                )
                persistence_state = self._classify_persistence_state(
                    context,
                    expected_items=expected_items,
                    actual_items=actual_items,
                )
                if persistence_state == "ALL_ABSENT":
                    raise
        if persistence_state == "FOREIGN_MARKER":
            return self._handle_foreign_marker(context, marker=actual_items[3])
        if persistence_state == "PARTIAL_OR_INCOMPATIBLE":
            return self._mark_reconciliation_required(
                context,
                current_state="COGNITO_CREATED",
            )

        self._transition(
            record_id=context.record_id,
            current_state="COGNITO_CREATED",
            next_state="PERSISTENCE_COMPLETED",
        )
        return self._complete_after_persistence(context)

    def _classify_persistence_state(
        self,
        context: BootstrapContext,
        *,
        expected_items: tuple[
            dict[str, object],
            dict[str, object],
            dict[str, object],
            dict[str, object],
            dict[str, object],
        ],
        actual_items: tuple[
            dict[str, object] | None,
            dict[str, object] | None,
            dict[str, object] | None,
            dict[str, object] | None,
            dict[str, object] | None,
        ],
    ) -> str:
        if all(item is None for item in actual_items):
            return "ALL_ABSENT"
        if self._marker_belongs_to_other_operation(context, actual_items[3]):
            return "FOREIGN_MARKER"
        if actual_items == expected_items:
            return "OUR_COMPLETE_PERSISTENCE"
        return "PARTIAL_OR_INCOMPATIBLE"

    @staticmethod
    def _validated_marker_identity(
        marker: dict[str, object] | None,
    ) -> tuple[str, str] | None:
        if marker is None:
            return None
        if marker.get("PK") != "CONTROL#FIRST_ADMIN_BOOTSTRAP":
            return None
        if marker.get("SK") != "CONTROL":
            return None

        user_id = marker.get("userId")
        operation_id = marker.get("operationId")
        created_at = marker.get("createdAt")
        created_by = marker.get("createdBy")
        if not isinstance(user_id, str) or user_id == "":
            return None
        if not isinstance(operation_id, str) or operation_id == "":
            return None
        if not isinstance(created_at, str) or created_at == "":
            return None
        if not isinstance(created_by, str) or created_by == "":
            return None
        try:
            validate_uuid4(user_id)
            validate_uuid4(operation_id)
        except ValueError:
            return None
        return user_id, operation_id

    @classmethod
    def _marker_belongs_to_other_operation(
        cls,
        context: BootstrapContext,
        marker: dict[str, object] | None,
    ) -> bool:
        marker_identity = cls._validated_marker_identity(marker)
        if marker_identity is None:
            return False
        user_id, operation_id = marker_identity
        return user_id != context.user_id or operation_id != context.operation_id

    @classmethod
    def _marker_authorizes_compensation(
        cls,
        context: BootstrapContext,
        marker: dict[str, object] | None,
    ) -> bool:
        marker_identity = cls._validated_marker_identity(marker)
        if marker_identity is None:
            return False
        user_id, operation_id = marker_identity
        return user_id != context.user_id and operation_id != context.operation_id

    def _handle_foreign_marker(
        self,
        context: BootstrapContext,
        *,
        marker: dict[str, object] | None,
    ) -> BootstrapResult:
        if self._marker_authorizes_compensation(context, marker):
            return self._compensate_current_identity(context)
        return self._mark_reconciliation_required(
            context,
            current_state="COGNITO_CREATED",
        )

    def _reconcile_missing_cognito(
        self,
        context: BootstrapContext,
        *,
        full_name: str,
        normalized_email: str,
        cognito_sub: str,
    ) -> BootstrapResult:
        expected_items = self._build_replay_items(
            context,
            full_name=full_name,
            normalized_email=normalized_email,
            cognito_sub=cognito_sub,
        )
        actual_items = self._read_provisioning_items(
            context,
            normalized_email=normalized_email,
            cognito_sub=cognito_sub,
        )
        persistence_state = self._classify_persistence_state(
            context,
            expected_items=expected_items,
            actual_items=actual_items,
        )
        if persistence_state == "FOREIGN_MARKER" and self._marker_authorizes_compensation(
            context,
            actual_items[3],
        ):
            return self._mark_compensated(context)
        return self._mark_reconciliation_required(
            context,
            current_state="COGNITO_CREATED",
        )

    def _compensate_current_identity(
        self,
        context: BootstrapContext,
    ) -> BootstrapResult:
        try:
            self._cognito_repository.delete_user(
                user_pool_id=self._config.user_pool_id,
                user_id=context.user_id,
            )
        except Exception as delete_error:
            if get_aws_error_code(delete_error) == "UserNotFoundException":
                return self._mark_compensated(context)
            try:
                self._cognito_repository.disable_user(
                    user_pool_id=self._config.user_pool_id,
                    user_id=context.user_id,
                )
            except Exception as disable_error:
                if get_aws_error_code(disable_error) == "UserNotFoundException":
                    return self._mark_compensated(context)
                return self._mark_reconciliation_required(
                    context,
                    current_state="COGNITO_CREATED",
                )
            return self._mark_reconciliation_required(
                context,
                current_state="COGNITO_CREATED",
            )
        return self._mark_compensated(context)

    def _build_replay_items(
        self,
        context: BootstrapContext,
        *,
        full_name: str,
        normalized_email: str,
        cognito_sub: str,
    ) -> tuple[
        dict[str, object],
        dict[str, object],
        dict[str, object],
        dict[str, object],
        dict[str, object],
    ]:
        return (
            build_user_profile(
                user_id=context.user_id,
                cognito_sub=cognito_sub,
                full_name=full_name,
                email=normalized_email,
                created_at=context.created_at,
                created_by=context.actor_id,
            ),
            build_unique_email(
                user_id=context.user_id,
                email=normalized_email,
            ),
            build_cognito_projection(
                user_id=context.user_id,
                cognito_sub=cognito_sub,
            ),
            build_first_admin_bootstrap_marker(
                user_id=context.user_id,
                operation_id=context.operation_id,
                created_at=context.created_at,
                created_by=context.actor_id,
            ),
            build_user_created_audit_event(
                user_id=context.user_id,
                actor_id=context.actor_id,
                event_id=context.event_id,
                correlation_id=context.correlation_id,
                occurred_at=context.occurred_at,
                expires_at=context.audit_expires_at,
            ),
        )

    def _read_provisioning_items(
        self,
        context: BootstrapContext,
        *,
        normalized_email: str,
        cognito_sub: str,
    ) -> tuple[
        dict[str, object] | None,
        dict[str, object] | None,
        dict[str, object] | None,
        dict[str, object] | None,
        dict[str, object] | None,
    ]:
        return (
            self._provisioning_repository.get_user_profile(
                users_table_name=self._config.users_table_name,
                user_id=context.user_id,
            ),
            self._provisioning_repository.get_unique_email(
                users_table_name=self._config.users_table_name,
                normalized_email=normalized_email,
            ),
            self._provisioning_repository.get_cognito_projection(
                users_table_name=self._config.users_table_name,
                cognito_sub=cognito_sub,
            ),
            self._provisioning_repository.get_bootstrap_marker(
                users_table_name=self._config.users_table_name,
            ),
            self._provisioning_repository.get_audit_event(
                audit_table_name=self._config.audit_table_name,
                user_id=context.user_id,
                occurred_at=context.occurred_at,
                event_id=context.event_id,
            ),
        )

    def _persist_replay_items(
        self,
        context: BootstrapContext,
        items: tuple[
            dict[str, object],
            dict[str, object],
            dict[str, object],
            dict[str, object],
            dict[str, object],
        ],
    ) -> None:
        (
            user_profile,
            unique_email,
            cognito_projection,
            bootstrap_marker,
            audit_event,
        ) = items
        self._provisioning_repository.persist_first_admin_with_audit(
            users_table_name=self._config.users_table_name,
            audit_table_name=self._config.audit_table_name,
            user_profile=user_profile,
            unique_email=unique_email,
            cognito_projection=cognito_projection,
            bootstrap_marker=bootstrap_marker,
            audit_event=audit_event,
            client_request_token=context.operation_id,
        )

    def _complete_after_persistence(
        self,
        context: BootstrapContext,
    ) -> BootstrapResult:
        self._cognito_repository.resend_invitation(
            user_pool_id=self._config.user_pool_id,
            user_id=context.user_id,
        )
        self._transition(
            record_id=context.record_id,
            current_state="PERSISTENCE_COMPLETED",
            next_state="INVITATION_SENT",
        )
        self._transition(
            record_id=context.record_id,
            current_state="INVITATION_SENT",
            next_state="COMPLETED",
        )
        return self._replay_result(context, state="COMPLETED")

    def _replay_started(
        self,
        context: BootstrapContext,
        *,
        full_name: str,
        normalized_email: str,
    ) -> BootstrapResult:
        try:
            cognito_sub = self._get_existing_user_sub(
                context,
                normalized_email=normalized_email,
            )
        except CognitoIdentityValidationError:
            return self._mark_reconciliation_required(
                context,
                current_state="STARTED",
            )
        except Exception as read_error:
            if get_aws_error_code(read_error) != "UserNotFoundException":
                raise
        else:
            return self._adopt_cognito_user(
                context,
                full_name=full_name,
                normalized_email=normalized_email,
                cognito_sub=cognito_sub,
            )

        try:
            cognito_sub = self._cognito_repository.create_suppressed_user(
                user_pool_id=self._config.user_pool_id,
                user_id=context.user_id,
                email=normalized_email,
            )
        except Exception as create_error:
            create_error_code = get_aws_error_code(create_error)
            if (
                create_error_code not in {
                "UsernameExistsException",
                "AliasExistsException",
                "InternalErrorException",
                }
                and not isinstance(create_error, CognitoCreateResultError)
                and not is_ambiguous_aws_transport_error(create_error)
            ):
                raise
            return self._reconcile_after_create_error(
                context,
                full_name=full_name,
                normalized_email=normalized_email,
                create_error=create_error,
            )

        return self._adopt_cognito_user(
            context,
            full_name=full_name,
            normalized_email=normalized_email,
            cognito_sub=cognito_sub,
        )

    def _reconcile_after_create_error(
        self,
        context: BootstrapContext,
        *,
        full_name: str,
        normalized_email: str,
        create_error: Exception,
    ) -> BootstrapResult:
        try:
            cognito_sub = self._get_existing_user_sub(
                context,
                normalized_email=normalized_email,
            )
        except CognitoIdentityValidationError:
            return self._mark_reconciliation_required(
                context,
                current_state="STARTED",
            )
        except Exception as read_error:
            if get_aws_error_code(read_error) != "UserNotFoundException":
                raise
            if get_aws_error_code(create_error) == "AliasExistsException":
                return self._mark_reconciliation_required(
                    context,
                    current_state="STARTED",
                )
            raise create_error from None

        return self._adopt_cognito_user(
            context,
            full_name=full_name,
            normalized_email=normalized_email,
            cognito_sub=cognito_sub,
        )

    def _get_existing_user_sub(
        self,
        context: BootstrapContext,
        *,
        normalized_email: str,
    ) -> str:
        return self._cognito_repository.get_existing_user_sub(
            user_pool_id=self._config.user_pool_id,
            user_id=context.user_id,
            expected_email=normalized_email,
        )

    def _adopt_cognito_user(
        self,
        context: BootstrapContext,
        *,
        full_name: str,
        normalized_email: str,
        cognito_sub: str,
    ) -> BootstrapResult:
        self._transition(
            record_id=context.record_id,
            current_state="STARTED",
            next_state="COGNITO_CREATED",
            cognito_sub=cognito_sub,
        )
        return self._continue_cognito_created(
            replace(context, state="COGNITO_CREATED", cognito_sub=cognito_sub),
            full_name=full_name,
            normalized_email=normalized_email,
            cognito_sub=cognito_sub,
        )

    def _mark_reconciliation_required(
        self,
        context: BootstrapContext,
        *,
        current_state: str,
    ) -> BootstrapResult:
        self._transition(
            record_id=context.record_id,
            current_state=current_state,
            next_state="RECONCILIATION_REQUIRED",
        )
        return self._replay_result(context, state="RECONCILIATION_REQUIRED")

    def _mark_compensated(self, context: BootstrapContext) -> BootstrapResult:
        self._transition(
            record_id=context.record_id,
            current_state="COGNITO_CREATED",
            next_state="COMPENSATED",
        )
        return self._replay_result(context, state="COMPENSATED")

    @staticmethod
    def _replay_result(
        context: BootstrapContext,
        *,
        state: BootstrapTerminalState,
    ) -> BootstrapResult:
        return BootstrapResult(
            operation_id=context.operation_id,
            user_id=context.user_id,
            state=state,
            replayed=True,
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
