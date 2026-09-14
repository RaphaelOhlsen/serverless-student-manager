from collections.abc import Iterable
from typing import Any

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError  # type: ignore[import-untyped]
from users_api.errors import (
    CognitoResultAmbiguousError,
    CognitoServiceError,
    CognitoUserNotFoundError,
    UserEmailAlreadyExistsError,
)
from users_api.repositories.cognito_repository import ReconciledCognitoIdentity
from users_api.services.invitation_saga import CreateSagaState
from users_api.services.user_provisioning import build_user_provisioning_items
from users_api.services.user_provisioning_service import (
    COMPENSATION_INCOMPLETE,
    EMAIL_ALREADY_EXISTS,
    ProvisioningOutcome,
    UserProvisioningService,
)
from users_api.validation import CreateUserInput

USER_ID = "11111111-1111-4111-8111-111111111111"
SUB = "22222222-2222-4222-8222-222222222222"
KEY = "44444444-4444-4444-8444-444444444444"


def record(state: str = "COGNITO_CREATED") -> dict[str, object]:
    return {
        "id": "HTTP#dev#actor-1#create-user#key",
        "operation": "create-user",
        "state": state,
        "userId": USER_ID,
        "cognitoSub": SUB,
        "cognitoEvidence": "CREATE_SUCCESS",
        "actorId": "actor-1",
        "eventId": "33333333-3333-4333-8333-333333333333",
        "correlationId": "request-1",
        "startedAt": "2026-09-14T12:00:00.000Z",
        "idempotencyKey": KEY,
        "requestHash": "safe-hash",
    }


USER = CreateUserInput("Admin Example", "admin example", "admin@example.test", "ADMIN")


def transaction_error() -> ClientError:
    return ClientError(
        {
            "Error": {"Code": "TransactionCanceledException", "Message": "private"},
            "CancellationReasons": [{"Code": "None"}] * 5,
        },
        "TransactWriteItems",
    )


class FakeUsers:
    def __init__(self, outcomes: Iterable[Exception | None] = (None,)) -> None:
        self.outcomes = iter(outcomes)
        self.writes: list[dict[str, object]] = []
        self.profile: dict[str, object] | None = None
        self.unique: dict[str, object] | None = None
        self.authorization: dict[str, object] | None = None
        self.audit: dict[str, object] | None = None

    def provision_invited_user(self, **kwargs: object) -> None:
        self.writes.append(kwargs)
        outcome = next(self.outcomes)
        if outcome is not None:
            raise outcome

    def get_profile(self, user_id: str) -> dict[str, object] | None:
        assert user_id == USER_ID
        return self.profile

    def get_email_reservation(self, normalized_email: str) -> dict[str, object] | None:
        assert normalized_email == USER.email
        return self.unique

    def get_authorization(self, cognito_sub: str) -> dict[str, object] | None:
        assert cognito_sub == SUB
        return self.authorization

    def get_audit_event(self, **kwargs: str) -> dict[str, object] | None:
        return self.audit


class FakeSaga:
    def __init__(self, initial: dict[str, object]) -> None:
        self.current = dict(initial)
        self.begins: list[tuple[int, str]] = []
        self.completed = 0
        self.reconciliation: list[str] = []

    def get(self, record_id: str) -> dict[str, object] | None:
        assert record_id == self.current["id"]
        return dict(self.current)

    def build_transaction_transition(
        self, *, record: dict[str, object], next_state: str
    ) -> dict[str, object]:
        return {
            "Update": {
                "TableName": "idempotency",
                "Key": {"id": {"S": str(record["id"])}},
                "next": next_state,
            }
        }

    def begin_cognito_compensation(
        self,
        *,
        record: dict[str, object],
        http_status: int,
        error_code: str,
    ) -> None:
        self.begins.append((http_status, error_code))
        self.current.update(
            state=CreateSagaState.COMPENSATING.value,
            terminalHttpStatus=http_status,
            terminalErrorCode=error_code,
        )

    def complete_compensation(self, *, record: dict[str, object]) -> None:
        self.completed += 1
        self.current.update(
            state=CreateSagaState.COMPLETED.value,
            httpStatus=record["terminalHttpStatus"],
            errorCode=record["terminalErrorCode"],
        )

    def store_provisioning_reconciliation_required(
        self, *, record: dict[str, object], reason: str
    ) -> None:
        self.reconciliation.append(reason)
        self.current.update(state=CreateSagaState.RECONCILIATION_REQUIRED.value, errorCode=reason)


