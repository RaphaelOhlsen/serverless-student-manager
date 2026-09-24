from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid5

from users_api.errors import (
    AdminUserForbiddenError,
    AdminUserNotFoundError,
    CognitoIdentityInvariantError,
    CognitoResultAmbiguousError,
    CognitoServiceError,
    CognitoUserNotFoundError,
    InvitationSagaConcurrentTransitionError,
    InvitationSagaInvariantError,
    UserReactivationReconciliationError,
    UserStateConflictError,
    UserVersionConflictError,
)
from users_api.services.invitation_saga import ReactivationState, SagaClaim
from users_api.services.user_state import (
    ReconciledUserState,
    UserStateReconciliationError,
    reconcile_user_state,
)
from users_api.validation import (
    normalize_admin_user_email,
    parse_reactivation_body,
    validate_idempotency_key,
)


class UserRepositoryProtocol(Protocol):
    def get_authorization(self, cognito_sub: str) -> dict[str, object] | None: ...

    def get_profile(self, user_id: str) -> dict[str, object] | None: ...

    def reactivate_user(
        self,
        *,
        user_id: str,
        cognito_sub: str,
        normalized_email: str,
        role: str,
        version: int,
        auth_version: int,
        updated_at: str,
        actor_id: str,
        audit: dict[str, object],
        idempotency_transition: dict[str, object],
        client_request_token: str,
    ) -> None: ...


