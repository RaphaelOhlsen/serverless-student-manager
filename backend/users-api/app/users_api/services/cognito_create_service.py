from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from users_api.errors import (
    CognitoAliasExistsError,
    CognitoIdentityInvariantError,
    CognitoResultAmbiguousError,
    CognitoServiceError,
    CognitoUsernameExistsError,
    CognitoUserNotFoundError,
    InvitationSagaInvariantError,
)
from users_api.repositories.cognito_repository import ReconciledCognitoIdentity
from users_api.services.invitation_saga import (
    CREATE_USER_OPERATION,
    CognitoIdentityEvidence,
    CognitoReconciliationReason,
    CreateSagaState,
)


class CognitoRepositoryProtocol(Protocol):
    def admin_create_user(self, *, user_id: str, email: str) -> None: ...

    def admin_get_user(
        self,
        *,
        user_id: str,
        expected_email: str,
    ) -> ReconciledCognitoIdentity: ...


class InvitationSagaRepositoryProtocol(Protocol):
    def store_cognito_created(
        self,
        *,
        record: dict[str, object],
        cognito_sub: str,
        evidence: CognitoIdentityEvidence,
    ) -> None: ...

    def store_cognito_reconciliation_required(
        self,
        *,
        record: dict[str, object],
        reason: CognitoReconciliationReason,
    ) -> None: ...


class CognitoCreateOutcome(StrEnum):
    CREATED_AND_RECONCILED = "CREATED_AND_RECONCILED"
    EXISTING_AND_RECONCILED = "EXISTING_AND_RECONCILED"
    ABSENT_AFTER_AMBIGUOUS = "ABSENT_AFTER_AMBIGUOUS"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    ALREADY_COGNITO_CREATED = "ALREADY_COGNITO_CREATED"


@dataclass(frozen=True)
class CognitoCreateResult:
    outcome: CognitoCreateOutcome
    user_id: str
    cognito_sub: str | None


