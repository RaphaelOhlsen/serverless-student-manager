from typing import Protocol

from aws_lambda_powertools import Logger

from users_api.config import SERVICE_NAME
from users_api.errors import (
    AdminUserForbiddenError,
    CognitoInvitationDeliveryError,
    CognitoResultAmbiguousError,
    InvitationDeliveryFailedError,
    InvitationDeliveryUncertainError,
    InvitationSagaInvariantError,
    UserCreateReconciliationError,
    UserEmailAlreadyExistsError,
)
from users_api.services.cognito_create_service import (
    CognitoCreateOutcome,
    CognitoCreateResult,
)
from users_api.services.invitation_saga import (
    INVITATION_DELIVERY_FAILED,
    INVITATION_DELIVERY_UNCERTAIN,
    CognitoReconciliationReason,
    CreateSagaState,
    SagaClaim,
    replay_from_record,
)
from users_api.services.user_provisioning_service import (
    ProvisioningOutcome,
    ProvisioningResult,
)
from users_api.services.user_state import UserStateReconciliationError, reconcile_user_state
from users_api.validation import (
    CreateUserInput,
    parse_create_user_body,
    validate_idempotency_key,
)

logger = Logger(service=SERVICE_NAME)


class UserStateRepositoryProtocol(Protocol):
    def get_authorization(self, cognito_sub: str) -> dict[str, object] | None: ...

    def get_profile(self, user_id: str) -> dict[str, object] | None: ...


class CreateSagaRepositoryProtocol(Protocol):
    def claim_create(
        self,
        *,
        environment: str,
        actor_id: str,
        idempotency_key: str,
        full_name: str,
        email: str,
        role: str,
        request_id: str | None,
    ) -> SagaClaim: ...

    def get(self, record_id: str) -> dict[str, object] | None: ...

    def transition(self, *, record: dict[str, object], next_state: str) -> None: ...

    def store_completed(
        self,
        *,
        record: dict[str, object],
        http_status: int,
        response_user_id: str | None = None,
    ) -> None: ...

    def store_delivery_failure(
        self,
        *,
        record: dict[str, object],
        retryable_state: str,
        error_code: str,
    ) -> None: ...

    def store_cognito_reconciliation_required(
        self,
        *,
        record: dict[str, object],
        reason: CognitoReconciliationReason,
    ) -> None: ...


class InvitationRepositoryProtocol(Protocol):
    def admin_resend_invitation(self, *, user_id: str) -> None: ...


class CognitoCreateServiceProtocol(Protocol):
    def create_or_reconcile(
        self,
        *,
        record: dict[str, object],
        email: str,
    ) -> CognitoCreateResult: ...


class ProvisioningServiceProtocol(Protocol):
    def materialize(
        self,
        *,
        record: dict[str, object],
        user: CreateUserInput,
    ) -> ProvisioningResult: ...