class SagaRepositoryProtocol(Protocol):
    def claim_reactivation(
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

    def mark_reactivation_enable_dispatching(
        self,
        *,
        record: dict[str, object],
        role: str,
        cognito_sub: str,
        observed_version: int,
        observed_auth_version: int,
    ) -> None: ...

    def transition(self, *, record: dict[str, object], next_state: str) -> None: ...

    def build_reactivation_completion_transition(
        self,
        *,
        record: dict[str, object],
        response: dict[str, object],
    ) -> dict[str, object]: ...


class CognitoRepositoryProtocol(Protocol):
    def admin_get_reactivation_state(
        self,
        *,
        user_id: str,
        expected_cognito_sub: str,
        expected_email: str,
        expected_enabled: bool | None,
    ) -> object: ...

    def admin_enable_user(self, *, user_id: str) -> None: ...


@dataclass(frozen=True)
class ReactivationTarget:
    profile: dict[str, object]
    state: ReconciledUserState
    version: int
    normalized_email: str


class ReactivationService:
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

    def reactivate_user(
        self,
        *,
        cognito_sub: str,
        user_id: str,
        idempotency_key: object,
        request_id: str | None,
        body: str,
    ) -> dict[str, object]:
        actor_id = self._authorize(cognito_sub)
        key = validate_idempotency_key(idempotency_key)
        request = parse_reactivation_body(body)
        claim = self._saga.claim_reactivation(
            environment=self._environment,
            actor_id=actor_id,
            idempotency_key=key,
            user_id=user_id,
            expected_version=request.expected_version,
            request_id=request_id,
        )
        return self._resume(claim.record)

    def _resume(self, record: dict[str, object]) -> dict[str, object]:
        for _ in range(8):
            state = self._state(record)
            if state == ReactivationState.COMPLETED:
                return self._replay(record)
            if state == ReactivationState.CLAIMED:
                record = self._start(record)
                continue
            if state == ReactivationState.ENABLE_DISPATCHING:
                record = self._resume_enable_dispatch(record)
                continue
            if state == ReactivationState.COGNITO_ENABLED:
                record = self._complete_domain(record)
                continue
            if state == ReactivationState.RECONCILIATION_REQUIRED:
                record = self._resume_reconciliation(record)
                continue
        return self._mark_reconciliation(record)

    def _start(self, record: dict[str, object]) -> dict[str, object]:
        target = self._initial_target(record)
        try:
            self._read_cognito(record, target, expected_enabled=False)
        except Exception:
            return self._mark_reconciliation(record)
        return self._mark_dispatch_and_enable(record, target)

    def _resume_enable_dispatch(self, record: dict[str, object]) -> dict[str, object]:
        try:
            target = self._durable_target(record)
            enabled = self._read_cognito(record, target, expected_enabled=None)
        except Exception:
            return self._mark_reconciliation(record)
        if enabled:
            return self._mark_cognito_enabled(record)
        return self._call_enable(record, target, allow_retry_after_readback=True)

    def _resume_reconciliation(self, record: dict[str, object]) -> dict[str, object]:
        has_marker = self._has_enable_marker(record)
        try:
            target = self._durable_target(record) if has_marker else self._initial_target(record)
            enabled = self._read_cognito(record, target, expected_enabled=None)
        except (UserVersionConflictError, UserStateConflictError, AdminUserNotFoundError):
            if has_marker:
                raise UserReactivationReconciliationError from None
            raise
        except Exception:
            raise UserReactivationReconciliationError from None
        if enabled:
            if not has_marker:
                raise UserReactivationReconciliationError
            return self._mark_cognito_enabled(record)
        return self._mark_dispatch_and_enable(record, target)

    def _mark_dispatch_and_enable(
        self,
        record: dict[str, object],
        target: ReactivationTarget,
    ) -> dict[str, object]:
        try:
            self._saga.mark_reactivation_enable_dispatching(
                record=record,
                role=target.state.role,
                cognito_sub=target.state.cognito_sub,
                observed_version=target.version,
                observed_auth_version=target.state.auth_version,
            )
        except InvitationSagaConcurrentTransitionError:
            return self._resume_enable_dispatch(self._reload(self._required_string(record, "id")))
        except Exception:
            current = self._reload(self._required_string(record, "id"))
            if self._state(current) == ReactivationState.ENABLE_DISPATCHING:
                return self._resume_enable_dispatch(current)
            return self._mark_reconciliation(current)
        marked = self._reload(self._required_string(record, "id"))
        if self._state(marked) != ReactivationState.ENABLE_DISPATCHING:
            return self._mark_reconciliation(marked)
        return self._call_enable(marked, target, allow_retry_after_readback=True)

    def _call_enable(
        self,
        record: dict[str, object],
        target: ReactivationTarget,
        *,
        allow_retry_after_readback: bool,
    ) -> dict[str, object]:
        try:
            self._cognito.admin_enable_user(user_id=self._required_string(record, "target"))
        except CognitoResultAmbiguousError:
            return self._reconcile_ambiguous_enable(
                record,
                target,
                allow_retry=allow_retry_after_readback,
            )
        except (CognitoUserNotFoundError, CognitoServiceError):
            return self._mark_reconciliation(record)
        except Exception:
            return self._mark_reconciliation(record)
        return self._mark_cognito_enabled(record)

    def _reconcile_ambiguous_enable(
        self,
        record: dict[str, object],
        target: ReactivationTarget,
        *,
        allow_retry: bool,
    ) -> dict[str, object]:
        try:
            enabled = self._read_cognito(record, target, expected_enabled=None)
        except Exception:
            return self._mark_reconciliation(record)
        if enabled:
            return self._mark_cognito_enabled(record)
        if not allow_retry:
            return self._mark_reconciliation(record)
        return self._call_enable(record, target, allow_retry_after_readback=False)

    def _mark_cognito_enabled(self, record: dict[str, object]) -> dict[str, object]:
        try:
            self._saga.transition(
                record=record,
                next_state=ReactivationState.COGNITO_ENABLED.value,
            )
        except InvitationSagaConcurrentTransitionError:
            pass
        except Exception:
            current = self._reload(self._required_string(record, "id"))
            if self._state(current) not in {
                ReactivationState.COGNITO_ENABLED,
                ReactivationState.COMPLETED,
            }:
                return self._mark_reconciliation(current)
            return current
        current = self._reload(self._required_string(record, "id"))
        if self._state(current) not in {
            ReactivationState.COGNITO_ENABLED,
            ReactivationState.COMPLETED,
        }:
            return self._mark_reconciliation(current)
        return current

    def _complete_domain(self, record: dict[str, object]) -> dict[str, object]:
        try:
            target = self._durable_target(record)
            self._read_cognito(record, target, expected_enabled=True)
            response = self._public_user(record, target)
            transition = self._saga.build_reactivation_completion_transition(
                record=record,
                response=response,
            )
            self._users.reactivate_user(
                user_id=target.state.user_id,
                cognito_sub=target.state.cognito_sub,
                normalized_email=target.normalized_email,
                role=target.state.role,
                version=target.version,
                auth_version=target.state.auth_version,
                updated_at=self._required_string(record, "startedAt"),
                actor_id=self._required_string(record, "actorId"),
                audit=self._audit(record, target.version),
                idempotency_transition=transition,
                client_request_token=self._client_request_token(record),
            )
        except Exception:
            current = self._reload(self._required_string(record, "id"))
            if self._state(current) == ReactivationState.COMPLETED:
                return current
            return self._mark_reconciliation(current)
        current = self._reload(self._required_string(record, "id"))
        if self._state(current) != ReactivationState.COMPLETED:
            return self._mark_reconciliation(current)
        return current

    def _read_cognito(
        self,
        record: dict[str, object],
        target: ReactivationTarget,
        *,
        expected_enabled: bool | None,
    ) -> bool:
        state = self._cognito.admin_get_reactivation_state(
            user_id=self._required_string(record, "target"),
            expected_cognito_sub=target.state.cognito_sub,
            expected_email=target.normalized_email,
            expected_enabled=expected_enabled,
        )
        enabled = getattr(state, "enabled", None)
        if (
            type(enabled) is not bool
            or getattr(state, "user_id", None) != target.state.user_id
            or getattr(state, "cognito_sub", None) != target.state.cognito_sub
        ):
            raise CognitoIdentityInvariantError
        return enabled

    def _initial_target(self, record: dict[str, object]) -> ReactivationTarget:
        user_id = self._required_string(record, "target")
        profile = self._profile(user_id)
        version = self._logical_version(profile)
        if version != self._required_int(record, "expectedVersion"):
            raise UserVersionConflictError
        target = self._reconcile_target(profile, user_id)
        if target.status != "INACTIVE":
            raise UserStateConflictError
        return ReactivationTarget(
            profile=profile,
            state=target,
            version=version,
            normalized_email=self._normalized_email(profile),
        )

    def _durable_target(self, record: dict[str, object]) -> ReactivationTarget:
        try:
            user_id = self._required_string(record, "target")
            profile = self._profile(user_id)
            version = self._logical_version(profile)
            target = self._reconcile_target(profile, user_id)
            if (
                target.status != "INACTIVE"
                or target.role != self._required_string(record, "domainRole")
                or target.cognito_sub != self._required_string(record, "cognitoSub")
                or target.auth_version != self._required_int(record, "observedAuthVersion")
                or version != self._required_int(record, "observedVersion")
                or version != self._required_int(record, "expectedVersion")
            ):
                raise UserReactivationReconciliationError
            return ReactivationTarget(
                profile=profile,
                state=target,
                version=version,
                normalized_email=self._normalized_email(profile),
            )
        except UserReactivationReconciliationError:
            raise
        except Exception:
            raise UserReactivationReconciliationError from None

    def _profile(self, user_id: str) -> dict[str, object]:
        profile = self._users.get_profile(user_id)
        if profile is None:
            raise AdminUserNotFoundError
        if profile.get("PK") != f"USER#{user_id}" or profile.get("SK") != "PROFILE":
            raise UserReactivationReconciliationError
        return profile

    def _reconcile_target(
        self,
        profile: dict[str, object],
        user_id: str,
    ) -> ReconciledUserState:
        cognito_sub = self._required_profile_string(profile, "cognitoSub")
        try:
            target = reconcile_user_state(self._users, cognito_sub)
        except UserStateReconciliationError:
            raise UserReactivationReconciliationError from None
        if target.user_id != user_id or target.role not in {"ADMIN", "OPERATOR"}:
            raise UserReactivationReconciliationError
        return target

    @staticmethod
    def _normalized_email(profile: dict[str, object]) -> str:
        value = ReactivationService._required_profile_string(profile, "email")
        try:
            return normalize_admin_user_email(value)
        except ValueError:
            raise UserReactivationReconciliationError from None

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

    def _mark_reconciliation(self, record: dict[str, object]) -> dict[str, object]:
        record_id = self._required_string(record, "id")
        current = self._reload(record_id)
        state = self._state(current)
        if state == ReactivationState.COMPLETED:
            return current
        if state != ReactivationState.RECONCILIATION_REQUIRED:
            try:
                self._saga.transition(
                    record=current,
                    next_state=ReactivationState.RECONCILIATION_REQUIRED.value,
                )
            except InvitationSagaConcurrentTransitionError:
                winner = self._reload(record_id)
                winner_state = self._state(winner)
                if winner_state in {
                    ReactivationState.ENABLE_DISPATCHING,
                    ReactivationState.COGNITO_ENABLED,
                    ReactivationState.COMPLETED,
                }:
                    return winner
                if winner_state != ReactivationState.RECONCILIATION_REQUIRED:
                    raise UserReactivationReconciliationError from None
            except Exception:
                latest = self._reload(record_id)
                latest_state = self._state(latest)
                if latest_state in {
                    ReactivationState.ENABLE_DISPATCHING,
                    ReactivationState.COGNITO_ENABLED,
                    ReactivationState.COMPLETED,
                }:
                    return latest
                if latest_state != ReactivationState.RECONCILIATION_REQUIRED:
                    raise UserReactivationReconciliationError from None
        raise UserReactivationReconciliationError

    def _replay(self, record: dict[str, object]) -> dict[str, object]:
        if self._state(record) != ReactivationState.COMPLETED or record.get("httpStatus") != 200:
            raise InvitationSagaInvariantError("reactivation replay is invalid")
        response = {
            "userId": self._required_string(record, "responseUserId"),
            "fullName": self._required_string(record, "responseFullName"),
            "email": self._required_string(record, "responseEmail"),
            "role": self._required_string(record, "responseRole"),
            "status": self._required_string(record, "responseStatus"),
            "version": self._required_int(record, "responseVersion"),
            "createdAt": self._required_string(record, "responseCreatedAt"),
            "updatedAt": self._required_string(record, "responseUpdatedAt"),
        }
        if (
            response["userId"] != record.get("target")
            or response["role"] != record.get("domainRole")
            or response["status"] != "ACTIVE"
            or response["version"] != self._required_int(record, "observedVersion") + 1
        ):
            raise InvitationSagaInvariantError("reactivation replay response is incompatible")
        return response

    def _public_user(
        self,
        record: dict[str, object],
        target: ReactivationTarget,
    ) -> dict[str, object]:
        return {
            "userId": target.state.user_id,
            "fullName": self._required_profile_string(target.profile, "fullName"),
            "email": target.normalized_email,
            "role": target.state.role,
            "status": "ACTIVE",
            "version": target.version + 1,
            "createdAt": self._required_profile_string(target.profile, "createdAt"),
            "updatedAt": self._required_string(record, "startedAt"),
        }

    def _audit(self, record: dict[str, object], old_version: int) -> dict[str, object]:
        target = self._required_string(record, "target")
        actor_id = self._required_string(record, "actorId")
        event_id = self._required_string(record, "eventId")
        correlation_id = self._required_string(record, "correlationId")
        occurred_at = self._required_string(record, "startedAt")
        try:
            timestamp = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        except ValueError:
            raise InvitationSagaInvariantError("reactivation timestamp is invalid") from None
        if timestamp.tzinfo is None or self._audit_retention_days <= 0:
            raise InvitationSagaInvariantError("reactivation audit context is invalid")
        sort_key = f"TS#{occurred_at}#EVENT#{event_id}"
        return {
            "PK": f"RESOURCE#USER#{target}",
            "SK": sort_key,
            "eventId": event_id,
            "eventType": "USER_REACTIVATED",
            "resourceType": "USER",
            "resourceId": target,
            "actorId": actor_id,
            "occurredAt": occurred_at,
            "result": "SUCCESS",
            "correlationId": correlation_id,
            "changes": {
                "status": {"from": "INACTIVE", "to": "ACTIVE"},
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

    def _reload(self, record_id: str) -> dict[str, object]:
        current = self._saga.get(record_id)
        if current is None:
            raise InvitationSagaInvariantError("reactivation saga disappeared")
        return current

    @staticmethod
    def _has_enable_marker(record: dict[str, object]) -> bool:
        value = record.get("enableAttemptedAt")
        return isinstance(value, str) and bool(value)

    @staticmethod
    def _state(record: dict[str, object]) -> ReactivationState:
        try:
            return ReactivationState(str(record.get("state")))
        except ValueError:
            raise InvitationSagaInvariantError("reactivation state is invalid") from None

    @staticmethod
    def _logical_version(profile: dict[str, object]) -> int:
        value = profile.get("version", 1)
        if type(value) is not int or value < 1:
            raise UserReactivationReconciliationError
        return value

    @staticmethod
    def _required_string(record: dict[str, object], name: str) -> str:
        value = record.get(name)
        if not isinstance(value, str) or not value:
            raise InvitationSagaInvariantError("reactivation context is invalid")
        return value

    @staticmethod
    def _required_int(record: dict[str, object], name: str) -> int:
        value = record.get(name)
        if type(value) is not int or value < 1:
            raise InvitationSagaInvariantError("reactivation context is invalid")
        return value

    @staticmethod
    def _client_request_token(record: dict[str, object]) -> str:
        record_id = ReactivationService._required_string(record, "id")
        return str(uuid5(UUID(int=0), record_id))

    @staticmethod
    def _required_profile_string(profile: dict[str, object], name: str) -> str:
        value = profile.get(name)
        if not isinstance(value, str) or not value:
            raise UserReactivationReconciliationError
        return value
