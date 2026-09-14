from collections.abc import Iterable

import pytest
from users_api.errors import (
    AdminUserForbiddenError,
    CognitoInvitationDeliveryError,
    CognitoResultAmbiguousError,
    IdempotencyKeyReusedError,
    InvalidAdminUserWriteRequestError,
    InvitationDeliveryFailedError,
    InvitationDeliveryUncertainError,
    OperationInProgressError,
    UserCreateReconciliationError,
    UserEmailAlreadyExistsError,
)
from users_api.services.cognito_create_service import CognitoCreateOutcome, CognitoCreateResult
from users_api.services.create_user_service import CreateUserService
from users_api.services.invitation_saga import (
    INVITATION_DELIVERY_FAILED,
    INVITATION_DELIVERY_UNCERTAIN,
    CognitoIdentityEvidence,
    CreateSagaState,
    SagaClaim,
)
from users_api.services.user_provisioning_service import ProvisioningOutcome, ProvisioningResult

KEY = "44444444-4444-4444-8444-444444444444"
USER_ID = "11111111-1111-4111-8111-111111111111"
SUB = "22222222-2222-4222-8222-222222222222"
BODY = '{"fullName":" Admin   Example ","email":"ADMIN@EXAMPLE.TEST","role":"ADMIN"}'


def saga_record(state: CreateSagaState = CreateSagaState.CLAIMED) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "HTTP#dev#actor-1#create-user#key",
        "environment": "dev",
        "actorId": "actor-1",
        "operation": "create-user",
        "target": USER_ID,
        "idempotencyKey": KEY,
        "requestHash": "hash",
        "state": state.value,
        "userId": USER_ID,
        "eventId": "33333333-3333-4333-8333-333333333333",
        "correlationId": "request-1",
        "startedAt": "2026-09-14T12:00:00.000Z",
        "expiration": 1,
        "inProgressExpiration": 1,
    }
    if state not in {CreateSagaState.CLAIMED, CreateSagaState.RECONCILIATION_REQUIRED}:
        value.update(
            cognitoSub=SUB,
            cognitoEvidence=CognitoIdentityEvidence.CREATE_SUCCESS.value,
        )
    return value


class FakeUsers:
    def __init__(self, role: str = "ADMIN", status: str = "ACTIVE") -> None:
        self.authorization = {
            "userId": "actor-1",
            "role": role,
            "status": status,
            "authVersion": 1,
        }
        self.profile = {
            **self.authorization,
            "cognitoSub": "actor-sub",
        }

    def get_authorization(self, cognito_sub: str) -> dict[str, object] | None:
        return self.authorization if cognito_sub == "actor-sub" else None

    def get_profile(self, user_id: str) -> dict[str, object] | None:
        return self.profile if user_id == "actor-1" else None


class FakeSaga:
    def __init__(self, state: CreateSagaState = CreateSagaState.CLAIMED) -> None:
        self.current = saga_record(state)
        self.transitions: list[tuple[str, str]] = []
        self.failures: list[tuple[str, str]] = []
        self.completed = 0
        self.completion_errors: list[Exception] = []
        self.claim_error: Exception | None = None
        self.claim_calls = 0

    def claim_create(self, **kwargs: object) -> SagaClaim:
        self.claim_calls += 1
        if self.claim_error is not None:
            raise self.claim_error
        assert kwargs["actor_id"] == "actor-1"
        assert kwargs["full_name"] == "Admin Example"
        assert kwargs["email"] == "admin@example.test"
        return SagaClaim(dict(self.current), created=self.current["state"] == "CLAIMED")

    def get(self, record_id: str) -> dict[str, object] | None:
        assert record_id == self.current["id"]
        return dict(self.current)

    def transition(self, *, record: dict[str, object], next_state: str) -> None:
        self.transitions.append((str(record["state"]), next_state))
        self.current["state"] = next_state
        if record["state"] == CreateSagaState.INVITATION_RETRYABLE.value:
            self.current.pop("httpStatus", None)
            self.current.pop("errorCode", None)

    def store_completed(self, **kwargs: object) -> None:
        if self.completion_errors:
            raise self.completion_errors.pop(0)
        self.completed += 1
        self.current.update(
            state="COMPLETED",
            httpStatus=kwargs["http_status"],
            responseUserId=kwargs["response_user_id"],
        )
        self.current.pop("errorCode", None)

    def store_delivery_failure(
        self, *, record: dict[str, object], retryable_state: str, error_code: str
    ) -> None:
        self.failures.append((retryable_state, error_code))
        self.current.update(state=retryable_state, httpStatus=503, errorCode=error_code)

    def store_cognito_reconciliation_required(self, **kwargs: object) -> None:
        self.current.update(
            state=CreateSagaState.RECONCILIATION_REQUIRED.value,
            errorCode="COGNITO_CREATE_RESULT_UNCERTAIN",
        )


