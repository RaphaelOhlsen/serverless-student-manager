from collections.abc import Iterable

import pytest
from users_api.errors import (
    AdminUserForbiddenError,
    AdminUserNotFoundError,
    CognitoInvitationDeliveryError,
    CognitoResultAmbiguousError,
    InvitationDeliveryFailedError,
    InvitationDeliveryUncertainError,
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
)
from users_api.services.resend_invitation_service import ResendInvitationService

KEY = "44444444-4444-4444-8444-444444444444"
NEW_KEY = "55555555-5555-4555-8555-555555555555"
TARGET = "target-1"
TARGET_SUB = "22222222-2222-4222-8222-222222222222"
BODY = '{"expectedVersion":3}'


def record(state: ResendSagaState = ResendSagaState.CLAIMED) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "HTTP#dev#actor-1#resend-user-invitation#key",
        "environment": "dev",
        "actorId": "actor-1",
        "operation": "resend-user-invitation",
        "target": TARGET,
        "idempotencyKey": KEY,
        "requestHash": "safe-hash",
        "state": state.value,
        "eventId": "33333333-3333-4333-8333-333333333333",
        "correlationId": "request-1",
        "expectedVersion": 3,
        "startedAt": "2026-09-14T12:00:00.000Z",
        "expiration": 1,
        "inProgressExpiration": 1,
    }
    if state == ResendSagaState.COMPLETED:
        value["httpStatus"] = 204
    return value


class FakeSaga:
    def __init__(self, state: ResendSagaState = ResendSagaState.CLAIMED) -> None:
        self.current = record(state)
        self.transitions: list[tuple[str, str]] = []
        self.failures: list[tuple[str, str]] = []
        self.claims = 0
        self.claim_keys: list[object] = []

    def claim_resend(self, **kwargs: object) -> SagaClaim:
        self.claims += 1
        self.claim_keys.append(kwargs["idempotency_key"])
        assert kwargs["actor_id"] == "actor-1"
        assert kwargs["user_id"] == TARGET
        assert kwargs["expected_version"] == 3
        return SagaClaim(dict(self.current), created=self.current["state"] == "CLAIMED")

    def get(self, record_id: str) -> dict[str, object] | None:
        assert record_id == self.current["id"]
        return dict(self.current)

    def transition(self, *, record: dict[str, object], next_state: str) -> None:
        self.transitions.append((str(record["state"]), next_state))
        self.current["state"] = next_state
        if record["state"] == ResendSagaState.RETRYABLE.value:
            self.current.pop("httpStatus", None)
            self.current.pop("errorCode", None)

    def store_delivery_failure(
        self, *, record: dict[str, object], retryable_state: str, error_code: str
    ) -> None:
        self.failures.append((retryable_state, error_code))
        self.current.update(state=retryable_state, httpStatus=503, errorCode=error_code)

    def build_resend_completion_transition(self, *, record: dict[str, object]) -> dict[str, object]:
        return {"Update": {"TableName": "idempotency", "state": "COMPLETED"}}


class FakeUsers:
    def __init__(
        self,
        saga: FakeSaga,
        *,
        actor_role: str = "ADMIN",
        actor_status: str = "ACTIVE",
        target_status: str = "INVITED",
        target_version: int = 3,
    ) -> None:
        self.saga = saga
        self.actor_authorization = {
            "userId": "actor-1",
            "role": actor_role,
            "status": actor_status,
            "authVersion": 1,
        }
        self.actor_profile = {
            **self.actor_authorization,
            "cognitoSub": "actor-sub",
        }
        self.target_profile: dict[str, object] | None = {
            "PK": f"USER#{TARGET}",
            "SK": "PROFILE",
            "userId": TARGET,
            "cognitoSub": TARGET_SUB,
            "fullName": "Synthetic Target",
            "email": "target@example.test",
            "role": "OPERATOR",
            "status": target_status,
            "version": target_version,
            "authVersion": 1,
        }
        self.target_authorization = {
            "userId": TARGET,
            "role": "OPERATOR",
            "status": target_status,
            "authVersion": 1,
        }
        self.target_reads = 0
        self.completions: list[dict[str, object]] = []
        self.completion_errors: list[Exception] = []

    def get_authorization(self, cognito_sub: str) -> dict[str, object] | None:
        if cognito_sub == "actor-sub":
            return self.actor_authorization
        if cognito_sub == TARGET_SUB:
            return self.target_authorization
        return None

    def get_profile(self, user_id: str) -> dict[str, object] | None:
        if user_id == "actor-1":
            return self.actor_profile
        if user_id == TARGET:
            self.target_reads += 1
            return self.target_profile
        return None

    def complete_invitation_resend(self, **kwargs: object) -> None:
        if self.completion_errors:
            raise self.completion_errors.pop(0)
        self.completions.append(kwargs)
        self.saga.current.update(state="COMPLETED", httpStatus=204)