class FakeCognito:
    def __init__(
        self,
        *,
        reads: Iterable[Exception | ReconciledCognitoIdentity] = (
            ReconciledCognitoIdentity(USER_ID, SUB),
        ),
        deletes: Iterable[Exception | None] = (None,),
        disables: Iterable[Exception | None] = (None,),
    ) -> None:
        self.reads = iter(reads)
        self.deletes = iter(deletes)
        self.disables = iter(disables)
        self.calls: list[str] = []

    def admin_get_user(self, *, user_id: str, expected_email: str) -> ReconciledCognitoIdentity:
        self.calls.append("get")
        outcome = next(self.reads)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def admin_delete_user(self, *, user_id: str) -> None:
        self.calls.append("delete")
        outcome = next(self.deletes)
        if outcome is not None:
            raise outcome

    def admin_disable_user(self, *, user_id: str) -> None:
        self.calls.append("disable")
        outcome = next(self.disables)
        if outcome is not None:
            raise outcome


def service(
    users: FakeUsers,
    saga: FakeSaga,
    cognito: FakeCognito | None = None,
) -> UserProvisioningService:
    return UserProvisioningService(
        users,
        saga,
        cognito or FakeCognito(),
        audit_retention_days=90,
    )


def committed_snapshot(users: FakeUsers, saga: FakeSaga) -> None:
    expected = build_user_provisioning_items(record=record(), user=USER, audit_retention_days=90)
    users.profile = expected.profile
    users.unique = expected.unique_email
    users.authorization = expected.authorization
    users.audit = expected.audit
    saga.current["state"] = CreateSagaState.DDB_COMMITTED.value


def test_success_uses_one_stable_atomic_transaction() -> None:
    users = FakeUsers()
    saga = FakeSaga(record())
    result = service(users, saga).materialize(record=record(), user=USER)

    assert result.outcome == ProvisioningOutcome.DDB_COMMITTED
    assert len(users.writes) == 1
    assert users.writes[0]["client_request_token"] == KEY
    transition = users.writes[0]["saga_transition"]
    assert isinstance(transition, dict)
    update = transition["Update"]
    assert isinstance(update, dict)
    assert update["next"] == "DDB_COMMITTED"


def test_ambiguous_result_reconciles_committed_transaction() -> None:
    users = FakeUsers([EndpointConnectionError(endpoint_url="https://dynamodb.invalid")])
    saga = FakeSaga(record())
    committed_snapshot(users, saga)

    result = service(users, saga).materialize(record=record(), user=USER)

    assert result.outcome == ProvisioningOutcome.DDB_COMMITTED
    assert saga.reconciliation == []


def test_ambiguous_absence_retries_same_transaction_once() -> None:
    users = FakeUsers([EndpointConnectionError(endpoint_url="https://invalid"), None])
    saga = FakeSaga(record())
    result = service(users, saga).materialize(record=record(), user=USER)

    assert result.outcome == ProvisioningOutcome.DDB_COMMITTED
    assert len(users.writes) == 2
    assert users.writes[0] == users.writes[1]


def test_persistent_ambiguous_result_requires_reconciliation_without_compensation() -> None:
    users = FakeUsers(
        [
            EndpointConnectionError(endpoint_url="https://invalid"),
            EndpointConnectionError(endpoint_url="https://invalid"),
        ]
    )
    saga = FakeSaga(record())
    cognito = FakeCognito(reads=[])

    result = service(users, saga, cognito).materialize(record=record(), user=USER)

    assert result.outcome == ProvisioningOutcome.RECONCILIATION_REQUIRED
    assert cognito.calls == []
    assert saga.begins == []


def test_ambiguous_retry_that_committed_is_confirmed_by_second_readback() -> None:
    saga = FakeSaga(record())

    class CommittingRetryUsers(FakeUsers):
        def provision_invited_user(self, **kwargs: object) -> None:
            try:
                super().provision_invited_user(**kwargs)
            except EndpointConnectionError:
                if len(self.writes) == 2:
                    committed_snapshot(self, saga)
                raise

    users = CommittingRetryUsers(
        [
            EndpointConnectionError(endpoint_url="https://invalid"),
            EndpointConnectionError(endpoint_url="https://invalid"),
        ]
    )

    result = service(users, saga).materialize(record=record(), user=USER)

    assert result.outcome == ProvisioningOutcome.DDB_COMMITTED
    assert saga.reconciliation == []


