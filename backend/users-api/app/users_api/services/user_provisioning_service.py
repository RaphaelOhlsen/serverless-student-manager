from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from aws_lambda_powertools import Logger
from botocore.exceptions import (  # type: ignore[import-untyped]
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from users_api.config import SERVICE_NAME
from users_api.errors import (
    CognitoIdentityInvariantError,
    CognitoResultAmbiguousError,
    CognitoServiceError,
    CognitoUserNotFoundError,
    InvitationSagaInvariantError,
    UserEmailAlreadyExistsError,
)
from users_api.repositories.cognito_repository import ReconciledCognitoIdentity
from users_api.services.invitation_saga import CreateSagaState, replay_from_record
from users_api.services.user_provisioning import (
    UserProvisioningItems,
    build_user_provisioning_items,
)
from users_api.validation import CreateUserInput

logger = Logger(service=SERVICE_NAME)

EMAIL_ALREADY_EXISTS = "EMAIL_ALREADY_EXISTS"
PROVISIONING_RECONCILIATION_REQUIRED = "USER_PROVISIONING_RECONCILIATION_REQUIRED"
COMPENSATION_INCOMPLETE = "COGNITO_COMPENSATION_INCOMPLETE"
_AMBIGUOUS_DDB_ERRORS = (
    ConnectTimeoutError,
    ReadTimeoutError,
    ConnectionClosedError,
    EndpointConnectionError,
)


class UserRepositoryProtocol(Protocol):
    def provision_invited_user(
        self,
        *,
        profile: dict[str, object],
        unique_email: dict[str, object],
        authorization: dict[str, object],
        audit: dict[str, object],
        saga_transition: dict[str, object],
        client_request_token: str,
    ) -> None: ...

    def get_profile(self, user_id: str) -> dict[str, object] | None: ...

    def get_email_reservation(self, normalized_email: str) -> dict[str, object] | None: ...

    def get_authorization(self, cognito_sub: str) -> dict[str, object] | None: ...

    def get_audit_event(
        self,
        *,
        user_id: str,
        occurred_at: str,
        event_id: str,
    ) -> dict[str, object] | None: ...


class SagaRepositoryProtocol(Protocol):
    def get(self, record_id: str) -> dict[str, object] | None: ...

    def build_transaction_transition(
        self,
        *,
        record: dict[str, object],
        next_state: str,
    ) -> dict[str, object]: ...

    def begin_cognito_compensation(
        self,
        *,
        record: dict[str, object],
        http_status: int,
        error_code: str,
    ) -> None: ...

    def complete_compensation(self, *, record: dict[str, object]) -> None: ...

    def store_provisioning_reconciliation_required(
        self,
        *,
        record: dict[str, object],
        reason: str,
    ) -> None: ...


class CognitoCompensationProtocol(Protocol):
    def admin_get_user(
        self,
        *,
        user_id: str,
        expected_email: str,
    ) -> ReconciledCognitoIdentity: ...

    def admin_delete_user(self, *, user_id: str) -> None: ...

    def admin_disable_user(self, *, user_id: str) -> None: ...


class ProvisioningOutcome(StrEnum):
    DDB_COMMITTED = "DDB_COMMITTED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


@dataclass(frozen=True)
class ProvisioningResult:
    outcome: ProvisioningOutcome
    user_id: str


@dataclass(frozen=True)
class ProvisioningSnapshot:
    profile: dict[str, object] | None
    unique_email: dict[str, object] | None
    authorization: dict[str, object] | None
    audit: dict[str, object] | None
    saga: dict[str, object] | None


class UserProvisioningService:
    def __init__(
        self,
        users: UserRepositoryProtocol,
        saga: SagaRepositoryProtocol,
        cognito: CognitoCompensationProtocol,
        *,
        audit_retention_days: int,
    ) -> None:
        self._users = users
        self._saga = saga
        self._cognito = cognito
        self._audit_retention_days = audit_retention_days

    def materialize(
        self,
        *,
        record: dict[str, object],
        user: CreateUserInput,
    ) -> ProvisioningResult:
        user_id = self._required_string(record, "userId")
        state = self._required_string(record, "state")
        if state == CreateSagaState.DDB_COMMITTED.value:
            return ProvisioningResult(ProvisioningOutcome.DDB_COMMITTED, user_id)
        if state == CreateSagaState.RECONCILIATION_REQUIRED.value:
            return ProvisioningResult(ProvisioningOutcome.RECONCILIATION_REQUIRED, user_id)
        if state == CreateSagaState.COMPENSATING.value:
            if self._resume_compensation(record, user):
                raise UserEmailAlreadyExistsError
            return ProvisioningResult(ProvisioningOutcome.RECONCILIATION_REQUIRED, user_id)
        if state == CreateSagaState.COMPLETED.value:
            replay = replay_from_record(record)
            if replay.error_code == EMAIL_ALREADY_EXISTS:
                raise UserEmailAlreadyExistsError
            raise InvitationSagaInvariantError("completed provisioning replay is incompatible")
        if state != CreateSagaState.COGNITO_CREATED.value:
            raise InvitationSagaInvariantError("materialization requires COGNITO_CREATED")

        items = build_user_provisioning_items(
            record=record,
            user=user,
            audit_retention_days=self._audit_retention_days,
        )
        saga_transition = self._saga.build_transaction_transition(
            record=record,
            next_state=CreateSagaState.DDB_COMMITTED.value,
        )
        try:
            self._write(items, saga_transition)
        except Exception as error:
            if self._is_ambiguous_dynamodb(error):
                return self._reconcile_ambiguous(record, user, items, saga_transition)
            if self._error_code(error) == "TransactionCanceledException":
                return self._reconcile_cancelled(record, user, items, saga_transition)
            raise
        return ProvisioningResult(ProvisioningOutcome.DDB_COMMITTED, user_id)

    def _reconcile_ambiguous(
        self,
        record: dict[str, object],
        user: CreateUserInput,
        items: UserProvisioningItems,
        saga_transition: dict[str, object],
    ) -> ProvisioningResult:
        try:
            snapshot = self._read_snapshot(record, user)
        except Exception:
            return self._mark_reconciliation(record)
        classification = self._classify_snapshot(record, items, snapshot)
        if classification == "COMMITTED":
            return ProvisioningResult(
                ProvisioningOutcome.DDB_COMMITTED,
                self._required_string(record, "userId"),
            )
        if classification == "ABSENT":
            try:
                self._write(items, saga_transition)
            except Exception:
                return self._resolve_failed_retry(record, user, items)
            return ProvisioningResult(
                ProvisioningOutcome.DDB_COMMITTED,
                self._required_string(record, "userId"),
            )
        return self._mark_reconciliation(record, reason=f"USER_PROVISIONING_{classification}")

    def _reconcile_cancelled(
        self,
        record: dict[str, object],
        user: CreateUserInput,
        items: UserProvisioningItems,
        saga_transition: dict[str, object],
    ) -> ProvisioningResult:
        try:
            snapshot = self._read_snapshot(record, user)
        except Exception:
            return self._mark_reconciliation(record)
        classification = self._classify_snapshot(record, items, snapshot)
        if classification == "COMMITTED":
            return ProvisioningResult(
                ProvisioningOutcome.DDB_COMMITTED,
                self._required_string(record, "userId"),
            )
        if classification == "EMAIL_CONFLICT":
            if self._compensate(
                record,
                user,
                http_status=409,
                error_code=EMAIL_ALREADY_EXISTS,
            ):
                raise UserEmailAlreadyExistsError
            return ProvisioningResult(
                ProvisioningOutcome.RECONCILIATION_REQUIRED,
                self._required_string(record, "userId"),
            )
        if classification == "ABSENT":
            try:
                self._write(items, saga_transition)
            except Exception as error:
                return self._resolve_failed_retry(
                    record,
                    user,
                    items,
                    allow_email_compensation=(
                        self._error_code(error) == "TransactionCanceledException"
                    ),
                )
            return ProvisioningResult(
                ProvisioningOutcome.DDB_COMMITTED,
                self._required_string(record, "userId"),
            )
        return self._mark_reconciliation(record, reason=f"USER_PROVISIONING_{classification}")

    def _resolve_failed_retry(
        self,
        record: dict[str, object],
        user: CreateUserInput,
        items: UserProvisioningItems,
        *,
        allow_email_compensation: bool = False,
    ) -> ProvisioningResult:
        try:
            snapshot = self._read_snapshot(record, user)
        except Exception:
            return self._mark_reconciliation(record)
        classification = self._classify_snapshot(record, items, snapshot)
        if classification == "COMMITTED":
            return ProvisioningResult(
                ProvisioningOutcome.DDB_COMMITTED,
                self._required_string(record, "userId"),
            )
        if classification == "EMAIL_CONFLICT" and allow_email_compensation:
            if self._compensate(
                record,
                user,
                http_status=409,
                error_code=EMAIL_ALREADY_EXISTS,
            ):
                raise UserEmailAlreadyExistsError
            return ProvisioningResult(
                ProvisioningOutcome.RECONCILIATION_REQUIRED,
                self._required_string(record, "userId"),
            )
        return self._mark_reconciliation(record, reason=f"USER_PROVISIONING_{classification}")

    def _write(
        self,
        items: UserProvisioningItems,
        saga_transition: dict[str, object],
    ) -> None:
        self._users.provision_invited_user(
            profile=items.profile,
            unique_email=items.unique_email,
            authorization=items.authorization,
            audit=items.audit,
            saga_transition=saga_transition,
            client_request_token=items.client_request_token,
        )

    def _read_snapshot(
        self,
        record: dict[str, object],
        user: CreateUserInput,
    ) -> ProvisioningSnapshot:
        user_id = self._required_string(record, "userId")
        cognito_sub = self._required_string(record, "cognitoSub")
        event_id = self._required_string(record, "eventId")
        occurred_at = self._required_string(record, "startedAt")
        return ProvisioningSnapshot(
            profile=self._users.get_profile(user_id),
            unique_email=self._users.get_email_reservation(user.email),
            authorization=self._users.get_authorization(cognito_sub),
            audit=self._users.get_audit_event(
                user_id=user_id,
                occurred_at=occurred_at,
                event_id=event_id,
            ),
            saga=self._saga.get(self._required_string(record, "id")),
        )

    @staticmethod
    def _classify_snapshot(
        record: dict[str, object],
        expected: UserProvisioningItems,
        actual: ProvisioningSnapshot,
    ) -> str:
        expected_domain = (
            expected.profile,
            expected.unique_email,
            expected.authorization,
            expected.audit,
        )
        actual_domain = (
            actual.profile,
            actual.unique_email,
            actual.authorization,
            actual.audit,
        )
        saga_state = actual.saga.get("state") if actual.saga is not None else None
        if (
            all(
                current is not None and UserProvisioningService._contains(current, wanted)
                for current, wanted in zip(actual_domain, expected_domain, strict=True)
            )
            and saga_state == CreateSagaState.DDB_COMMITTED.value
        ):
            return "COMMITTED"
        if (
            actual.profile is None
            and actual.authorization is None
            and actual.audit is None
            and actual.unique_email is not None
            and actual.unique_email.get("userId") != record.get("userId")
            and saga_state == CreateSagaState.COGNITO_CREATED.value
        ):
            return "EMAIL_CONFLICT"
        if (
            all(item is None for item in actual_domain)
            and saga_state == CreateSagaState.COGNITO_CREATED.value
        ):
            return "ABSENT"
        if actual.profile is not None and not UserProvisioningService._contains(
            actual.profile, expected.profile
        ):
            return "PROFILE_INCOMPATIBLE"
        if actual.authorization is not None and not UserProvisioningService._contains(
            actual.authorization, expected.authorization
        ):
            return "AUTHORIZATION_INCOMPATIBLE"
        if actual.audit is not None and not UserProvisioningService._contains(
            actual.audit, expected.audit
        ):
            return "AUDIT_INCOMPATIBLE"
        if saga_state not in {
            CreateSagaState.COGNITO_CREATED.value,
            CreateSagaState.DDB_COMMITTED.value,
        }:
            return "SAGA_INCOMPATIBLE"
        return "INCOMPATIBLE"

    def _compensate(
        self,
        record: dict[str, object],
        user: CreateUserInput,
        *,
        http_status: int,
        error_code: str,
    ) -> bool:
        user_id = self._required_string(record, "userId")
        expected_sub = self._required_string(record, "cognitoSub")
        try:
            identity = self._cognito.admin_get_user(user_id=user_id, expected_email=user.email)
        except CognitoUserNotFoundError:
            identity = None
        except (CognitoIdentityInvariantError, CognitoResultAmbiguousError, CognitoServiceError):
            self._mark_reconciliation(record)
            return False
        if identity is not None and identity.cognito_sub != expected_sub:
            self._mark_reconciliation(record)
            return False

        self._saga.begin_cognito_compensation(
            record=record,
            http_status=http_status,
            error_code=error_code,
        )
        compensating = {
            **record,
            "state": CreateSagaState.COMPENSATING.value,
            "terminalHttpStatus": http_status,
            "terminalErrorCode": error_code,
        }
        if identity is None:
            self._saga.complete_compensation(record=compensating)
            return True
        return self._delete_compensated_identity(compensating, user)

    def _resume_compensation(
        self,
        record: dict[str, object],
        user: CreateUserInput,
    ) -> bool:
        if record.get("terminalErrorCode") != EMAIL_ALREADY_EXISTS:
            self._mark_reconciliation(record, reason=COMPENSATION_INCOMPLETE)
            return False
        identity_state = self._compensation_identity_state(record, user)
        if identity_state == "ABSENT":
            self._saga.complete_compensation(record=record)
            return True
        if identity_state != "COMPATIBLE":
            self._report_compensation_failure(record, "resume_identity_unverified")
            self._mark_reconciliation(record, reason=COMPENSATION_INCOMPLETE)
            return False
        return self._delete_compensated_identity(record, user)

    def _delete_compensated_identity(
        self,
        record: dict[str, object],
        user: CreateUserInput,
    ) -> bool:
        user_id = self._required_string(record, "userId")
        try:
            self._cognito.admin_delete_user(user_id=user_id)
        except CognitoUserNotFoundError:
            self._saga.complete_compensation(record=record)
            return True
        except CognitoResultAmbiguousError:
            identity_state = self._compensation_identity_state(record, user)
            if identity_state == "ABSENT":
                self._saga.complete_compensation(record=record)
                return True
            if identity_state == "COMPATIBLE":
                self._disable_or_reconcile(record, user)
                return False
            self._report_compensation_failure(record, "delete_result_unresolved")
            self._mark_reconciliation(record, reason=COMPENSATION_INCOMPLETE)
            return False
        except CognitoServiceError:
            identity_state = self._compensation_identity_state(record, user)
            if identity_state == "ABSENT":
                self._saga.complete_compensation(record=record)
                return True
            if identity_state == "COMPATIBLE":
                self._disable_or_reconcile(record, user)
                return False
            self._report_compensation_failure(record, "delete_failed_identity_unverified")
            self._mark_reconciliation(record, reason=COMPENSATION_INCOMPLETE)
            return False
        self._saga.complete_compensation(record=record)
        return True

    def _compensation_identity_state(
        self,
        record: dict[str, object],
        user: CreateUserInput,
    ) -> str:
        try:
            identity = self._cognito.admin_get_user(
                user_id=self._required_string(record, "userId"),
                expected_email=user.email,
            )
        except CognitoUserNotFoundError:
            return "ABSENT"
        except CognitoIdentityInvariantError:
            return "INCOMPATIBLE"
        except (CognitoResultAmbiguousError, CognitoServiceError):
            return "UNCERTAIN"
        if identity.cognito_sub != self._required_string(record, "cognitoSub"):
            return "INCOMPATIBLE"
        return "COMPATIBLE"

    def _disable_or_reconcile(
        self,
        record: dict[str, object],
        user: CreateUserInput,
    ) -> None:
        if self._compensation_identity_state(record, user) != "COMPATIBLE":
            self._report_compensation_failure(record, "disable_identity_unverified")
            self._mark_reconciliation(record, reason=COMPENSATION_INCOMPLETE)
            return
        user_id = self._required_string(record, "userId")
        try:
            self._cognito.admin_disable_user(user_id=user_id)
        except CognitoUserNotFoundError:
            self._saga.complete_compensation(record=record)
            return
        except CognitoResultAmbiguousError:
            if self._compensation_identity_state(record, user) == "ABSENT":
                self._saga.complete_compensation(record=record)
                return
            self._report_compensation_failure(record, "disable_result_unresolved")
            self._mark_reconciliation(record, reason=COMPENSATION_INCOMPLETE)
            return
        except CognitoServiceError:
            self._report_compensation_failure(record, "disable_failed")
            self._mark_reconciliation(record, reason=COMPENSATION_INCOMPLETE)
            return
        self._report_compensation_failure(record, "identity_disabled")
        self._mark_reconciliation(record, reason=COMPENSATION_INCOMPLETE)

    def _mark_reconciliation(
        self,
        record: dict[str, object],
        *,
        reason: str = PROVISIONING_RECONCILIATION_REQUIRED,
    ) -> ProvisioningResult:
        self._saga.store_provisioning_reconciliation_required(record=record, reason=reason)
        return ProvisioningResult(
            ProvisioningOutcome.RECONCILIATION_REQUIRED,
            self._required_string(record, "userId"),
        )

    @staticmethod
    def _report_compensation_failure(record: dict[str, object], reason: str) -> None:
        logger.error(
            "Administrative user compensation requires reconciliation",
            extra={
                "stage": "create_user_compensation",
                "reason": reason,
                "correlationId": str(record.get("correlationId", "")),
            },
        )

    @staticmethod
    def _contains(actual: dict[str, object], expected: dict[str, object]) -> bool:
        return all(actual.get(key) == value for key, value in expected.items())

    @staticmethod
    def _is_ambiguous_dynamodb(error: Exception) -> bool:
        if isinstance(error, _AMBIGUOUS_DDB_ERRORS):
            return True
        if isinstance(error, ClientError):
            code = UserProvisioningService._error_code(error)
            status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            return code == "InternalServerError" or (type(status) is int and status >= 500)
        return False

    @staticmethod
    def _error_code(error: Exception) -> str | None:
        if not isinstance(error, ClientError):
            return None
        code = error.response.get("Error", {}).get("Code")
        return code if isinstance(code, str) else None

    @staticmethod
    def _required_string(record: dict[str, object], field: str) -> str:
        value = record.get(field)
        if not isinstance(value, str) or not value:
            raise InvitationSagaInvariantError("provisioning saga context is invalid")
        return value
