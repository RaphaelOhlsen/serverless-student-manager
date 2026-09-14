from datetime import datetime, timedelta
from typing import Protocol

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from users_api.errors import (
    AdminUserDataInvariantError,
    AdminUserForbiddenError,
    AdminUserNotFoundError,
    InvitationSagaInvariantError,
    LastActiveAdminConflictError,
    UserRoleChangeReconciliationError,
    UserVersionConflictError,
)
from users_api.repositories.dynamodb_values import normalize_dynamodb_value
from users_api.services.invitation_saga import RoleChangeState, SagaClaim
from users_api.services.user_state import (
    ReconciledUserState,
    UserStateReconciliationError,
    reconcile_user_state,
)
from users_api.validation import parse_role_change_body, validate_idempotency_key


class UserRepositoryProtocol(Protocol):
    def get_authorization(self, cognito_sub: str) -> dict[str, object] | None: ...

    def get_profile(self, user_id: str) -> dict[str, object] | None: ...

    def get_active_admin_count(self) -> int | None: ...

    def change_role(self, **kwargs: object) -> None: ...

    def complete_role_change_noop(self, **kwargs: object) -> None: ...


class SagaRepositoryProtocol(Protocol):
    def claim_role_change(self, **kwargs: object) -> SagaClaim: ...

    def get(self, record_id: str) -> dict[str, object] | None: ...

    def build_role_change_completion_transition(
        self, *, record: dict[str, object], response: dict[str, object]
    ) -> dict[str, object]: ...