def test_ambiguous_retry_never_compensates_even_if_email_conflict_appears() -> None:
    saga = FakeSaga(record())

    class ConflictingRetryUsers(FakeUsers):
        def provision_invited_user(self, **kwargs: object) -> None:
            try:
                super().provision_invited_user(**kwargs)
            except EndpointConnectionError:
                if len(self.writes) == 2:
                    self.unique = {"userId": "other"}
                raise

    users = ConflictingRetryUsers(
        [
            EndpointConnectionError(endpoint_url="https://invalid"),
            EndpointConnectionError(endpoint_url="https://invalid"),
        ]
    )
    cognito = FakeCognito(reads=[])

    result = service(users, saga, cognito).materialize(record=record(), user=USER)

    assert result.outcome == ProvisioningOutcome.RECONCILIATION_REQUIRED
    assert cognito.calls == []
    assert saga.begins == []


def test_same_operation_already_committed_after_cancellation_is_success() -> None:
    users = FakeUsers([transaction_error()])
    saga = FakeSaga(record())
    committed_snapshot(users, saga)
    result = service(users, saga).materialize(record=record(), user=USER)
    assert result.outcome == ProvisioningOutcome.DDB_COMMITTED


@pytest.mark.parametrize(
    ("component", "reason"),
    [
        ("profile", "USER_PROVISIONING_PROFILE_INCOMPATIBLE"),
        ("authorization", "USER_PROVISIONING_AUTHORIZATION_INCOMPATIBLE"),
        ("audit", "USER_PROVISIONING_AUDIT_INCOMPATIBLE"),
        ("saga", "USER_PROVISIONING_SAGA_INCOMPATIBLE"),
    ],
)
def test_incompatible_transaction_state_is_not_repaired_item_by_item(
    component: str,
    reason: str,
) -> None:
    users = FakeUsers([transaction_error()])
    saga = FakeSaga(record())
    if component == "saga":
        saga.current["state"] = CreateSagaState.CLAIMED.value
    else:
        setattr(users, component, {"unexpected": "foreign"})

    result = service(users, saga, FakeCognito(reads=[])).materialize(
        record=record(),
        user=USER,
    )

    assert result.outcome == ProvisioningOutcome.RECONCILIATION_REQUIRED
    assert saga.reconciliation == [reason]
    assert len(users.writes) == 1


def test_email_conflict_compensates_owned_identity_and_is_terminal() -> None:
    users = FakeUsers([transaction_error()])
    users.unique = {"PK": "UNIQUE#EMAIL#admin@example.test", "SK": "UNIQUE", "userId": "other"}
    saga = FakeSaga(record())
    cognito = FakeCognito()

    with pytest.raises(UserEmailAlreadyExistsError):
        service(users, saga, cognito).materialize(record=record(), user=USER)

    assert cognito.calls == ["get", "delete"]
    assert saga.begins == [(409, EMAIL_ALREADY_EXISTS)]
    assert saga.completed == 1
    assert saga.current["state"] == "COMPLETED"

    replay_cognito = FakeCognito(reads=[])
    with pytest.raises(UserEmailAlreadyExistsError):
        service(FakeUsers([]), saga, replay_cognito).materialize(
            record=saga.current,
            user=USER,
        )
    assert replay_cognito.calls == []


def test_incompatible_identity_is_never_deleted_or_disabled() -> None:
    users = FakeUsers([transaction_error()])
    users.unique = {"userId": "other"}
    saga = FakeSaga(record())
    cognito = FakeCognito(reads=[ReconciledCognitoIdentity(USER_ID, "other-sub")])

    result = service(users, saga, cognito).materialize(record=record(), user=USER)

    assert result.outcome == ProvisioningOutcome.RECONCILIATION_REQUIRED
    assert cognito.calls == ["get"]
    assert saga.begins == []