class CognitoCreateService:
    def __init__(
        self,
        cognito: CognitoRepositoryProtocol,
        saga: InvitationSagaRepositoryProtocol,
    ) -> None:
        self._cognito = cognito
        self._saga = saga

    def create_or_reconcile(
        self,
        *,
        record: dict[str, object],
        email: str,
    ) -> CognitoCreateResult:
        if self._required_string(record, "operation") != CREATE_USER_OPERATION:
            raise InvitationSagaInvariantError("Cognito create requires a create-user saga")
        user_id = self._required_string(record, "userId")
        state = self._required_string(record, "state")
        if state == CreateSagaState.COGNITO_CREATED.value:
            cognito_sub = self._required_uuid(record, "cognitoSub")
            evidence = record.get("cognitoEvidence")
            try:
                if not isinstance(evidence, str):
                    raise ValueError
                CognitoIdentityEvidence(evidence)
            except ValueError:
                raise InvitationSagaInvariantError("Cognito saga evidence is invalid") from None
            return CognitoCreateResult(
                outcome=CognitoCreateOutcome.ALREADY_COGNITO_CREATED,
                user_id=user_id,
                cognito_sub=cognito_sub,
            )
        if state == CreateSagaState.RECONCILIATION_REQUIRED.value:
            return CognitoCreateResult(
                outcome=CognitoCreateOutcome.RECONCILIATION_REQUIRED,
                user_id=user_id,
                cognito_sub=None,
            )
        if state != CreateSagaState.CLAIMED.value:
            raise InvitationSagaInvariantError("Cognito create requires a CLAIMED saga")

        try:
            self._cognito.admin_create_user(user_id=user_id, email=email)
        except CognitoUsernameExistsError:
            return self._read_back(
                record=record,
                email=email,
                evidence=CognitoIdentityEvidence.USERNAME_EXISTS,
                success_outcome=CognitoCreateOutcome.EXISTING_AND_RECONCILED,
                absent_reason=CognitoReconciliationReason.CREATE_RESULT_UNCERTAIN,
            )
        except CognitoAliasExistsError:
            return self._read_back(
                record=record,
                email=email,
                evidence=CognitoIdentityEvidence.ALIAS_ERROR_READBACK,
                success_outcome=CognitoCreateOutcome.EXISTING_AND_RECONCILED,
                absent_reason=CognitoReconciliationReason.ALIAS_CONFLICT,
            )
        except CognitoResultAmbiguousError:
            return self._read_back(
                record=record,
                email=email,
                evidence=CognitoIdentityEvidence.AMBIGUOUS_CREATE_READBACK,
                success_outcome=CognitoCreateOutcome.EXISTING_AND_RECONCILED,
                absent_is_safe_retry=True,
                absent_reason=CognitoReconciliationReason.CREATE_RESULT_UNCERTAIN,
            )

        return self._read_back(
            record=record,
            email=email,
            evidence=CognitoIdentityEvidence.CREATE_SUCCESS,
            success_outcome=CognitoCreateOutcome.CREATED_AND_RECONCILED,
            absent_reason=CognitoReconciliationReason.CREATE_RESULT_UNCERTAIN,
        )

    def _read_back(
        self,
        *,
        record: dict[str, object],
        email: str,
        evidence: CognitoIdentityEvidence,
        success_outcome: CognitoCreateOutcome,
        absent_reason: CognitoReconciliationReason,
        absent_is_safe_retry: bool = False,
    ) -> CognitoCreateResult:
        user_id = self._required_string(record, "userId")
        try:
            identity = self._cognito.admin_get_user(user_id=user_id, expected_email=email)
        except CognitoUserNotFoundError:
            if absent_is_safe_retry:
                return CognitoCreateResult(
                    outcome=CognitoCreateOutcome.ABSENT_AFTER_AMBIGUOUS,
                    user_id=user_id,
                    cognito_sub=None,
                )
            return self._mark_reconciliation(record, user_id=user_id, reason=absent_reason)
        except CognitoIdentityInvariantError:
            return self._mark_reconciliation(
                record,
                user_id=user_id,
                reason=CognitoReconciliationReason.IDENTITY_INCOMPATIBLE,
            )
        except (CognitoResultAmbiguousError, CognitoServiceError):
            return self._mark_reconciliation(
                record,
                user_id=user_id,
                reason=CognitoReconciliationReason.CREATE_RESULT_UNCERTAIN,
            )

        if identity.user_id != user_id or not self._is_canonical_uuid(identity.cognito_sub):
            return self._mark_reconciliation(
                record,
                user_id=user_id,
                reason=CognitoReconciliationReason.IDENTITY_INCOMPATIBLE,
            )
        self._saga.store_cognito_created(
            record=record,
            cognito_sub=identity.cognito_sub,
            evidence=evidence,
        )
        return CognitoCreateResult(
            outcome=success_outcome,
            user_id=user_id,
            cognito_sub=identity.cognito_sub,
        )

    def _mark_reconciliation(
        self,
        record: dict[str, object],
        *,
        user_id: str,
        reason: CognitoReconciliationReason,
    ) -> CognitoCreateResult:
        self._saga.store_cognito_reconciliation_required(record=record, reason=reason)
        return CognitoCreateResult(
            outcome=CognitoCreateOutcome.RECONCILIATION_REQUIRED,
            user_id=user_id,
            cognito_sub=None,
        )

    @staticmethod
    def _required_string(record: dict[str, object], field: str) -> str:
        value = record.get(field)
        if not isinstance(value, str) or not value:
            raise InvitationSagaInvariantError("Cognito saga context is invalid")
        return value

    @staticmethod
    def _required_uuid(record: dict[str, object], field: str) -> str:
        value = CognitoCreateService._required_string(record, field)
        if not CognitoCreateService._is_canonical_uuid(value):
            raise InvitationSagaInvariantError("Cognito saga identity is invalid")
        return value

    @staticmethod
    def _is_canonical_uuid(value: str) -> bool:
        try:
            return str(UUID(value)) == value
        except ValueError:
            return False
