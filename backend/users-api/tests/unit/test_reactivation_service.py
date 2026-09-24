from copy import deepcopy
from dataclasses import dataclass
from uuid import UUID, uuid5

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from users_api.errors import (
    AdminUserForbiddenError,
    CognitoIdentityInvariantError,
    CognitoResultAmbiguousError,
    IdempotencyKeyReusedError,
    InvitationSagaInvariantError,
    OperationInProgressError,
    UserReactivationReconciliationError,
    UserStateConflictError,
    UserVersionConflictError,
)
from users_api.repositories.cognito_repository import ReconciledCognitoReactivationState
from users_api.services.invitation_saga import ReactivationState, SagaClaim
from users_api.services.reactivation_service import ReactivationService

ACTOR_ID = "11111111-1111-4111-8111-111111111111"
ACTOR_SUB = "22222222-2222-4222-8222-222222222222"
TARGET_ID = "33333333-3333-4333-8333-333333333333"
TARGET_SUB = "44444444-4444-4444-8444-444444444444"
KEY = "55555555-5555-4555-8555-555555555555"
EVENT_ID = "66666666-6666-4666-8666-666666666666"
STARTED_AT = "2026-09-23T14:00:00.000Z"


def transaction_cancelled() -> ClientError:
    return ClientError(
        {
            "Error": {"Code": "TransactionCanceledException", "Message": "private"},
            "CancellationReasons": [{"Code": "ConditionalCheckFailed"}],
        },
        "TransactWriteItems",
    )


class FakeSaga:
    def __init__(self, *, state: ReactivationState = ReactivationState.CLAIMED) -> None:
        self.record: dict[str, object] = {
            "id": f"HTTP#dev#{ACTOR_ID}#reactivate-user#{KEY}",
            "environment": "dev",
            "actorId": ACTOR_ID,
            "operation": "reactivate-user",
            "idempotencyKey": KEY,
            "requestHash": "stable-request-hash",
            "target": TARGET_ID,
            "state": state.value,
            "expectedVersion": 3,
            "eventId": EVENT_ID,
            "correlationId": "request-1",
            "startedAt": STARTED_AT,
            "updatedAt": STARTED_AT,
            "expiration": 1_900_000_000,
            "inProgressExpiration": 1_800_000_060_000,
        }
        self.claim_error: Exception | None = None
        self.claim_calls: list[dict[str, object]] = []
        self.transition_calls: list[str] = []
        self.transition_error: Exception | None = None
        self.transition_winner: ReactivationState | None = None
        self.marker_calls = 0
        self.builder_calls = 0
        if state in {
            ReactivationState.ENABLE_DISPATCHING,
            ReactivationState.COGNITO_ENABLED,
            ReactivationState.COMPLETED,
        }:
            self.add_marker()

    def add_marker(self, *, role: str = "OPERATOR") -> None:
        self.record.update(
            domainRole=role,
            cognitoSub=TARGET_SUB,
            observedVersion=3,
            observedAuthVersion=7,
            enableAttemptedAt=STARTED_AT,
        )

    def claim_reactivation(self, **kwargs: object) -> SagaClaim:
        self.claim_calls.append(dict(kwargs))
        if self.claim_error is not None:
            raise self.claim_error
        return SagaClaim(deepcopy(self.record), created=False)

    def get(self, record_id: str) -> dict[str, object] | None:
        if record_id != self.record["id"]:
            return None
        return deepcopy(self.record)

    def mark_reactivation_enable_dispatching(
        self,
        *,
        record: dict[str, object],
        role: str,
        cognito_sub: str,
        observed_version: int,
        observed_auth_version: int,
    ) -> None:
        assert record["state"] in {
            ReactivationState.CLAIMED.value,
            ReactivationState.RECONCILIATION_REQUIRED.value,
        }
        self.marker_calls += 1
        self.record.update(
            state=ReactivationState.ENABLE_DISPATCHING.value,
            domainRole=role,
            cognitoSub=cognito_sub,
            observedVersion=observed_version,
            observedAuthVersion=observed_auth_version,
            enableAttemptedAt=self.record.get("enableAttemptedAt", STARTED_AT),
        )

    def transition(self, *, record: dict[str, object], next_state: str) -> None:
        assert record["state"] == self.record["state"]
        self.transition_calls.append(next_state)
        if self.transition_error is not None:
            if self.transition_winner is not None:
                self.record["state"] = self.transition_winner.value
            raise self.transition_error
        self.record["state"] = next_state

    def build_reactivation_completion_transition(
        self,
        *,
        record: dict[str, object],
        response: dict[str, object],
    ) -> dict[str, object]:
        assert record["state"] == ReactivationState.COGNITO_ENABLED.value
        self.builder_calls += 1
        return {
            "recordId": record["id"],
            "requestHash": record["requestHash"],
            "response": deepcopy(response),
        }

    def complete(self, transition: dict[str, object]) -> None:
        assert transition["recordId"] == self.record["id"]
        assert transition["requestHash"] == self.record["requestHash"]
        response = transition["response"]
        assert isinstance(response, dict)
        self.record.update(
            state=ReactivationState.COMPLETED.value,
            httpStatus=200,
            responseUserId=response["userId"],
            responseFullName=response["fullName"],
            responseEmail=response["email"],
            responseRole=response["role"],
            responseStatus=response["status"],
            responseVersion=response["version"],
            responseCreatedAt=response["createdAt"],
            responseUpdatedAt=response["updatedAt"],
        )