class RoleChangeService:
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

    def change_role(
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
        request = parse_role_change_body(body)
        claim = self._saga.claim_role_change(
            environment=self._environment,
            actor_id=actor_id,
            idempotency_key=key,
            user_id=user_id,
            role=request.role,
            expected_version=request.expected_version,
            request_id=request_id,
        )
        if claim.record.get("state") == RoleChangeState.COMPLETED.value:
            return self._replay(claim.record)

        profile = self._profile(user_id)
        current_version = self._logical_version(profile)
        if current_version != request.expected_version:
            raise UserVersionConflictError
        if actor_id == user_id:
            raise AdminUserForbiddenError
        state = self._reconcile_target(profile, user_id)
        current_role = state.role
        status = state.status
        response = self._public_user(
            profile,
            role=request.role,
            version=current_version + (request.role != current_role),
            updated_at=(
                self._required_string(claim.record, "startedAt")
                if request.role != current_role
                else self._required_string(profile, "updatedAt")
            ),
        )
        transition = self._saga.build_role_change_completion_transition(
            record=claim.record, response=response
        )
        try:
            if request.role == current_role:
                self._users.complete_role_change_noop(
                    user_id=user_id,
                    cognito_sub=state.cognito_sub,
                    role=current_role,
                    status=status,
                    version=current_version,
                    auth_version=state.auth_version,
                    idempotency_transition=transition,
                    client_request_token=key,
                )
            else:
                self._users.change_role(
                    user_id=user_id,
                    cognito_sub=state.cognito_sub,
                    old_role=current_role,
                    new_role=request.role,
                    status=status,
                    version=current_version,
                    auth_version=state.auth_version,
                    updated_at=self._required_string(claim.record, "startedAt"),
                    actor_id=actor_id,
                    audit=self._audit(
                        claim.record,
                        old_role=current_role,
                        new_role=request.role,
                        old_version=current_version,
                    ),
                    idempotency_transition=transition,
                    client_request_token=key,
                )
        except ClientError as error:
            if self._error_code(error) not in {
                "ConditionalCheckFailedException",
                "TransactionCanceledException",
            }:
                raise
            return self._classify_transaction_cancellation(
                claim.record,
                user_id=user_id,
                expected_version=request.expected_version,
                old_role=current_role,
                new_role=request.role,
                old_status=status,
            )
        return response

    def _authorize(self, cognito_sub: str) -> str:
        try:
            state = reconcile_user_state(self._users, cognito_sub, self._validate_admin)
        except UserStateReconciliationError:
            raise AdminUserForbiddenError from None
        return state.user_id

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
            raise UserRoleChangeReconciliationError
        return profile

    def _reconcile_target(self, profile: dict[str, object], user_id: str) -> ReconciledUserState:
        cognito_sub = self._required_string(profile, "cognitoSub")
        try:
            state = reconcile_user_state(self._users, cognito_sub)
        except UserStateReconciliationError:
            raise UserRoleChangeReconciliationError from None
        if state.user_id != user_id or state.status not in {"INVITED", "ACTIVE", "INACTIVE"}:
            raise UserRoleChangeReconciliationError
        return state

    def _classify_transaction_cancellation(
        self,
        record: dict[str, object],
        *,
        user_id: str,
        expected_version: int,
        old_role: str,
        new_role: str,
        old_status: str,
    ) -> dict[str, object]:
        current = self._saga.get(self._required_string(record, "id"))
        if current is not None and current.get("state") == RoleChangeState.COMPLETED.value:
            return self._replay(current)
        profile = self._profile(user_id)
        if self._logical_version(profile) != expected_version:
            raise UserVersionConflictError
        try:
            state = self._reconcile_target(profile, user_id)
        except UserRoleChangeReconciliationError:
            raise
        if state.role != old_role or state.status != old_status:
            raise UserRoleChangeReconciliationError
        if old_status == "ACTIVE" and old_role == "ADMIN" and new_role == "OPERATOR":
            count = self._users.get_active_admin_count()
            if count == 1:
                raise LastActiveAdminConflictError
            if count is None or count < 1:
                raise UserRoleChangeReconciliationError
        raise UserRoleChangeReconciliationError

    def _replay(self, record: dict[str, object]) -> dict[str, object]:
        if record.get("httpStatus") != 200:
            raise InvitationSagaInvariantError("role change replay status is invalid")
        user_id = self._required_string(record, "responseUserId")
        profile = self._profile(user_id)
        response = {
            "userId": user_id,
            "fullName": self._required_string(profile, "fullName"),
            "email": self._required_string(profile, "email"),
            "role": self._required_string(record, "responseRole"),
            "status": self._required_string(record, "responseStatus"),
            "version": self._required_int(record, "responseVersion"),
            "createdAt": self._required_string(record, "responseCreatedAt"),
            "updatedAt": self._required_string(record, "responseUpdatedAt"),
        }
        if response["role"] not in {"ADMIN", "OPERATOR"} or response["status"] not in {
            "INVITED",
            "ACTIVE",
            "INACTIVE",
        }:
            raise InvitationSagaInvariantError("role change replay is invalid")
        return response

    def _audit(
        self,
        record: dict[str, object],
        *,
        old_role: str,
        new_role: str,
        old_version: int,
    ) -> dict[str, object]:
        target = self._required_string(record, "target")
        actor_id = self._required_string(record, "actorId")
        event_id = self._required_string(record, "eventId")
        correlation_id = self._required_string(record, "correlationId")
        occurred_at = self._required_string(record, "startedAt")
        try:
            timestamp = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        except ValueError:
            raise InvitationSagaInvariantError("role change timestamp is invalid") from None
        if timestamp.tzinfo is None or self._audit_retention_days <= 0:
            raise InvitationSagaInvariantError("role change audit context is invalid")
        sort_key = f"TS#{occurred_at}#EVENT#{event_id}"
        return {
            "PK": f"RESOURCE#USER#{target}",
            "SK": sort_key,
            "eventId": event_id,
            "eventType": "USER_ROLE_CHANGED",
            "resourceType": "USER",
            "resourceId": target,
            "actorId": actor_id,
            "occurredAt": occurred_at,
            "result": "SUCCESS",
            "correlationId": correlation_id,
            "changes": {
                "role": {"from": old_role, "to": new_role},
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
    def _public_user(
        profile: dict[str, object], *, role: str, version: int, updated_at: str
    ) -> dict[str, object]:
        return {
            "userId": RoleChangeService._required_string(profile, "userId"),
            "fullName": RoleChangeService._required_string(profile, "fullName"),
            "email": RoleChangeService._required_string(profile, "email"),
            "role": role,
            "status": RoleChangeService._required_string(profile, "status"),
            "version": version,
            "createdAt": RoleChangeService._required_string(profile, "createdAt"),
            "updatedAt": updated_at,
        }

    @staticmethod
    def _logical_version(profile: dict[str, object]) -> int:
        value = normalize_dynamodb_value(profile.get("version", 1))
        if type(value) is not int or value < 1:
            raise AdminUserDataInvariantError
        return value

    @staticmethod
    def _required_string(item: dict[str, object], name: str) -> str:
        value = item.get(name)
        if not isinstance(value, str) or not value:
            raise InvitationSagaInvariantError(f"role change field is invalid: {name}")
        return value

    @staticmethod
    def _required_int(item: dict[str, object], name: str) -> int:
        value = item.get(name)
        if type(value) is not int or value < 1:
            raise InvitationSagaInvariantError(f"role change field is invalid: {name}")
        return value

    @staticmethod
    def _error_code(error: ClientError) -> str:
        return str(error.response.get("Error", {}).get("Code", ""))
