from datetime import datetime, timedelta
from typing import Protocol

from aws_lambda_powertools import Logger

from users_api.config import SERVICE_NAME
from users_api.errors import (
    AdminUserDataInvariantError,
    AdminUserForbiddenError,
    AdminUserNotFoundError,
    CognitoIdentityInvariantError,
    CognitoInvitationDeliveryError,
    CognitoResultAmbiguousError,
    CognitoServiceError,
    CognitoUserNotFoundError,
    InvitationDeliveryFailedError,
    InvitationDeliveryUncertainError,
    InvitationSagaInvariantError,
    UserInvitationReconciliationError,
    UserStateConflictError,
    UserVersionConflictError,
)
from users_api.repositories.cognito_repository import ReconciledCognitoIdentity
from users_api.services.invitation_saga import (
    INVITATION_DELIVERY_FAILED,
    INVITATION_DELIVERY_UNCERTAIN,
    ResendSagaState,
    SagaClaim,
    replay_from_record,
)
from users_api.services.user_state import UserStateReconciliationError, reconcile_user_state
from users_api.validation import parse_resend_invitation_body, validate_idempotency_key

logger = Logger(service=SERVICE_NAME)


class UserRepositoryProtocol(Protocol):
    def get_authorization(self, cognito_sub: str) -> dict[str, object] | None: ...

    def get_profile(self, user_id: str) -> dict[str, object] | None: ...

    def complete_invitation_resend(
        self,
        *,
        audit: dict[str, object],
        saga_transition: dict[str, object],
        client_request_token: str,
    ) -> None: ...


class SagaRepositoryProtocol(Protocol):
    def claim_resend(
        self,
        *,
        environment: str,
        actor_id: str,
        idempotency_key: str,
        user_id: str,
        expected_version: int,
        request_id: str | None,
    ) -> SagaClaim: ...

    def get(self, record_id: str) -> dict[str, object] | None: ...

    def transition(self, *, record: dict[str, object], next_state: str) -> None: ...

    def store_delivery_failure(
        self,
        *,
        record: dict[str, object],
        retryable_state: str,
        error_code: str,
    ) -> None: ...

    def build_resend_completion_transition(
        self,
        *,
        record: dict[str, object],
    ) -> dict[str, object]: ...


class CognitoRepositoryProtocol(Protocol):
    def admin_get_user(
        self,
        *,
        user_id: str,
        expected_email: str,
    ) -> ReconciledCognitoIdentity: ...

    def admin_resend_invitation(self, *, user_id: str) -> None: ...