class FakeUsers:
    def __init__(self, saga: FakeSaga, *, role: str = "OPERATOR") -> None:
        self.saga = saga
        self.transaction_error: Exception | None = None
        self.transaction_calls: list[dict[str, object]] = []
        self.profile_reads: list[str] = []
        self.authorizations: dict[str, dict[str, object]] = {
            ACTOR_SUB: {
                "userId": ACTOR_ID,
                "role": "ADMIN",
                "status": "ACTIVE",
                "authVersion": 5,
            },
            TARGET_SUB: {
                "userId": TARGET_ID,
                "role": role,
                "status": "INACTIVE",
                "authVersion": 7,
            },
        }
        self.profiles: dict[str, dict[str, object]] = {
            ACTOR_ID: {
                "PK": f"USER#{ACTOR_ID}",
                "SK": "PROFILE",
                "userId": ACTOR_ID,
                "cognitoSub": ACTOR_SUB,
                "fullName": "Synthetic Actor",
                "email": "actor@example.test",
                "role": "ADMIN",
                "status": "ACTIVE",
                "version": 4,
                "authVersion": 5,
                "createdAt": "2026-01-01T00:00:00.000Z",
            },
            TARGET_ID: {
                "PK": f"USER#{TARGET_ID}",
                "SK": "PROFILE",
                "userId": TARGET_ID,
                "cognitoSub": TARGET_SUB,
                "fullName": "Synthetic Target",
                "email": "TARGET@EXAMPLE.TEST",
                "role": role,
                "status": "INACTIVE",
                "version": 3,
                "authVersion": 7,
                "createdAt": "2026-02-01T00:00:00.000Z",
                "deactivatedAt": "2026-09-01T00:00:00.000Z",
            },
        }

    def get_authorization(self, cognito_sub: str) -> dict[str, object] | None:
        value = self.authorizations.get(cognito_sub)
        return deepcopy(value) if value is not None else None

    def get_profile(self, user_id: str) -> dict[str, object] | None:
        self.profile_reads.append(user_id)
        value = self.profiles.get(user_id)
        return deepcopy(value) if value is not None else None

    def reactivate_user(self, **kwargs: object) -> None:
        self.transaction_calls.append(deepcopy(dict(kwargs)))
        if self.transaction_error is not None:
            raise self.transaction_error
        transition = kwargs["idempotency_transition"]
        assert isinstance(transition, dict)
        self.saga.complete(transition)
        target = self.profiles[TARGET_ID]
        target.update(
            status="ACTIVE",
            version=4,
            authVersion=8,
            updatedAt=STARTED_AT,
            updatedBy=ACTOR_ID,
        )
        target.pop("deactivatedAt", None)
        authorization = self.authorizations[TARGET_SUB]
        authorization.update(status="ACTIVE", authVersion=8)


@dataclass(frozen=True)
class CognitoOutcome:
    enabled: bool


class FakeCognito:
    def __init__(
        self,
        *,
        reads: list[CognitoOutcome | Exception],
        enables: list[Exception | None] | None = None,
    ) -> None:
        self.reads = list(reads)
        self.enables = list(enables or [None])
        self.read_calls: list[dict[str, object]] = []
        self.enable_calls: list[str] = []

    def admin_get_reactivation_state(self, **kwargs: object) -> object:
        self.read_calls.append(dict(kwargs))
        outcome = self.reads.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        expected = kwargs["expected_enabled"]
        if expected is not None and outcome.enabled is not expected:
            raise CognitoIdentityInvariantError
        return ReconciledCognitoReactivationState(
            user_id=TARGET_ID,
            cognito_sub=TARGET_SUB,
            enabled=outcome.enabled,
        )

    def admin_enable_user(self, *, user_id: str) -> None:
        self.enable_calls.append(user_id)
        outcome = self.enables.pop(0)
        if outcome is not None:
            raise outcome


