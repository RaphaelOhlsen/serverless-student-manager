from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from users_api.errors import (
    AdminUserForbiddenError,
    AdminUserNotFoundError,
    InvitationSagaInvariantError,
    LastActiveAdminConflictError,
    UserDeactivationReconciliationError,
    UserStateConflictError,
    UserVersionConflictError,
)
from users_api.services.invitation_saga import DeactivationState, SagaClaim
from users_api.services.user_state import (
    ReconciledUserState,
    UserStateReconciliationError,
    reconcile_user_state,
)
from users_api.validation import parse_deactivation_body, validate_idempotency_key


class UserRepositoryProtocol(Protocol):
    def get_authorization(self, cognito_sub: str) -> dict[str, object] | None: ...

    def get_profile(self, user_id: str) -> dict[str, object] | None: ...

    def get_active_admin_count(self) -> int | None: ...

    def deactivate_user(
        self,
        *,
        user_id: str,
        cognito_sub: str,
        role: str,
        version: int,
        auth_version: int,
        occurred_at: str,
        actor_id: str,
        audit: dict[str, object],
        idempotency_transition: dict[str, object],
        client_request_token: str,
    ) -> None: ...


class SagaRepositoryProtocol(Protocol):
    def claim_deactivation(
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

    def build_deactivation_domain_transition(
        self,
        *,
        record: dict[str, object],
        cognito_sub: str,
        role: str,
        resulting_version: int,
    ) -> dict[str, object]: ...


@dataclass(frozen=True)
class DeactivationDomainResult:
    record_id: str
    user_id: str
    state: DeactivationState


class DeactivationService:
    def __init__(
        self,
        users: UserRepositoryProtocol,
        saga: SagaRepositoryProtocol,
        *,
        environment: str,
        audit_retention_days: int,
    ) -> None:
        self._users = users
        self._saga = saga
        self._environment = environment
        self._audit_retention_days = audit_retention_days

    def commit_domain(
        self,
        *,
        cognito_sub: str,
        user_id: str,
        idempotency_key: object,
        request_id: str | None,
        body: str,
    ) -> DeactivationDomainResult:
        actor_id = self._authorize(cognito_sub)
        key = validate_idempotency_key(idempotency_key)
        request = parse_deactivation_body(body)
        if actor_id == user_id:
            raise AdminUserForbiddenError
        claim = self._saga.claim_deactivation(
            environment=self._environment,
            actor_id=actor_id,
            idempotency_key=key,
            user_id=user_id,
            expected_version=request.expected_version,
            request_id=request_id,
        )
        record = claim.record
        record_id = self._required_string(record, "id")
        state = self._state(record)
        if state != DeactivationState.CLAIMED:
            return DeactivationDomainResult(record_id, user_id, state)

        profile = self._profile(user_id)
        version = self._logical_version(profile)
        if version != request.expected_version:
            raise UserVersionConflictError
        target = self._target(profile, user_id)
        if target.status != "ACTIVE":
            raise UserStateConflictError
        transition = self._saga.build_deactivation_domain_transition(
            record=record,
            cognito_sub=target.cognito_sub,
            role=target.role,
            resulting_version=version + 1,
        )
        try:
            self._users.deactivate_user(
                user_id=user_id,
                cognito_sub=target.cognito_sub,
                role=target.role,
                version=version,
                auth_version=target.auth_version,
                occurred_at=self._required_string(record, "startedAt"),
                actor_id=actor_id,
                audit=self._audit(record, version),
                idempotency_transition=transition,
                client_request_token=key,
            )
        except ClientError as error:
            if self._error_code(error) in {
                "ConditionalCheckFailedException",
                "TransactionCanceledException",
            }:
                return self._classify_cancellation(
                    record_id=record_id,
                    user_id=user_id,
                    expected_version=request.expected_version,
                    old_role=target.role,
                )
            raise UserDeactivationReconciliationError from None
        return DeactivationDomainResult(record_id, user_id, DeactivationState.DOMAIN_COMMITTED)

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

    def _profile(self, user_id: str) -> dict[str, object]:
        profile = self._users.get_profile(user_id)
        if profile is None:
            raise AdminUserNotFoundError
        if profile.get("PK") != f"USER#{user_id}" or profile.get("SK") != "PROFILE":
            raise UserDeactivationReconciliationError
        return profile

    def _target(self, profile: dict[str, object], user_id: str) -> ReconciledUserState:
        cognito_sub = self._required_string(profile, "cognitoSub")
        try:
            target = reconcile_user_state(self._users, cognito_sub)
        except UserStateReconciliationError:
            raise UserDeactivationReconciliationError from None
        if target.user_id != user_id or target.role not in {"ADMIN", "OPERATOR"}:
            raise UserDeactivationReconciliationError
        return target

    def _classify_cancellation(
        self,
        *,
        record_id: str,
        user_id: str,
        expected_version: int,
        old_role: str,
    ) -> DeactivationDomainResult:
        current = self._saga.get(record_id)
        if current is not None:
            state = self._state(current)
            if state != DeactivationState.CLAIMED:
                return DeactivationDomainResult(record_id, user_id, state)
        profile = self._profile(user_id)
        if self._logical_version(profile) != expected_version:
            raise UserVersionConflictError
        target = self._target(profile, user_id)
        if target.status != "ACTIVE":
            raise UserStateConflictError
        if target.role != old_role:
            raise UserDeactivationReconciliationError
        if old_role == "ADMIN":
            count = self._users.get_active_admin_count()
            if count == 1:
                raise LastActiveAdminConflictError
            if count is None or count < 1:
                raise UserDeactivationReconciliationError
        raise UserDeactivationReconciliationError

    def _audit(self, record: dict[str, object], old_version: int) -> dict[str, object]:
        target = self._required_string(record, "target")
        actor_id = self._required_string(record, "actorId")
        event_id = self._required_string(record, "eventId")
        correlation_id = self._required_string(record, "correlationId")
        occurred_at = self._required_string(record, "startedAt")
        try:
            timestamp = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        except ValueError:
            raise InvitationSagaInvariantError("deactivation timestamp is invalid") from None
        if timestamp.tzinfo is None or self._audit_retention_days <= 0:
            raise InvitationSagaInvariantError("deactivation audit context is invalid")
        sort_key = f"TS#{occurred_at}#EVENT#{event_id}"
        return {
            "PK": f"RESOURCE#USER#{target}",
            "SK": sort_key,
            "eventId": event_id,
            "eventType": "USER_DEACTIVATED",
            "resourceType": "USER",
            "resourceId": target,
            "actorId": actor_id,
            "occurredAt": occurred_at,
            "result": "SUCCESS",
            "correlationId": correlation_id,
            "changes": {
                "status": {"from": "ACTIVE", "to": "INACTIVE"},
                "version": {"from": old_version, "to": old_version + 1},
            },
            "GSI1PK": f"ACTOR#{actor_id}",
            "GSI1SK": sort_key,
            "GSI2PK": f"CORRELATION#{correlation_id}",
            "GSI2SK": sort_key,
            "GSI3PK": f"PERIOD#{occurred_at[:7]}",
            "GSI3SK": sort_key,
            "expiresAt": int((timestamp + timedelta(days=self._audit_retention_days)).timestamp()),
        }

    @staticmethod
    def _state(record: dict[str, object]) -> DeactivationState:
        try:
            return DeactivationState(str(record.get("state")))
        except ValueError:
            raise InvitationSagaInvariantError("deactivation state is invalid") from None

    @staticmethod
    def _logical_version(profile: dict[str, object]) -> int:
        value = profile.get("version", 1)
        if type(value) is not int or value < 1:
            raise UserDeactivationReconciliationError
        return value

    @staticmethod
    def _required_string(record: dict[str, object], name: str) -> str:
        value = record.get(name)
        if not isinstance(value, str) or not value:
            raise InvitationSagaInvariantError("deactivation context is invalid")
        return value

    @staticmethod
    def _error_code(error: ClientError) -> str:
        details = error.response.get("Error")
        return str(details.get("Code", "")) if isinstance(details, dict) else ""