class FakeCognitoCreate:
    def __init__(
        self, saga: FakeSaga, outcomes: Iterable[CognitoCreateOutcome] | None = None
    ) -> None:
        self.saga = saga
        self.outcomes = iter(outcomes or [CognitoCreateOutcome.CREATED_AND_RECONCILED])
        self.calls = 0

    def create_or_reconcile(self, **kwargs: object) -> CognitoCreateResult:
        self.calls += 1
        outcome = next(self.outcomes)
        if outcome in {
            CognitoCreateOutcome.CREATED_AND_RECONCILED,
            CognitoCreateOutcome.EXISTING_AND_RECONCILED,
        }:
            self.saga.current.update(
                state=CreateSagaState.COGNITO_CREATED.value,
                cognitoSub=SUB,
                cognitoEvidence=CognitoIdentityEvidence.CREATE_SUCCESS.value,
            )
            return CognitoCreateResult(outcome, USER_ID, SUB)
        return CognitoCreateResult(outcome, USER_ID, None)


class FakeProvisioning:
    def __init__(
        self,
        saga: FakeSaga,
        outcome: ProvisioningOutcome = ProvisioningOutcome.DDB_COMMITTED,
    ) -> None:
        self.saga = saga
        self.outcome = outcome
        self.calls = 0

    def materialize(self, **kwargs: object) -> ProvisioningResult:
        self.calls += 1
        self.saga.current["state"] = self.outcome.value
        return ProvisioningResult(self.outcome, USER_ID)


class FakeInvitations:
    def __init__(self, outcomes: Iterable[Exception | None] = (None,)) -> None:
        self.outcomes = iter(outcomes)
        self.calls: list[str] = []

    def admin_resend_invitation(self, *, user_id: str) -> None:
        self.calls.append(user_id)
        outcome = next(self.outcomes)
        if outcome is not None:
            raise outcome


def make_service(
    saga: FakeSaga,
    *,
    users: FakeUsers | None = None,
    create: FakeCognitoCreate | None = None,
    provisioning: FakeProvisioning | None = None,
    invitations: FakeInvitations | None = None,
) -> tuple[CreateUserService, FakeCognitoCreate, FakeProvisioning, FakeInvitations]:
    create = create or FakeCognitoCreate(saga)
    provisioning = provisioning or FakeProvisioning(saga)
    invitations = invitations or FakeInvitations()
    return (
        CreateUserService(
            users or FakeUsers(),
            saga,
            create,
            provisioning,
            invitations,
            environment="dev",
        ),
        create,
        provisioning,
        invitations,
    )


def invoke(service: CreateUserService) -> dict[str, object]:
    return service.create_user(
        cognito_sub="actor-sub",
        idempotency_key=KEY,
        request_id="request-1",
        body=BODY,
    )


def test_happy_path_composes_all_phases_and_returns_public_user() -> None:
    saga = FakeSaga()
    service, create, provisioning, invitations = make_service(saga)

    result = invoke(service)

    assert create.calls == 1
    assert provisioning.calls == 1
    assert invitations.calls == [USER_ID]
    assert saga.transitions == [
        ("DDB_COMMITTED", "INVITATION_DISPATCHING"),
        ("INVITATION_DISPATCHING", "INVITATION_SENT"),
    ]
    assert saga.completed == 1
    assert result == {
        "userId": USER_ID,
        "fullName": "Admin Example",
        "email": "admin@example.test",
        "role": "ADMIN",
        "status": "INVITED",
        "version": 1,
        "createdAt": "2026-09-14T12:00:00.000Z",
        "updatedAt": "2026-09-14T12:00:00.000Z",
    }