def build_service(
    *,
    role: str = "OPERATOR",
    state: ReactivationState = ReactivationState.CLAIMED,
    reads: list[CognitoOutcome | Exception] | None = None,
    enables: list[Exception | None] | None = None,
) -> tuple[ReactivationService, FakeUsers, FakeSaga, FakeCognito]:
    saga = FakeSaga(state=state)
    if state == ReactivationState.COMPLETED:
        saga.record.update(
            httpStatus=200,
            responseUserId=TARGET_ID,
            responseFullName="Synthetic Target",
            responseEmail="target@example.test",
            responseRole=role,
            responseStatus="ACTIVE",
            responseVersion=4,
            responseCreatedAt="2026-02-01T00:00:00.000Z",
            responseUpdatedAt=STARTED_AT,
        )
        saga.record["domainRole"] = role
    elif state != ReactivationState.CLAIMED:
        saga.record["domainRole"] = role
    users = FakeUsers(saga, role=role)
    cognito = FakeCognito(
        reads=reads if reads is not None else [CognitoOutcome(False), CognitoOutcome(True)],
        enables=enables,
    )
    service = ReactivationService(
        users,
        saga,
        cognito,
        environment="dev",
        audit_retention_days=365,
    )
    return service, users, saga, cognito


def execute(service: ReactivationService) -> dict[str, object]:
    return service.reactivate_user(
        cognito_sub=ACTOR_SUB,
        user_id=TARGET_ID,
        idempotency_key=KEY,
        request_id="request-1",
        body='{"expectedVersion":3}',
    )


@pytest.mark.parametrize("role", ["OPERATOR", "ADMIN"])
def test_happy_path_completes_once_with_public_response_and_stable_context(role: str) -> None:
    service, users, saga, cognito = build_service(role=role)

    response = execute(service)

    assert response == {
        "userId": TARGET_ID,
        "fullName": "Synthetic Target",
        "email": "target@example.test",
        "role": role,
        "status": "ACTIVE",
        "version": 4,
        "createdAt": "2026-02-01T00:00:00.000Z",
        "updatedAt": STARTED_AT,
    }
    assert saga.marker_calls == 1
    assert saga.transition_calls == [ReactivationState.COGNITO_ENABLED.value]
    assert saga.builder_calls == 1
    assert cognito.enable_calls == [TARGET_ID]
    assert [call["expected_enabled"] for call in cognito.read_calls] == [False, True]
    assert len(users.transaction_calls) == 1
    transaction = users.transaction_calls[0]
    assert transaction["role"] == role
    assert transaction["client_request_token"] == str(uuid5(UUID(int=0), str(saga.record["id"])))
    audit = transaction["audit"]
    assert isinstance(audit, dict)
    assert audit["eventId"] == EVENT_ID
    assert audit["eventType"] == "USER_REACTIVATED"
    assert audit["result"] == "SUCCESS"


def test_completed_replay_precedes_target_validation_and_has_zero_side_effects() -> None:
    service, users, saga, cognito = build_service(state=ReactivationState.COMPLETED)
    users.profiles.pop(TARGET_ID)
    users.authorizations.pop(TARGET_SUB)

    response = execute(service)

    assert response["status"] == "ACTIVE"
    assert TARGET_ID not in users.profile_reads
    assert cognito.read_calls == []
    assert cognito.enable_calls == []
    assert users.transaction_calls == []
    assert saga.builder_calls == 0


@pytest.mark.parametrize("error", [IdempotencyKeyReusedError(), OperationInProgressError()])
def test_claim_conflicts_stop_before_target_or_cognito(error: Exception) -> None:
    service, users, saga, cognito = build_service()
    saga.claim_error = error

    with pytest.raises(type(error)):
        execute(service)

    assert TARGET_ID not in users.profile_reads
    assert cognito.read_calls == []
    assert cognito.enable_calls == []
    assert users.transaction_calls == []