class CreateUserService:
    def __init__(
        self,
        users: UserStateRepositoryProtocol,
        saga: CreateSagaRepositoryProtocol,
        cognito_create: CognitoCreateServiceProtocol,
        provisioning: ProvisioningServiceProtocol,
        invitations: InvitationRepositoryProtocol,
        *,
        environment: str,
    ) -> None:
        self._users = users
        self._saga = saga
        self._cognito_create = cognito_create
        self._provisioning = provisioning
        self._invitations = invitations
        self._environment = environment

    def create_user(
        self,
        *,
        cognito_sub: str,
        idempotency_key: object,
        request_id: str | None,
        body: str,
    ) -> dict[str, object]:
        actor_id = self._authorize(cognito_sub)
        key = validate_idempotency_key(idempotency_key)
        user = parse_create_user_body(body)
        claim = self._saga.claim_create(
            environment=self._environment,
            actor_id=actor_id,
            idempotency_key=key,
            full_name=user.full_name,
            email=user.email,
            role=user.role,
            request_id=request_id,
        )
        return self._resume(claim.record, user)

    def _resume(
        self,
        record: dict[str, object],
        user: CreateUserInput,
    ) -> dict[str, object]:
        state = self._state(record)
        if state == CreateSagaState.COMPLETED:
            return self._replay(record, user)
        if state == CreateSagaState.RECONCILIATION_REQUIRED:
            self._raise_reconciliation(record)
        if state == CreateSagaState.INVITATION_DISPATCHING:
            self._mark_uncertain(record, reason="dispatch_state_recovered")
        if state == CreateSagaState.INVITATION_SENT:
            return self._complete(record, user)

        if state == CreateSagaState.CLAIMED:
            self._create_identity(record, user)
            record = self._reload(record)
            state = self._state(record)
            if state == CreateSagaState.RECONCILIATION_REQUIRED:
                self._raise_reconciliation(record)

        if state in {CreateSagaState.COGNITO_CREATED, CreateSagaState.COMPENSATING}:
            result = self._provisioning.materialize(record=record, user=user)
            if result.outcome == ProvisioningOutcome.RECONCILIATION_REQUIRED:
                raise UserCreateReconciliationError
            record = self._reload(record)
            state = self._state(record)

        if state in {CreateSagaState.DDB_COMMITTED, CreateSagaState.INVITATION_RETRYABLE}:
            return self._dispatch(record, user)
        if state == CreateSagaState.INVITATION_SENT:
            return self._complete(record, user)
        if state == CreateSagaState.COMPLETED:
            return self._replay(record, user)
        if state == CreateSagaState.RECONCILIATION_REQUIRED:
            self._raise_reconciliation(record)
        raise InvitationSagaInvariantError("create-user saga cannot be resumed")

    def _create_identity(self, record: dict[str, object], user: CreateUserInput) -> None:
        first = self._cognito_create.create_or_reconcile(record=record, email=user.email)
        if first.outcome != CognitoCreateOutcome.ABSENT_AFTER_AMBIGUOUS:
            return
        second = self._cognito_create.create_or_reconcile(record=record, email=user.email)
        if second.outcome == CognitoCreateOutcome.ABSENT_AFTER_AMBIGUOUS:
            self._saga.store_cognito_reconciliation_required(
                record=record,
                reason=CognitoReconciliationReason.CREATE_RESULT_UNCERTAIN,
            )

    def _dispatch(
        self,
        record: dict[str, object],
        user: CreateUserInput,
    ) -> dict[str, object]:
        self._saga.transition(
            record=record,
            next_state=CreateSagaState.INVITATION_DISPATCHING.value,
        )
        dispatching = self._reload(record)
        try:
            self._invitations.admin_resend_invitation(
                user_id=self._required_string(dispatching, "userId")
            )
        except CognitoInvitationDeliveryError:
            self._saga.store_delivery_failure(
                record=dispatching,
                retryable_state=CreateSagaState.INVITATION_RETRYABLE.value,
                error_code=INVITATION_DELIVERY_FAILED,
            )
            self._log_delivery(record, "delivery_not_applied")
            raise InvitationDeliveryFailedError from None
        except CognitoResultAmbiguousError:
            self._mark_uncertain(dispatching, reason="delivery_result_ambiguous")
        except Exception:
            self._mark_uncertain(dispatching, reason="delivery_result_inconclusive")

        try:
            self._saga.transition(
                record=dispatching,
                next_state=CreateSagaState.INVITATION_SENT.value,
            )
        except Exception:
            current = self._reload(record)
            current_state = self._state(current)
            if current_state not in {
                CreateSagaState.INVITATION_SENT,
                CreateSagaState.COMPLETED,
            }:
                if current_state == CreateSagaState.INVITATION_DISPATCHING:
                    self._mark_uncertain(current, reason="delivery_success_transition_failed")
                raise
        return self._complete(self._reload(record), user)

    def _complete(
        self,
        record: dict[str, object],
        user: CreateUserInput,
    ) -> dict[str, object]:
        if self._state(record) == CreateSagaState.COMPLETED:
            return self._replay(record, user)
        if self._state(record) != CreateSagaState.INVITATION_SENT:
            raise InvitationSagaInvariantError("create completion requires INVITATION_SENT")
        user_id = self._required_string(record, "userId")
        try:
            self._saga.store_completed(record=record, http_status=201, response_user_id=user_id)
        except Exception:
            current = self._reload(record)
            if self._state(current) == CreateSagaState.COMPLETED:
                return self._replay(current, user)
            raise
        return self._public_user(record, user)

    def _replay(
        self,
        record: dict[str, object],
        user: CreateUserInput,
    ) -> dict[str, object]:
        replay = replay_from_record(record)
        if replay.http_status == 201 and replay.response_user_id == record.get("userId"):
            return self._public_user(record, user)
        if replay.error_code == "EMAIL_ALREADY_EXISTS":
            raise UserEmailAlreadyExistsError
        raise InvitationSagaInvariantError("create-user terminal replay is incompatible")

    def _mark_uncertain(self, record: dict[str, object], *, reason: str) -> None:
        self._saga.store_delivery_failure(
            record=record,
            retryable_state=CreateSagaState.RECONCILIATION_REQUIRED.value,
            error_code=INVITATION_DELIVERY_UNCERTAIN,
        )
        self._log_delivery(record, reason)
        raise InvitationDeliveryUncertainError

    def _raise_reconciliation(self, record: dict[str, object]) -> None:
        if record.get("errorCode") == INVITATION_DELIVERY_UNCERTAIN:
            raise InvitationDeliveryUncertainError
        raise UserCreateReconciliationError

    def _reload(self, record: dict[str, object]) -> dict[str, object]:
        current = self._saga.get(self._required_string(record, "id"))
        if current is None:
            raise InvitationSagaInvariantError("create-user saga disappeared")
        return current

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

    @staticmethod
    def _public_user(record: dict[str, object], user: CreateUserInput) -> dict[str, object]:
        timestamp = CreateUserService._required_string(record, "startedAt")
        return {
            "userId": CreateUserService._required_string(record, "userId"),
            "fullName": user.full_name,
            "email": user.email,
            "role": user.role,
            "status": "INVITED",
            "version": 1,
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }

    @staticmethod
    def _state(record: dict[str, object]) -> CreateSagaState:
        try:
            return CreateSagaState(CreateUserService._required_string(record, "state"))
        except ValueError:
            raise InvitationSagaInvariantError("create-user saga state is invalid") from None

    @staticmethod
    def _required_string(record: dict[str, object], field: str) -> str:
        value = record.get(field)
        if not isinstance(value, str) or not value:
            raise InvitationSagaInvariantError("create-user saga context is invalid")
        return value

    @staticmethod
    def _log_delivery(record: dict[str, object], reason: str) -> None:
        logger.warning(
            "Administrative user invitation delivery did not complete",
            extra={
                "stage": "create_user_invitation",
                "reason": reason,
                "correlationId": str(record.get("correlationId", "")),
            },
        )