def test_compensation_already_absent_is_terminal_without_delete() -> None:
    users = FakeUsers([transaction_error()])
    users.unique = {"userId": "other"}
    saga = FakeSaga(record())
    cognito = FakeCognito(reads=[CognitoUserNotFoundError()])

    with pytest.raises(UserEmailAlreadyExistsError):
        service(users, saga, cognito).materialize(record=record(), user=USER)
    assert cognito.calls == ["get"]
    assert saga.completed == 1


def test_ambiguous_delete_readback_absent_completes_compensation() -> None:
    users = FakeUsers([transaction_error()])
    users.unique = {"userId": "other"}
    saga = FakeSaga(record())
    cognito = FakeCognito(
        reads=[ReconciledCognitoIdentity(USER_ID, SUB), CognitoUserNotFoundError()],
        deletes=[CognitoResultAmbiguousError()],
    )

    with pytest.raises(UserEmailAlreadyExistsError):
        service(users, saga, cognito).materialize(record=record(), user=USER)
    assert cognito.calls == ["get", "delete", "get"]
    assert saga.completed == 1


def test_ambiguous_delete_with_owned_identity_uses_safe_disable_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users = FakeUsers([transaction_error()])
    users.unique = {"userId": "other"}
    saga = FakeSaga(record())
    cognito = FakeCognito(
        reads=[
            ReconciledCognitoIdentity(USER_ID, SUB),
            ReconciledCognitoIdentity(USER_ID, SUB),
            ReconciledCognitoIdentity(USER_ID, SUB),
        ],
        deletes=[CognitoResultAmbiguousError()],
    )
    monkeypatch.setattr(
        "users_api.services.user_provisioning_service.logger.error",
        lambda *args, **kwargs: None,
    )

    result = service(users, saga, cognito).materialize(record=record(), user=USER)

    assert result.outcome == ProvisioningOutcome.RECONCILIATION_REQUIRED
    assert cognito.calls == ["get", "delete", "get", "get", "disable"]
    assert saga.completed == 0
    assert saga.reconciliation == [COMPENSATION_INCOMPLETE]


def test_delete_failure_disables_only_after_second_ownership_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users = FakeUsers([transaction_error()])
    users.unique = {"userId": "other"}
    saga = FakeSaga(record())
    cognito = FakeCognito(
        reads=[
            ReconciledCognitoIdentity(USER_ID, SUB),
            ReconciledCognitoIdentity(USER_ID, SUB),
            ReconciledCognitoIdentity(USER_ID, SUB),
        ],
        deletes=[CognitoServiceError()],
    )
    monkeypatch.setattr(
        "users_api.services.user_provisioning_service.logger.error",
        lambda *args, **kwargs: None,
    )

    result = service(users, saga, cognito).materialize(record=record(), user=USER)

    assert result.outcome == ProvisioningOutcome.RECONCILIATION_REQUIRED
    assert cognito.calls == ["get", "delete", "get", "get", "disable"]
    assert saga.reconciliation == [COMPENSATION_INCOMPLETE]


def test_disable_failure_remains_reconciliation_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users = FakeUsers([transaction_error()])
    users.unique = {"userId": "other"}
    saga = FakeSaga(record())
    cognito = FakeCognito(
        reads=[
            ReconciledCognitoIdentity(USER_ID, SUB),
            ReconciledCognitoIdentity(USER_ID, SUB),
            ReconciledCognitoIdentity(USER_ID, SUB),
        ],
        deletes=[CognitoServiceError()],
        disables=[CognitoServiceError()],
    )
    logged: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "users_api.services.user_provisioning_service.logger.error",
        lambda message, *, extra: logged.append(extra),
    )

    result = service(users, saga, cognito).materialize(record=record(), user=USER)

    assert result.outcome == ProvisioningOutcome.RECONCILIATION_REQUIRED
    assert saga.reconciliation == [COMPENSATION_INCOMPLETE]
    assert "admin@example.test" not in repr(logged)


def test_ddb_committed_replay_never_writes_or_compensates() -> None:
    users = FakeUsers([])
    saga = FakeSaga(record(CreateSagaState.DDB_COMMITTED.value))
    cognito = FakeCognito(reads=[])
    result = service(users, saga, cognito).materialize(record=saga.current, user=USER)
    assert result.outcome == ProvisioningOutcome.DDB_COMMITTED
    assert users.writes == []
    assert cognito.calls == []