def test_stale_version_stops_before_cognito_side_effect() -> None:
    service, users, _, cognito = build_service()
    users.profiles[TARGET_ID]["version"] = 4

    with pytest.raises(UserVersionConflictError):
        execute(service)

    assert cognito.read_calls == []
    assert cognito.enable_calls == []
    assert users.transaction_calls == []


def test_actor_must_reconcile_as_active_admin_before_claim() -> None:
    service, users, saga, cognito = build_service()
    users.authorizations[ACTOR_SUB]["status"] = "INACTIVE"
    users.profiles[ACTOR_ID]["status"] = "INACTIVE"

    with pytest.raises(AdminUserForbiddenError):
        execute(service)

    assert saga.claim_calls == []
    assert cognito.read_calls == []
    assert cognito.enable_calls == []


def test_new_intent_requires_inactive_target_before_cognito() -> None:
    service, users, _, cognito = build_service()
    users.authorizations[TARGET_SUB]["status"] = "ACTIVE"
    users.profiles[TARGET_ID]["status"] = "ACTIVE"

    with pytest.raises(UserStateConflictError):
        execute(service)

    assert cognito.read_calls == []
    assert cognito.enable_calls == []
    assert users.transaction_calls == []


def test_ambiguous_enable_readback_true_does_not_repeat_enable() -> None:
    service, users, _, cognito = build_service(
        reads=[CognitoOutcome(False), CognitoOutcome(True), CognitoOutcome(True)],
        enables=[CognitoResultAmbiguousError()],
    )

    execute(service)

    assert cognito.enable_calls == [TARGET_ID]
    assert [call["expected_enabled"] for call in cognito.read_calls] == [False, None, True]
    assert len(users.transaction_calls) == 1


def test_ambiguous_enable_readback_false_allows_one_proven_retry() -> None:
    service, users, _, cognito = build_service(
        reads=[CognitoOutcome(False), CognitoOutcome(False), CognitoOutcome(True)],
        enables=[CognitoResultAmbiguousError(), None],
    )

    execute(service)

    assert cognito.enable_calls == [TARGET_ID, TARGET_ID]
    assert [call["expected_enabled"] for call in cognito.read_calls] == [False, None, True]
    assert len(users.transaction_calls) == 1


def test_second_ambiguous_result_is_read_back_before_reconciliation() -> None:
    service, users, saga, cognito = build_service(
        reads=[
            CognitoOutcome(False),
            CognitoOutcome(False),
            CognitoOutcome(False),
        ],
        enables=[CognitoResultAmbiguousError(), CognitoResultAmbiguousError()],
    )

    with pytest.raises(UserReactivationReconciliationError):
        execute(service)

    assert cognito.enable_calls == [TARGET_ID, TARGET_ID]
    assert [call["expected_enabled"] for call in cognito.read_calls] == [False, None, None]
    assert saga.record["state"] == ReactivationState.RECONCILIATION_REQUIRED.value
    assert users.transaction_calls == []


@pytest.mark.parametrize(
    ("state", "reads", "expected_enable_calls"),
    [
        (
            ReactivationState.ENABLE_DISPATCHING,
            [CognitoOutcome(False), CognitoOutcome(True)],
            1,
        ),
        (ReactivationState.ENABLE_DISPATCHING, [CognitoOutcome(True), CognitoOutcome(True)], 0),
        (ReactivationState.COGNITO_ENABLED, [CognitoOutcome(True)], 0),
    ],
)
def test_resume_durable_states_without_duplicate_side_effects(
    state: ReactivationState,
    reads: list[CognitoOutcome | Exception],
    expected_enable_calls: int,
) -> None:
    service, users, _, cognito = build_service(state=state, reads=reads)

    execute(service)

    assert len(cognito.enable_calls) == expected_enable_calls
    assert len(users.transaction_calls) == 1


def test_reconciliation_with_marker_adopts_compatible_enabled_identity() -> None:
    service, users, saga, cognito = build_service(
        state=ReactivationState.RECONCILIATION_REQUIRED,
        reads=[CognitoOutcome(True), CognitoOutcome(True)],
    )
    saga.add_marker()

    execute(service)

    assert cognito.enable_calls == []
    assert len(users.transaction_calls) == 1


def test_reconciliation_without_marker_requires_disabled_identity_before_enable() -> None:
    service, users, saga, cognito = build_service(
        state=ReactivationState.RECONCILIATION_REQUIRED,
        reads=[CognitoOutcome(False), CognitoOutcome(True)],
    )

    execute(service)

    assert saga.marker_calls == 1
    assert cognito.enable_calls == [TARGET_ID]
    assert len(users.transaction_calls) == 1