@pytest.mark.parametrize(
    ("state", "create_calls", "provisioning_calls", "resend_calls", "completed"),
    [
        (CreateSagaState.COGNITO_CREATED, 0, 1, 1, 1),
        (CreateSagaState.DDB_COMMITTED, 0, 0, 1, 1),
        (CreateSagaState.INVITATION_SENT, 0, 0, 0, 1),
        (CreateSagaState.COMPLETED, 0, 0, 0, 0),
    ],
)
def test_resume_starts_at_durable_phase_without_repeating_side_effects(
    state: CreateSagaState,
    create_calls: int,
    provisioning_calls: int,
    resend_calls: int,
    completed: int,
) -> None:
    saga = FakeSaga(state)
    if state == CreateSagaState.COMPLETED:
        saga.current.update(httpStatus=201, responseUserId=USER_ID)
    service, create, provisioning, invitations = make_service(saga)

    result = invoke(service)

    assert result["userId"] == USER_ID
    assert create.calls == create_calls
    assert provisioning.calls == provisioning_calls
    assert len(invitations.calls) == resend_calls
    assert saga.completed == completed


def test_reconciliation_and_dispatch_crash_never_repeat_side_effects() -> None:
    reconciliation = FakeSaga(CreateSagaState.RECONCILIATION_REQUIRED)
    service, create, provisioning, invitations = make_service(reconciliation)
    with pytest.raises(UserCreateReconciliationError):
        invoke(service)
    assert (create.calls, provisioning.calls, invitations.calls) == (0, 0, [])

    dispatching = FakeSaga(CreateSagaState.INVITATION_DISPATCHING)
    service, create, provisioning, invitations = make_service(dispatching)
    with pytest.raises(InvitationDeliveryUncertainError):
        invoke(service)
    assert (create.calls, provisioning.calls, invitations.calls) == (0, 0, [])
    assert dispatching.failures == [("RECONCILIATION_REQUIRED", INVITATION_DELIVERY_UNCERTAIN)]


def test_deterministic_delivery_failure_is_retryable_without_domain_rollback() -> None:
    saga = FakeSaga(CreateSagaState.DDB_COMMITTED)
    invitations = FakeInvitations([CognitoInvitationDeliveryError(), None])
    service, create, provisioning, invitations = make_service(saga, invitations=invitations)

    with pytest.raises(InvitationDeliveryFailedError):
        invoke(service)
    assert saga.current["state"] == CreateSagaState.INVITATION_RETRYABLE.value
    assert saga.failures == [("INVITATION_RETRYABLE", INVITATION_DELIVERY_FAILED)]

    result = invoke(service)
    assert result["status"] == "INVITED"
    assert create.calls == 0
    assert provisioning.calls == 0
    assert invitations.calls == [USER_ID, USER_ID]

    replay = invoke(service)
    assert replay == result
    assert invitations.calls == [USER_ID, USER_ID]


def test_ambiguous_delivery_is_terminal_for_same_operation_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saga = FakeSaga(CreateSagaState.DDB_COMMITTED)
    invitations = FakeInvitations([CognitoResultAmbiguousError()])
    service, create, provisioning, invitations = make_service(saga, invitations=invitations)
    logs: list[dict[str, object]] = []
    monkeypatch.setattr(
        "users_api.services.create_user_service.logger.warning",
        lambda message, *, extra: logs.append(extra),
    )

    with pytest.raises(InvitationDeliveryUncertainError):
        invoke(service)
    assert invitations.calls == [USER_ID]

    with pytest.raises(InvitationDeliveryUncertainError):
        invoke(service)
    assert invitations.calls == [USER_ID]
    assert create.calls == provisioning.calls == 0
    assert "admin@example.test" not in repr(logs)
    assert "Admin Example" not in repr(logs)


def test_terminal_email_conflict_replay_has_no_side_effects() -> None:
    saga = FakeSaga(CreateSagaState.COMPLETED)
    saga.current.update(httpStatus=409, errorCode="EMAIL_ALREADY_EXISTS")
    service, create, provisioning, invitations = make_service(saga)
    with pytest.raises(UserEmailAlreadyExistsError):
        invoke(service)
    assert (create.calls, provisioning.calls, invitations.calls) == (0, 0, [])


def test_conclusive_absence_retries_same_cognito_identity_once() -> None:
    saga = FakeSaga()
    create = FakeCognitoCreate(
        saga,
        [
            CognitoCreateOutcome.ABSENT_AFTER_AMBIGUOUS,
            CognitoCreateOutcome.EXISTING_AND_RECONCILED,
        ],
    )
    service, create, provisioning, invitations = make_service(saga, create=create)

    result = invoke(service)

    assert result["userId"] == USER_ID
    assert create.calls == 2
    assert invitations.calls == [USER_ID]
    assert provisioning.calls == 1