class FakeCognito:
    def __init__(self, outcomes: Iterable[Exception | None] = (None,)) -> None:
        self.outcomes = iter(outcomes)
        self.reads: list[tuple[str, str]] = []
        self.resends: list[str] = []
        self.identity = ReconciledCognitoIdentity(TARGET, TARGET_SUB)

    def admin_get_user(self, *, user_id: str, expected_email: str) -> ReconciledCognitoIdentity:
        self.reads.append((user_id, expected_email))
        return self.identity

    def admin_resend_invitation(self, *, user_id: str) -> None:
        self.resends.append(user_id)
        outcome = next(self.outcomes)
        if outcome is not None:
            raise outcome


def make_service(
    saga: FakeSaga,
    *,
    users: FakeUsers | None = None,
    cognito: FakeCognito | None = None,
) -> tuple[ResendInvitationService, FakeUsers, FakeCognito]:
    users = users or FakeUsers(saga)
    cognito = cognito or FakeCognito()
    return (
        ResendInvitationService(
            users,
            saga,
            cognito,
            environment="dev",
            audit_retention_days=90,
        ),
        users,
        cognito,
    )


def invoke(service: ResendInvitationService, *, key: str = KEY) -> None:
    service.resend_invitation(
        cognito_sub="actor-sub",
        user_id=TARGET,
        idempotency_key=key,
        request_id="request-1",
        body=BODY,
    )


def test_happy_path_reconciles_dispatches_and_atomically_completes_audit() -> None:
    saga = FakeSaga()
    service, users, cognito = make_service(saga)

    invoke(service)

    assert cognito.reads == [(TARGET, "target@example.test")]
    assert cognito.resends == [TARGET]
    assert saga.transitions == [("CLAIMED", "DISPATCHING"), ("DISPATCHING", "SENT")]
    assert len(users.completions) == 1
    completion = users.completions[0]
    audit = completion["audit"]
    assert isinstance(audit, dict)
    assert audit["eventType"] == "USER_INVITATION_RESENT"
    assert audit["observedVersion"] == 3
    assert audit["actorId"] == "actor-1"
    assert audit["resourceId"] == TARGET
    assert "target@example.test" not in repr(audit)
    assert completion["client_request_token"] == KEY
    assert users.target_profile is not None
    assert users.target_profile["version"] == 3
    assert users.target_profile["authVersion"] == 1
    assert users.target_profile["status"] == "INVITED"
    assert users.target_profile["role"] == "OPERATOR"
    assert "CONTROL#ACTIVE_ADMIN_COUNT" not in repr(users.completions)


def test_completed_replay_precedes_target_read_even_if_target_changed() -> None:
    saga = FakeSaga(ResendSagaState.COMPLETED)
    users = FakeUsers(saga, target_status="ACTIVE", target_version=4)
    service, users, cognito = make_service(saga, users=users)

    invoke(service)

    assert users.target_reads == 0
    assert cognito.reads == []
    assert cognito.resends == []
    assert users.completions == []


@pytest.mark.parametrize(
    ("version", "status", "missing", "error"),
    [
        (4, "INVITED", False, UserVersionConflictError),
        (3, "ACTIVE", False, UserStateConflictError),
        (3, "INACTIVE", False, UserStateConflictError),
        (3, "INVITED", True, AdminUserNotFoundError),
    ],
)
def test_target_preconditions_fail_before_dispatch(
    version: int,
    status: str,
    missing: bool,
    error: type[Exception],
) -> None:
    saga = FakeSaga()
    users = FakeUsers(saga, target_version=version, target_status=status)
    if missing:
        users.target_profile = None
    service, _, cognito = make_service(saga, users=users)

    with pytest.raises(error):
        invoke(service)

    assert saga.transitions == []
    assert cognito.resends == []