def test_reconciliation_without_marker_never_adopts_enabled_identity() -> None:
    service, users, saga, cognito = build_service(
        state=ReactivationState.RECONCILIATION_REQUIRED,
        reads=[CognitoOutcome(True)],
    )

    with pytest.raises(UserReactivationReconciliationError):
        execute(service)

    assert saga.record["state"] == ReactivationState.RECONCILIATION_REQUIRED.value
    assert cognito.enable_calls == []
    assert users.transaction_calls == []


def test_cognito_divergence_moves_claim_to_reconciliation_without_enable() -> None:
    service, users, saga, cognito = build_service(
        reads=[CognitoIdentityInvariantError("safe")],
    )

    with pytest.raises(UserReactivationReconciliationError):
        execute(service)

    assert saga.record["state"] == ReactivationState.RECONCILIATION_REQUIRED.value
    assert cognito.enable_calls == []
    assert users.transaction_calls == []


def test_post_enable_transaction_cancellation_is_reconciliation_not_version_conflict() -> None:
    service, users, saga, cognito = build_service()
    users.transaction_error = transaction_cancelled()

    with pytest.raises(UserReactivationReconciliationError):
        execute(service)

    assert cognito.enable_calls == [TARGET_ID]
    assert len(users.transaction_calls) == 1
    assert saga.record["state"] == ReactivationState.RECONCILIATION_REQUIRED.value


def test_success_then_replay_does_not_duplicate_cognito_transaction_audit_or_counter() -> None:
    service, users, saga, cognito = build_service(role="ADMIN")

    first = execute(service)
    second = execute(service)

    assert second == first
    assert cognito.enable_calls == [TARGET_ID]
    assert len(users.transaction_calls) == 1
    assert saga.builder_calls == 1
    audits = [call["audit"] for call in users.transaction_calls]
    assert len(audits) == 1
    assert users.transaction_calls[0]["role"] == "ADMIN"


def test_post_enable_domain_divergence_is_reconciliation_without_second_enable() -> None:
    service, users, saga, cognito = build_service(
        state=ReactivationState.COGNITO_ENABLED,
        reads=[CognitoOutcome(True)],
    )
    users.profiles[TARGET_ID]["version"] = 4

    with pytest.raises(UserReactivationReconciliationError):
        execute(service)

    assert saga.record["state"] == ReactivationState.RECONCILIATION_REQUIRED.value
    assert cognito.enable_calls == []
    assert users.transaction_calls == []


def test_service_never_exposes_a_disable_compensation_dependency() -> None:
    service, _, _, cognito = build_service()

    execute(service)

    assert not hasattr(cognito, "admin_disable_user")


@pytest.mark.parametrize(
    "winner",
    [
        ReactivationState.ENABLE_DISPATCHING,
        ReactivationState.COGNITO_ENABLED,
        ReactivationState.COMPLETED,
    ],
)
def test_reconciliation_cas_race_returns_safe_winning_state(winner: ReactivationState) -> None:
    service, _, saga, _ = build_service()
    saga.transition_error = InvitationSagaInvariantError()
    saga.transition_winner = winner

    result = service._mark_reconciliation(deepcopy(saga.record))

    assert result["state"] == winner.value
    assert saga.transition_calls == [ReactivationState.RECONCILIATION_REQUIRED.value]


def test_reconciliation_cas_race_fails_closed_for_incompatible_winner() -> None:
    service, _, saga, _ = build_service()
    saga.transition_error = InvitationSagaInvariantError()
    saga.transition_winner = ReactivationState.CLAIMED

    with pytest.raises(UserReactivationReconciliationError):
        service._mark_reconciliation(deepcopy(saga.record))


def test_client_request_token_is_stable_for_the_same_durable_operation() -> None:
    service, _, saga, _ = build_service()

    first = service._client_request_token(deepcopy(saga.record))
    second = service._client_request_token(deepcopy(saga.record))

    assert first == second
    assert str(UUID(first)) == first


def test_client_request_token_is_namespaced_beyond_the_public_idempotency_key() -> None:
    service, _, saga, _ = build_service()
    other = deepcopy(saga.record)
    other["id"] = f"HTTP#dev#different-actor#reactivate-user#{KEY}"

    original_token = service._client_request_token(deepcopy(saga.record))
    other_token = service._client_request_token(other)

    assert original_token != other_token
    assert str(UUID(other_token)) == other_token
