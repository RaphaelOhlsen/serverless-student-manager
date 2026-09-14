from collections.abc import Iterable

import pytest
from users_api.errors import (
    CognitoAliasExistsError,
    CognitoCreateDeterministicError,
    CognitoIdentityInvariantError,
    CognitoResultAmbiguousError,
    CognitoServiceError,
    CognitoUsernameExistsError,
    CognitoUserNotFoundError,
    InvitationSagaConcurrentTransitionError,
    InvitationSagaInvariantError,
)
from users_api.repositories.cognito_repository import ReconciledCognitoIdentity
from users_api.services.cognito_create_service import (
    CognitoCreateOutcome,
    CognitoCreateService,
)
from users_api.services.invitation_saga import (
    CognitoIdentityEvidence,
    CognitoReconciliationReason,
    CreateSagaState,
)

USER_ID = "11111111-1111-4111-8111-111111111111"
COGNITO_SUB = "22222222-2222-4222-8222-222222222222"
EMAIL = "admin@example.test"


def claimed_record() -> dict[str, object]:
    return {
        "id": "HTTP#dev#actor#create-user#key",
        "operation": "create-user",
        "state": CreateSagaState.CLAIMED.value,
        "userId": USER_ID,
        "requestHash": "safe-hash",
    }


class FakeCognitoRepository:
    def __init__(
        self,
        *,
        create_outcomes: Iterable[Exception | None] = (None,),
        get_outcomes: Iterable[Exception | ReconciledCognitoIdentity] = (
            ReconciledCognitoIdentity(USER_ID, COGNITO_SUB),
        ),
    ) -> None:
        self._create_outcomes = iter(create_outcomes)
        self._get_outcomes = iter(get_outcomes)
        self.create_calls: list[dict[str, str]] = []
        self.get_calls: list[dict[str, str]] = []

    def admin_create_user(self, *, user_id: str, email: str) -> None:
        self.create_calls.append({"userId": user_id, "email": email})
        outcome = next(self._create_outcomes)
        if outcome is not None:
            raise outcome

    def admin_get_user(
        self,
        *,
        user_id: str,
        expected_email: str,
    ) -> ReconciledCognitoIdentity:
        self.get_calls.append({"userId": user_id, "email": expected_email})
        outcome = next(self._get_outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeSagaRepository:
    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []
        self.reconciliation: list[dict[str, object]] = []
        self.error: Exception | None = None

    def store_cognito_created(
        self,
        *,
        record: dict[str, object],
        cognito_sub: str,
        evidence: CognitoIdentityEvidence,
    ) -> None:
        if self.error is not None:
            raise self.error
        self.created.append(
            {"recordId": record["id"], "cognitoSub": cognito_sub, "evidence": evidence}
        )

    def store_cognito_reconciliation_required(
        self,
        *,
        record: dict[str, object],
        reason: CognitoReconciliationReason,
    ) -> None:
        if self.error is not None:
            raise self.error
        self.reconciliation.append({"recordId": record["id"], "reason": reason})


def service(
    cognito: FakeCognitoRepository,
    saga: FakeSagaRepository | None = None,
) -> tuple[CognitoCreateService, FakeSagaRepository]:
    saga = saga or FakeSagaRepository()
    return CognitoCreateService(cognito, saga), saga


def test_create_success_requires_compatible_readback_before_cognito_created() -> None:
    cognito = FakeCognitoRepository()
    subject, saga = service(cognito)
    result = subject.create_or_reconcile(record=claimed_record(), email=EMAIL)

    assert result.outcome == CognitoCreateOutcome.CREATED_AND_RECONCILED
    assert result.user_id == USER_ID
    assert result.cognito_sub == COGNITO_SUB
    assert saga.created == [
        {
            "recordId": claimed_record()["id"],
            "cognitoSub": COGNITO_SUB,
            "evidence": CognitoIdentityEvidence.CREATE_SUCCESS,
        }
    ]
    assert len(cognito.create_calls) == len(cognito.get_calls) == 1


@pytest.mark.parametrize(
    "create_error",
    [CognitoUsernameExistsError(), CognitoResultAmbiguousError()],
)
def test_existing_or_ambiguous_create_adopts_only_compatible_readback(
    create_error: Exception,
) -> None:
    cognito = FakeCognitoRepository(create_outcomes=[create_error])
    subject, saga = service(cognito)
    result = subject.create_or_reconcile(record=claimed_record(), email=EMAIL)

    assert result.outcome == CognitoCreateOutcome.EXISTING_AND_RECONCILED
    assert result.cognito_sub == COGNITO_SUB
    assert saga.created[0]["cognitoSub"] == COGNITO_SUB


@pytest.mark.parametrize(
    "create_error",
    [None, CognitoUsernameExistsError()],
)
def test_success_or_username_exists_with_incompatible_readback_requires_reconciliation(
    create_error: Exception | None,
) -> None:
    cognito = FakeCognitoRepository(
        create_outcomes=[create_error],
        get_outcomes=[CognitoIdentityInvariantError()],
    )
    subject, saga = service(cognito)
    result = subject.create_or_reconcile(record=claimed_record(), email=EMAIL)

    assert result.outcome == CognitoCreateOutcome.RECONCILIATION_REQUIRED
    assert saga.reconciliation[0]["reason"] == CognitoReconciliationReason.IDENTITY_INCOMPATIBLE
    assert saga.created == []


def test_ambiguous_create_and_conclusive_absence_can_retry_same_user_id() -> None:
    cognito = FakeCognitoRepository(
        create_outcomes=[CognitoResultAmbiguousError(), None],
        get_outcomes=[
            CognitoUserNotFoundError(),
            ReconciledCognitoIdentity(USER_ID, COGNITO_SUB),
        ],
    )
    subject, saga = service(cognito)
    record = claimed_record()

    first = subject.create_or_reconcile(record=record, email=EMAIL)
    second = subject.create_or_reconcile(record=record, email=EMAIL)

    assert first.outcome == CognitoCreateOutcome.ABSENT_AFTER_AMBIGUOUS
    assert second.outcome == CognitoCreateOutcome.CREATED_AND_RECONCILED
    assert [call["userId"] for call in cognito.create_calls] == [USER_ID, USER_ID]
    assert saga.reconciliation == []


@pytest.mark.parametrize(
    "read_error",
    [CognitoResultAmbiguousError(), CognitoServiceError()],
)
def test_ambiguous_create_and_inconclusive_readback_requires_reconciliation(
    read_error: Exception,
) -> None:
    cognito = FakeCognitoRepository(
        create_outcomes=[CognitoResultAmbiguousError()],
        get_outcomes=[read_error],
    )
    subject, saga = service(cognito)
    result = subject.create_or_reconcile(record=claimed_record(), email=EMAIL)

    assert result.outcome == CognitoCreateOutcome.RECONCILIATION_REQUIRED
    assert saga.reconciliation[0]["reason"] == CognitoReconciliationReason.CREATE_RESULT_UNCERTAIN


def test_alias_exists_never_becomes_email_business_conflict_or_takeover() -> None:
    cognito = FakeCognitoRepository(
        create_outcomes=[CognitoAliasExistsError()],
        get_outcomes=[CognitoUserNotFoundError()],
    )
    subject, saga = service(cognito)
    result = subject.create_or_reconcile(record=claimed_record(), email=EMAIL)

    assert result.outcome == CognitoCreateOutcome.RECONCILIATION_REQUIRED
    assert saga.reconciliation[0]["reason"] == CognitoReconciliationReason.ALIAS_CONFLICT
    assert len(cognito.create_calls) == 1


def test_alias_error_can_only_adopt_the_same_compatible_stable_identity() -> None:
    cognito = FakeCognitoRepository(create_outcomes=[CognitoAliasExistsError()])
    subject, saga = service(cognito)

    result = subject.create_or_reconcile(record=claimed_record(), email=EMAIL)

    assert result.outcome == CognitoCreateOutcome.EXISTING_AND_RECONCILED
    assert result.user_id == USER_ID
    assert result.cognito_sub == COGNITO_SUB
    assert saga.created[0]["evidence"] == CognitoIdentityEvidence.ALIAS_ERROR_READBACK


def test_cognito_created_replay_uses_durable_sub_without_cognito_calls() -> None:
    cognito = FakeCognitoRepository(create_outcomes=[])
    subject, saga = service(cognito)
    record = claimed_record()
    record.update(
        state=CreateSagaState.COGNITO_CREATED.value,
        cognitoSub=COGNITO_SUB,
        cognitoEvidence=CognitoIdentityEvidence.CREATE_SUCCESS.value,
    )

    result = subject.create_or_reconcile(record=record, email=EMAIL)

    assert result.outcome == CognitoCreateOutcome.ALREADY_COGNITO_CREATED
    assert result.cognito_sub == COGNITO_SUB
    assert cognito.create_calls == cognito.get_calls == []
    assert saga.created == saga.reconciliation == []


def test_cognito_created_replay_requires_durable_identity_evidence() -> None:
    cognito = FakeCognitoRepository(create_outcomes=[])
    subject, _ = service(cognito)
    record = claimed_record()
    record.update(state=CreateSagaState.COGNITO_CREATED.value, cognitoSub=COGNITO_SUB)

    with pytest.raises(InvitationSagaInvariantError, match="evidence"):
        subject.create_or_reconcile(record=record, email=EMAIL)
    assert cognito.create_calls == cognito.get_calls == []


def test_repository_identity_mismatch_is_not_adopted() -> None:
    cognito = FakeCognitoRepository(
        get_outcomes=[ReconciledCognitoIdentity("other-user", COGNITO_SUB)]
    )
    subject, saga = service(cognito)

    result = subject.create_or_reconcile(record=claimed_record(), email=EMAIL)

    assert result.outcome == CognitoCreateOutcome.RECONCILIATION_REQUIRED
    assert saga.created == []
    assert saga.reconciliation[0]["reason"] == CognitoReconciliationReason.IDENTITY_INCOMPATIBLE


def test_reconciliation_required_replay_never_retries_create() -> None:
    cognito = FakeCognitoRepository(create_outcomes=[])
    subject, saga = service(cognito)
    record = claimed_record()
    record["state"] = CreateSagaState.RECONCILIATION_REQUIRED.value

    result = subject.create_or_reconcile(record=record, email=EMAIL)

    assert result.outcome == CognitoCreateOutcome.RECONCILIATION_REQUIRED
    assert cognito.create_calls == cognito.get_calls == []
    assert saga.created == saga.reconciliation == []


def test_stale_cas_is_not_silently_treated_as_success() -> None:
    cognito = FakeCognitoRepository()
    saga = FakeSagaRepository()
    saga.error = InvitationSagaConcurrentTransitionError()
    subject, _ = service(cognito, saga)

    with pytest.raises(InvitationSagaConcurrentTransitionError):
        subject.create_or_reconcile(record=claimed_record(), email=EMAIL)


def test_deterministic_create_failure_is_preserved_without_readback_or_state_change() -> None:
    error = CognitoCreateDeterministicError()
    cognito = FakeCognitoRepository(create_outcomes=[error])
    subject, saga = service(cognito)

    with pytest.raises(CognitoCreateDeterministicError):
        subject.create_or_reconcile(record=claimed_record(), email=EMAIL)
    assert cognito.get_calls == []
    assert saga.created == saga.reconciliation == []


def test_saga_persistence_contains_no_raw_pii() -> None:
    cognito = FakeCognitoRepository()
    subject, saga = service(cognito)
    subject.create_or_reconcile(record=claimed_record(), email=EMAIL)

    persisted = repr(saga.created) + repr(saga.reconciliation)
    assert EMAIL not in persisted
    assert "requestBody" not in persisted
    assert "TemporaryPassword" not in persisted