def test_repeated_conclusive_absence_requires_reconciliation() -> None:
    saga = FakeSaga()
    create = FakeCognitoCreate(
        saga,
        [
            CognitoCreateOutcome.ABSENT_AFTER_AMBIGUOUS,
            CognitoCreateOutcome.ABSENT_AFTER_AMBIGUOUS,
        ],
    )
    service, create, provisioning, invitations = make_service(saga, create=create)

    with pytest.raises(UserCreateReconciliationError):
        invoke(service)

    assert create.calls == 2
    assert provisioning.calls == 0
    assert invitations.calls == []


def test_provisioning_reconciliation_stops_before_invitation() -> None:
    saga = FakeSaga(CreateSagaState.COGNITO_CREATED)
    provisioning = FakeProvisioning(saga, ProvisioningOutcome.RECONCILIATION_REQUIRED)
    service, create, provisioning, invitations = make_service(
        saga,
        provisioning=provisioning,
    )

    with pytest.raises(UserCreateReconciliationError):
        invoke(service)

    assert create.calls == 0
    assert provisioning.calls == 1
    assert invitations.calls == []


def test_completion_failure_after_sent_retries_without_resend() -> None:
    saga = FakeSaga(CreateSagaState.INVITATION_SENT)
    saga.completion_errors = [RuntimeError("storage unavailable")]
    service, create, provisioning, invitations = make_service(saga)

    with pytest.raises(RuntimeError, match="storage unavailable"):
        invoke(service)
    result = invoke(service)

    assert result["userId"] == USER_ID
    assert create.calls == provisioning.calls == 0
    assert invitations.calls == []


def test_unclassified_exception_after_dispatch_is_treated_as_uncertain() -> None:
    saga = FakeSaga(CreateSagaState.DDB_COMMITTED)
    invitations = FakeInvitations([RuntimeError("provider detail")])
    service, _, _, invitations = make_service(saga, invitations=invitations)

    with pytest.raises(InvitationDeliveryUncertainError):
        invoke(service)

    assert invitations.calls == [USER_ID]
    assert saga.current["errorCode"] == INVITATION_DELIVERY_UNCERTAIN


@pytest.mark.parametrize(
    ("role", "status"),
    [("OPERATOR", "ACTIVE"), ("ADMIN", "INACTIVE")],
)
def test_authorization_precedes_request_validation(role: str, status: str) -> None:
    saga = FakeSaga()
    service, create, provisioning, invitations = make_service(
        saga,
        users=FakeUsers(role, status),
    )
    with pytest.raises(AdminUserForbiddenError):
        service.create_user(
            cognito_sub="actor-sub",
            idempotency_key="invalid",
            request_id=None,
            body="invalid",
        )
    assert (create.calls, provisioning.calls, invitations.calls) == (0, 0, [])


@pytest.mark.parametrize(
    ("key", "body"),
    [
        ("invalid", BODY),
        (KEY, '{"fullName":"A","email":"admin@example.test","role":"ADMIN"}'),
        (KEY, '{"fullName":"Admin","email":"invalid","role":"ADMIN"}'),
        (KEY, '{"fullName":"Admin","email":"admin@example.test","role":"OWNER"}'),
        (
            KEY,
            '{"fullName":"Admin","email":"admin@example.test","role":"ADMIN","x":1}',
        ),
    ],
)
def test_validation_stops_before_claim_and_side_effects(key: str, body: str) -> None:
    saga = FakeSaga()
    service, create, provisioning, invitations = make_service(saga)

    with pytest.raises(InvalidAdminUserWriteRequestError):
        service.create_user(
            cognito_sub="actor-sub",
            idempotency_key=key,
            request_id=None,
            body=body,
        )

    assert saga.claim_calls == 0
    assert (create.calls, provisioning.calls, invitations.calls) == (0, 0, [])


@pytest.mark.parametrize("error", [IdempotencyKeyReusedError(), OperationInProgressError()])
def test_claim_errors_do_not_start_side_effects(error: Exception) -> None:
    saga = FakeSaga()
    saga.claim_error = error
    service, create, provisioning, invitations = make_service(saga)

    with pytest.raises(type(error)):
        invoke(service)

    assert (create.calls, provisioning.calls, invitations.calls) == (0, 0, [])