class ResendInvitationService:
    def __init__(
        self,
        users: UserRepositoryProtocol,
        saga: SagaRepositoryProtocol,
        cognito: CognitoRepositoryProtocol,
        *,
        environment: str,
        audit_retention_days: int,
    ) -> None:
        self._users = users
        self._saga = saga
        self._cognito = cognito
        self._environment = environment
        self._audit_retention_days = audit_retention_days

    def resend_invitation(
        self,
        *,
        cognito_sub: str,
        user_id: str,
        idempotency_key: object,
        request_id: str | None,
        body: str,
    ) -> None:
        actor_id = self._authorize(cognito_sub)
        key = validate_idempotency_key(idempotency_key)
        request = parse_resend_invitation_body(body)
        claim = self._saga.claim_resend(
            environment=self._environment,
            actor_id=actor_id,
            idempotency_key=key,
            user_id=user_id,
            expected_version=request.expected_version,
            request_id=request_id,
        )
        self._resume(claim.record, expected_version=request.expected_version)

    def _resume(self, record: dict[str, object], *, expected_version: int) -> None:
        state = self._state(record)
        if state == ResendSagaState.COMPLETED:
            replay = replay_from_record(record)
            if replay.http_status != 204:
                raise InvitationSagaInvariantError("resend replay is incompatible")
            return
        if state == ResendSagaState.RECONCILIATION_REQUIRED:
            self._raise_reconciliation(record)
        if state == ResendSagaState.DISPATCHING:
            self._mark_uncertain(record, "dispatch_state_recovered")
        if state == ResendSagaState.SENT:
            self._complete(record, expected_version=expected_version)
            return
        if state not in {ResendSagaState.CLAIMED, ResendSagaState.RETRYABLE}:
            raise InvitationSagaInvariantError("resend saga cannot be resumed")

        self._validate_target(record, expected_version=expected_version)
        self._saga.transition(record=record, next_state=ResendSagaState.DISPATCHING.value)
        dispatching = self._reload(record)
        try:
            self._cognito.admin_resend_invitation(
                user_id=self._required_string(dispatching, "target")
            )
        except CognitoInvitationDeliveryError:
            self._saga.store_delivery_failure(
                record=dispatching,
                retryable_state=ResendSagaState.RETRYABLE.value,
                error_code=INVITATION_DELIVERY_FAILED,
            )
            self._log_failure(record, "delivery_not_applied")
            raise InvitationDeliveryFailedError from None
        except CognitoResultAmbiguousError:
            self._mark_uncertain(dispatching, "delivery_result_ambiguous")
        except Exception:
            self._mark_uncertain(dispatching, "delivery_result_inconclusive")

        try:
            self._saga.transition(record=dispatching, next_state=ResendSagaState.SENT.value)
        except Exception:
            current = self._reload(record)
            current_state = self._state(current)
            if current_state not in {ResendSagaState.SENT, ResendSagaState.COMPLETED}:
                if current_state == ResendSagaState.DISPATCHING:
                    self._mark_uncertain(current, "delivery_success_transition_failed")
                raise
        self._complete(self._reload(record), expected_version=expected_version)

    def _validate_target(self, record: dict[str, object], *, expected_version: int) -> None:
        user_id = self._required_string(record, "target")
        profile = self._users.get_profile(user_id)
        if profile is None:
            raise AdminUserNotFoundError
        if profile.get("PK") != f"USER#{user_id}" or profile.get("SK") != "PROFILE":
            raise UserInvitationReconciliationError
        if self._required_int(profile, "version") != expected_version:
            raise UserVersionConflictError
        if self._required_string(profile, "status") != "INVITED":
            raise UserStateConflictError
        cognito_sub = self._required_string(profile, "cognitoSub")
        email = self._required_string(profile, "email")
        try:
            reconciled = reconcile_user_state(self._users, cognito_sub)
            identity = self._cognito.admin_get_user(user_id=user_id, expected_email=email)
        except (
            UserStateReconciliationError,
            CognitoUserNotFoundError,
            CognitoIdentityInvariantError,
            CognitoResultAmbiguousError,
            CognitoServiceError,
        ):
            raise UserInvitationReconciliationError from None
        if reconciled.user_id != user_id or identity.cognito_sub != cognito_sub:
            raise UserInvitationReconciliationError
        if self._required_int(reconciled.profile, "version") != expected_version:
            raise UserVersionConflictError
        if reconciled.status != "INVITED":
            raise UserStateConflictError

    def _complete(self, record: dict[str, object], *, expected_version: int) -> None:
        if self._state(record) == ResendSagaState.COMPLETED:
            return
        if self._state(record) != ResendSagaState.SENT:
            raise InvitationSagaInvariantError("resend completion requires SENT")
        audit = self._audit(record, expected_version=expected_version)
        transition = self._saga.build_resend_completion_transition(record=record)
        try:
            self._users.complete_invitation_resend(
                audit=audit,
                saga_transition=transition,
                client_request_token=self._required_string(record, "idempotencyKey"),
            )
        except Exception:
            current = self._reload(record)
            if self._state(current) == ResendSagaState.COMPLETED:
                return
            raise

    def _audit(self, record: dict[str, object], *, expected_version: int) -> dict[str, object]:
        target = self._required_string(record, "target")
        actor_id = self._required_string(record, "actorId")
        event_id = self._required_string(record, "eventId")
        correlation_id = self._required_string(record, "correlationId")
        occurred_at = self._required_string(record, "startedAt")
        try:
            timestamp = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        except ValueError:
            raise InvitationSagaInvariantError("resend timestamp is invalid") from None
        if timestamp.tzinfo is None or self._audit_retention_days <= 0:
            raise InvitationSagaInvariantError("resend audit context is invalid")
        sort_key = f"TS#{occurred_at}#EVENT#{event_id}"
        return {
            "PK": f"RESOURCE#USER#{target}",
            "SK": sort_key,
            "eventId": event_id,
            "eventType": "USER_INVITATION_RESENT",
            "resourceType": "USER",
            "resourceId": target,
            "actorId": actor_id,
            "occurredAt": occurred_at,
            "result": "SUCCESS",
            "correlationId": correlation_id,
            "observedVersion": expected_version,
            "GSI1PK": f"ACTOR#{actor_id}",
            "GSI1SK": sort_key,
            "GSI2PK": f"CORRELATION#{correlation_id}",
            "GSI2SK": sort_key,
            "GSI3PK": f"PERIOD#{occurred_at[:7]}",
            "GSI3SK": sort_key,
            "expiresAt": int((timestamp + timedelta(days=self._audit_retention_days)).timestamp()),
        }

    def _mark_uncertain(self, record: dict[str, object], reason: str) -> None:
        self._saga.store_delivery_failure(
            record=record,
            retryable_state=ResendSagaState.RECONCILIATION_REQUIRED.value,
            error_code=INVITATION_DELIVERY_UNCERTAIN,
        )
        self._log_failure(record, reason)
        raise InvitationDeliveryUncertainError

    @staticmethod
    def _raise_reconciliation(record: dict[str, object]) -> None:
        if record.get("errorCode") == INVITATION_DELIVERY_UNCERTAIN:
            raise InvitationDeliveryUncertainError
        raise UserInvitationReconciliationError

    def _authorize(self, cognito_sub: str) -> str:
        try:
            actor = reconcile_user_state(self._users, cognito_sub, self._validate_admin)
        except UserStateReconciliationError:
            raise AdminUserForbiddenError from None
        return actor.user_id

    @staticmethod
    def _validate_admin(role: str, status: str, auth_version: int) -> None:
        del auth_version
        if role != "ADMIN" or status != "ACTIVE":
            raise AdminUserForbiddenError

    def _reload(self, record: dict[str, object]) -> dict[str, object]:
        current = self._saga.get(self._required_string(record, "id"))
        if current is None:
            raise InvitationSagaInvariantError("resend saga disappeared")
        return current

    @staticmethod
    def _state(record: dict[str, object]) -> ResendSagaState:
        try:
            return ResendSagaState(ResendInvitationService._required_string(record, "state"))
        except ValueError:
            raise InvitationSagaInvariantError("resend saga state is invalid") from None

    @staticmethod
    def _required_string(record: dict[str, object], field: str) -> str:
        value = record.get(field)
        if not isinstance(value, str) or not value:
            raise AdminUserDataInvariantError
        return value

    @staticmethod
    def _required_int(record: dict[str, object], field: str) -> int:
        value = record.get(field)
        if type(value) is not int or value < 1:
            raise AdminUserDataInvariantError
        return value

    @staticmethod
    def _log_failure(record: dict[str, object], reason: str) -> None:
        logger.warning(
            "Administrative invitation resend did not complete",
            extra={
                "stage": "resend_user_invitation",
                "reason": reason,
                "correlationId": str(record.get("correlationId", "")),
            },
        )
