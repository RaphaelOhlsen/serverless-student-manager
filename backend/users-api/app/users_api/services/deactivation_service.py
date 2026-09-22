from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from users_api.errors import (
    AdminUserForbiddenError,
    AdminUserNotFoundError,
    CognitoIdentityInvariantError,
    CognitoResultAmbiguousError,
    CognitoServiceError,
    CognitoUserNotFoundError,
    InvitationSagaConcurrentTransitionError,
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
        response: dict[str, object],
    ) -> dict[str, object]: ...

    def transition(self, *, record: dict[str, object], next_state: str) -> None: ...

    def mark_deactivation_disable_attempted(self, *, record: dict[str, object]) -> None: ...

    def store_deactivation_completed(self, *, record: dict[str, object]) -> None: ...


class CognitoRepositoryProtocol(Protocol):
    def admin_user_global_sign_out(self, *, user_id: str) -> None: ...

    def admin_disable_user(self, *, user_id: str) -> None: ...

    def admin_get_deactivation_state(
        self,
        *,
        user_id: str,
        expected_cognito_sub: str,
    ) -> object: ...


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

    def deactivate_user(
        self,
        *,
        cognito_sub: str,
        user_id: str,
        idempotency_key: object,
        request_id: str | None,
        body: str,
    ) -> dict[str, object]:
        result = self.commit_domain(
            cognito_sub=cognito_sub,
            user_id=user_id,
            idempotency_key=idempotency_key,
            request_id=request_id,
            body=body,
        )
        return self._resume(self._reload(result.record_id))

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
            response=self._public_user(
                profile,
                role=target.role,
                version=version + 1,
                updated_at=self._required_string(record, "startedAt"),
            ),
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

    def _resume(self, record: dict[str, object]) -> dict[str, object]:
        state = self._state(record)
        if state == DeactivationState.COMPLETED:
            return self._replay(record)
        if state == DeactivationState.DOMAIN_COMMITTED:
            record = self._complete_sign_out(record)
            state = self._state(record)
        if state == DeactivationState.SIGNOUT_COMPLETED:
            record = self._complete_disable(record)
            state = self._state(record)
        if state == DeactivationState.DISABLE_COMPLETED:
            record = self._complete_saga(record)
            state = self._state(record)
        if state != DeactivationState.COMPLETED:
            raise UserDeactivationReconciliationError
        return self._replay(record)

    def _complete_sign_out(self, record: dict[str, object]) -> dict[str, object]:
        try:
            self._cognito.admin_user_global_sign_out(
                user_id=self._required_string(record, "target")
            )
        except (
            CognitoUserNotFoundError,
            CognitoResultAmbiguousError,
            CognitoServiceError,
        ):
            raise UserDeactivationReconciliationError from None
        except Exception:
            raise UserDeactivationReconciliationError from None
        return self._advance(record, DeactivationState.SIGNOUT_COMPLETED)

    def _complete_disable(self, record: dict[str, object]) -> dict[str, object]:
        if self._disable_was_attempted(record):
            return self._reconcile_disable(record, allow_retry=True)
        try:
            self._saga.mark_deactivation_disable_attempted(record=record)
        except InvitationSagaConcurrentTransitionError:
            record = self._reload(self._required_string(record, "id"))
            if self._state(record) != DeactivationState.SIGNOUT_COMPLETED:
                return record
            if not self._disable_was_attempted(record):
                raise UserDeactivationReconciliationError from None
            return self._reconcile_disable(record, allow_retry=True)
        except Exception:
            raise UserDeactivationReconciliationError from None
        marked = self._reload(self._required_string(record, "id"))
        if self._state(marked) != DeactivationState.SIGNOUT_COMPLETED:
            return marked
        if not self._disable_was_attempted(marked):
            raise UserDeactivationReconciliationError
        return self._call_disable(marked, reconcile_ambiguous=True)

    def _call_disable(
        self,
        record: dict[str, object],
        *,
        reconcile_ambiguous: bool,
    ) -> dict[str, object]:
        try:
            self._cognito.admin_disable_user(user_id=self._required_string(record, "target"))
        except CognitoResultAmbiguousError:
            if reconcile_ambiguous:
                return self._reconcile_disable(record, allow_retry=True)
            raise UserDeactivationReconciliationError from None
        except (
            CognitoUserNotFoundError,
            CognitoServiceError,
        ):
            raise UserDeactivationReconciliationError from None
        except Exception:
            raise UserDeactivationReconciliationError from None
        return self._advance(record, DeactivationState.DISABLE_COMPLETED)

    def _reconcile_disable(
        self,
        record: dict[str, object],
        *,
        allow_retry: bool,
    ) -> dict[str, object]:
        try:
            state = self._cognito.admin_get_deactivation_state(
                user_id=self._required_string(record, "target"),
                expected_cognito_sub=self._required_string(record, "cognitoSub"),
            )
        except (
            CognitoUserNotFoundError,
            CognitoIdentityInvariantError,
            CognitoResultAmbiguousError,
            CognitoServiceError,
        ):
            raise UserDeactivationReconciliationError from None
        except Exception:
            raise UserDeactivationReconciliationError from None
        enabled = getattr(state, "enabled", None)
        user_id = getattr(state, "user_id", None)
        cognito_sub = getattr(state, "cognito_sub", None)
        if (
            type(enabled) is not bool
            or user_id != self._required_string(record, "target")
            or cognito_sub != self._required_string(record, "cognitoSub")
        ):
            raise UserDeactivationReconciliationError
        if not enabled:
            return self._advance(record, DeactivationState.DISABLE_COMPLETED)
        if not allow_retry:
            raise UserDeactivationReconciliationError
        return self._call_disable(record, reconcile_ambiguous=False)

    def _complete_saga(self, record: dict[str, object]) -> dict[str, object]:
        try:
            self._saga.store_deactivation_completed(record=record)
        except InvitationSagaConcurrentTransitionError:
            pass
        except Exception:
            current = self._reload(self._required_string(record, "id"))
            if self._state(current) != DeactivationState.COMPLETED:
                raise UserDeactivationReconciliationError from None
            return current
        current = self._reload(self._required_string(record, "id"))
        if self._state(current) != DeactivationState.COMPLETED:
            raise UserDeactivationReconciliationError
        return current

    def _advance(
        self,
        record: dict[str, object],
        next_state: DeactivationState,
    ) -> dict[str, object]:
        try:
            self._saga.transition(record=record, next_state=next_state.value)
        except InvitationSagaConcurrentTransitionError:
            pass
        except Exception:
            current = self._reload(self._required_string(record, "id"))
            if self._state_rank(self._state(current)) < self._state_rank(next_state):
                raise UserDeactivationReconciliationError from None
            return current
        current = self._reload(self._required_string(record, "id"))
        if self._state_rank(self._state(current)) < self._state_rank(next_state):
            raise UserDeactivationReconciliationError
        return current

    def _replay(self, record: dict[str, object]) -> dict[str, object]:
        if self._state(record) != DeactivationState.COMPLETED or record.get("httpStatus") != 200:
            raise InvitationSagaInvariantError("deactivation replay is invalid")
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
            or response["status"] != "INACTIVE"
            or response["version"] != record.get("resultingVersion")
        ):
            raise InvitationSagaInvariantError("deactivation replay response is incompatible")
        return response

    @staticmethod
    def _public_user(
        profile: dict[str, object],
        *,
        role: str,
        version: int,
        updated_at: str,
    ) -> dict[str, object]:
        return {
            "userId": DeactivationService._required_string(profile, "userId"),
            "fullName": DeactivationService._required_string(profile, "fullName"),
            "email": DeactivationService._required_string(profile, "email"),
            "role": role,
            "status": "INACTIVE",
            "version": version,
            "createdAt": DeactivationService._required_string(profile, "createdAt"),
            "updatedAt": updated_at,
        }

    def _reload(self, record_id: str) -> dict[str, object]:
        current = self._saga.get(record_id)
        if current is None:
            raise InvitationSagaInvariantError("deactivation saga disappeared")
        return current

    @staticmethod
    def _disable_was_attempted(record: dict[str, object]) -> bool:
        value = record.get("disableAttemptedAt")
        return isinstance(value, str) and bool(value)

    @staticmethod
    def _state_rank(state: DeactivationState) -> int:
        return {
            DeactivationState.CLAIMED: 0,
            DeactivationState.DOMAIN_COMMITTED: 1,
            DeactivationState.SIGNOUT_COMPLETED: 2,
            DeactivationState.DISABLE_COMPLETED: 3,
            DeactivationState.COMPLETED: 4,
        }[state]

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
    def _required_int(record: dict[str, object], name: str) -> int:
        value = record.get(name)
        if type(value) is not int or value < 1:
            raise InvitationSagaInvariantError("deactivation context is invalid")
        return value

    @staticmethod
    def _error_code(error: ClientError) -> str:
        details = error.response.get("Error")
        return str(details.get("Code", "")) if isinstance(details, dict) else ""