def test_incompatible_identity_fails_closed_before_dispatch() -> None:
    saga = FakeSaga()
    cognito = FakeCognito()
    cognito.identity = ReconciledCognitoIdentity(TARGET, "different-sub")
    service, _, cognito = make_service(saga, cognito=cognito)

    with pytest.raises(UserInvitationReconciliationError):
        invoke(service)

    assert saga.transitions == []
    assert cognito.resends == []


def test_deterministic_failure_is_retryable_and_revalidates_target() -> None:
    saga = FakeSaga()
    cognito = FakeCognito([CognitoInvitationDeliveryError(), None])
    service, users, cognito = make_service(saga, cognito=cognito)

    with pytest.raises(InvitationDeliveryFailedError):
        invoke(service)
    reads_after_failure = users.target_reads
    assert saga.current["state"] == "RETRYABLE"
    assert users.completions == []

    invoke(service)

    assert users.target_reads > reads_after_failure
    assert cognito.resends == [TARGET, TARGET]
    assert len(users.completions) == 1
    assert saga.failures == [("RETRYABLE", INVITATION_DELIVERY_FAILED)]


def test_ambiguous_result_and_dispatch_recovery_never_resend_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saga = FakeSaga()
    cognito = FakeCognito([CognitoResultAmbiguousError()])
    service, _, cognito = make_service(saga, cognito=cognito)
    logs: list[dict[str, object]] = []
    monkeypatch.setattr(
        "users_api.services.resend_invitation_service.logger.warning",
        lambda message, *, extra: logs.append(extra),
    )

    with pytest.raises(InvitationDeliveryUncertainError):
        invoke(service)
    with pytest.raises(InvitationDeliveryUncertainError):
        invoke(service)
    assert cognito.resends == [TARGET]
    assert saga.failures == [("RECONCILIATION_REQUIRED", INVITATION_DELIVERY_UNCERTAIN)]

    recovered = FakeSaga(ResendSagaState.DISPATCHING)
    recovered_service, _, recovered_cognito = make_service(recovered)
    with pytest.raises(InvitationDeliveryUncertainError):
        invoke(recovered_service)
    assert recovered_cognito.resends == []
    assert "target@example.test" not in repr(logs)
    assert "Synthetic Target" not in repr(logs)


def test_sent_recovery_completes_without_resend_and_single_audit() -> None:
    saga = FakeSaga(ResendSagaState.SENT)
    service, users, cognito = make_service(saga)

    invoke(service)
    invoke(service)

    assert cognito.resends == []
    assert len(users.completions) == 1
    assert saga.current["state"] == "COMPLETED"


def test_sent_completion_failure_retries_audit_without_resend() -> None:
    saga = FakeSaga(ResendSagaState.SENT)
    users = FakeUsers(saga)
    users.completion_errors = [RuntimeError("storage unavailable")]
    service, users, cognito = make_service(saga, users=users)

    with pytest.raises(RuntimeError, match="storage unavailable"):
        invoke(service)
    invoke(service)

    assert cognito.resends == []
    assert len(users.completions) == 1
    assert saga.current["state"] == "COMPLETED"


def test_new_keys_are_independent_explicit_intents_after_completed_or_uncertain() -> None:
    total_resends = 0
    for prior_state in (ResendSagaState.COMPLETED, ResendSagaState.RECONCILIATION_REQUIRED):
        prior = FakeSaga(prior_state)
        if prior_state == ResendSagaState.RECONCILIATION_REQUIRED:
            prior.current["errorCode"] = INVITATION_DELIVERY_UNCERTAIN

        new_saga = FakeSaga()
        service, _, cognito = make_service(new_saga)
        invoke(service, key=NEW_KEY)
        total_resends += len(cognito.resends)

        assert prior.current["state"] == prior_state.value
        assert new_saga.claim_keys == [NEW_KEY]

    assert total_resends == 2


@pytest.mark.parametrize(
    ("role", "status"),
    [("OPERATOR", "ACTIVE"), ("ADMIN", "INACTIVE")],
)
def test_only_active_admin_can_resend(role: str, status: str) -> None:
    saga = FakeSaga()
    users = FakeUsers(saga, actor_role=role, actor_status=status)
    service, _, cognito = make_service(saga, users=users)

    with pytest.raises(AdminUserForbiddenError):
        invoke(service)

    assert saga.claims == 0
    assert cognito.resends == []
