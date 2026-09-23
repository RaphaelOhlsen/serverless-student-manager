from collections.abc import Callable
from copy import deepcopy
from typing import Any
from uuid import UUID

import pytest
from boto3.dynamodb.types import TypeDeserializer  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from users_api.errors import (
    IdempotencyKeyReusedError,
    InvitationSagaConcurrentTransitionError,
    InvitationSagaInvariantError,
    OperationInProgressError,
)
from users_api.repositories.invitation_saga_repository import InvitationSagaRepository
from users_api.services.invitation_saga import (
    CHANGE_USER_ROLE_OPERATION,
    CREATE_TRANSITIONS,
    DEACTIVATE_USER_OPERATION,
    DEACTIVATION_TRANSITIONS,
    IDEMPOTENCY_TTL_SECONDS,
    IN_PROGRESS_TTL_SECONDS,
    INVITATION_DELIVERY_FAILED,
    INVITATION_DELIVERY_UNCERTAIN,
    REACTIVATE_USER_OPERATION,
    REACTIVATION_TRANSITIONS,
    RESEND_INVITATION_OPERATION,
    RESEND_TRANSITIONS,
    CognitoIdentityEvidence,
    CognitoReconciliationReason,
    CreateSagaState,
    DeactivationState,
    ReactivationState,
    ResendSagaState,
    RoleChangeState,
    create_request_hash,
    deactivation_request_hash,
    reactivation_request_hash,
    replay_from_record,
    resend_request_hash,
    role_change_request_hash,
    validate_transition,
)

NOW = 1_800_000_000
KEY = "11111111-1111-4111-8111-111111111111"
IDS = [
    UUID("22222222-2222-4222-8222-222222222222"),
    UUID("33333333-3333-4333-8333-333333333333"),
    UUID("44444444-4444-4444-8444-444444444444"),
]


def conditional_error() -> ClientError:
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "safe"}},
        "UpdateItem",
    )


class FakeTable:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, object]] = {}
        self.updates: list[dict[str, object]] = []
        self.reject_update = False

    def put_item(self, **kwargs: object) -> dict[str, Any]:
        item = kwargs["Item"]
        assert isinstance(item, dict)
        record_id = str(item["id"])
        if record_id in self.items:
            raise conditional_error()
        self.items[record_id] = deepcopy(item)
        return {}

    def get_item(self, **kwargs: object) -> dict[str, Any]:
        key = kwargs["Key"]
        assert isinstance(key, dict)
        item = self.items.get(str(key["id"]))
        return {"Item": deepcopy(item)} if item is not None else {}

    def update_item(self, **kwargs: object) -> dict[str, Any]:
        self.updates.append(dict(kwargs))
        if self.reject_update:
            raise conditional_error()
        key = kwargs["Key"]
        values = kwargs["ExpressionAttributeValues"]
        assert isinstance(key, dict) and isinstance(values, dict)
        item = self.items[str(key["id"])]
        expected = values.get(":current", values.get(":state"))
        if item["state"] != expected:
            raise conditional_error()
        expiration = item["inProgressExpiration"]
        now = values.get(":now")
        if (
            ":now" in values
            and isinstance(expiration, int)
            and isinstance(now, int)
            and expiration > now
        ):
            raise conditional_error()
        current_lease = values.get(":current_lease")
        if current_lease is not None and expiration != current_lease:
            raise conditional_error()
        if ":next" in values:
            item["state"] = values[":next"]
        if ":lease" in values:
            item["inProgressExpiration"] = values[":lease"]
        names = kwargs.get("ExpressionAttributeNames", {})
        assert isinstance(names, dict)
        for alias, name in names.items():
            if alias.startswith("#field"):
                index = alias.removeprefix("#field")
                item[str(name)] = values[f":value{index}"]
        expression = kwargs.get("UpdateExpression")
        if isinstance(expression, str) and " REMOVE " in expression:
            for name in expression.split(" REMOVE ", 1)[1].split(","):
                item.pop(name.strip(), None)
        return {}


def ids() -> Callable[[], UUID]:
    values = iter(IDS * 4)
    return lambda: next(values)


def repository(
    table: FakeTable,
    clock: Callable[[], float] = lambda: NOW,
    identifier_factory: Callable[[], UUID] | None = None,
) -> InvitationSagaRepository:
    return InvitationSagaRepository(
        table,
        "idempotency",
        clock=clock,
        identifier_factory=identifier_factory or ids(),
    )


def test_deactivation_claim_hash_ttl_replay_and_privacy() -> None:
    table = FakeTable()
    repo = repository(table)
    kwargs: Any = dict(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="target-1",
        expected_version=1,
        request_id=None,
    )
    claim = repo.claim_deactivation(**kwargs)
    record = claim.record
    assert claim.created and record["operation"] == DEACTIVATE_USER_OPERATION
    assert record["state"] == DeactivationState.CLAIMED.value
    assert record["requestHash"] == deactivation_request_hash(
        user_id="target-1", expected_version=1
    )
    assert record["expiration"] == NOW + IDEMPOTENCY_TTL_SECONDS
    assert record["eventId"] == str(IDS[0]) and record["correlationId"] == str(IDS[1])
    assert "email" not in repr(record).lower() and "fullName" not in repr(record)
    with pytest.raises(OperationInProgressError):
        repo.claim_deactivation(**kwargs)
    with pytest.raises(IdempotencyKeyReusedError):
        repo.claim_deactivation(**{**kwargs, "expected_version": 2})


def test_deactivation_transition_cas_and_resume_after_domain_commit() -> None:
    table = FakeTable()
    repo = repository(table)
    kwargs: Any = dict(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="target-1",
        expected_version=1,
        request_id=None,
    )
    claim = repo.claim_deactivation(**kwargs)
    transition: Any = repo.build_deactivation_domain_transition(
        record=claim.record,
        cognito_sub=str(IDS[2]),
        role="OPERATOR",
        resulting_version=2,
        response={
            "userId": "target-1",
            "fullName": "Synthetic User",
            "email": "synthetic@example.test",
            "role": "OPERATOR",
            "status": "INACTIVE",
            "version": 2,
            "createdAt": "2026-01-01T00:00:00.000Z",
            "updatedAt": "2027-01-15T08:00:00.000Z",
        },
    )["Update"]
    assert transition["TableName"] == "idempotency"
    assert transition["ConditionExpression"] == "#state = :current AND requestHash = :request_hash"
    values = {
        key: TypeDeserializer().deserialize(value)
        for key, value in transition["ExpressionAttributeValues"].items()
    }
    assert values[":current"] == DeactivationState.CLAIMED.value
    assert values[":next"] == DeactivationState.DOMAIN_COMMITTED.value
    assert values[":version"] == 2
    assert "Synthetic User" in values.values()
    assert "synthetic@example.test" in values.values()
    assert DEACTIVATION_TRANSITIONS[DeactivationState.CLAIMED] == {
        DeactivationState.DOMAIN_COMMITTED
    }
    assert DEACTIVATION_TRANSITIONS[DeactivationState.COMPLETED] == set()
    stored = table.items[str(claim.record["id"])]
    stored.update(
        state=DeactivationState.DOMAIN_COMMITTED.value,
        cognitoSub=str(IDS[2]),
        domainRole="OPERATOR",
        resultingVersion=2,
        responseUserId="target-1",
        responseFullName="Synthetic User",
        responseEmail="synthetic@example.test",
        responseRole="OPERATOR",
        responseStatus="INACTIVE",
        responseVersion=2,
        responseCreatedAt="2026-01-01T00:00:00.000Z",
        responseUpdatedAt="2027-01-15T08:00:00.000Z",
        inProgressExpiration=NOW * 1000,
    )
    resumed = repo.claim_deactivation(**kwargs)
    assert (
        resumed.created is False
        and resumed.record["state"] == DeactivationState.DOMAIN_COMMITTED.value
    )
    assert resumed.record["eventId"] == claim.record["eventId"]


def test_deactivation_disable_marker_is_conditional_metadata_without_state_change() -> None:
    table = FakeTable()
    repo = repository(table)
    claim = repo.claim_deactivation(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="target-1",
        expected_version=1,
        request_id=None,
    )
    record = table.items[str(claim.record["id"])]
    record.update(
        state=DeactivationState.SIGNOUT_COMPLETED.value,
        cognitoSub=str(IDS[2]),
        domainRole="OPERATOR",
        resultingVersion=2,
        responseUserId="target-1",
        responseFullName="Synthetic User",
        responseEmail="synthetic@example.test",
        responseRole="OPERATOR",
        responseStatus="INACTIVE",
        responseVersion=2,
        responseCreatedAt="2026-01-01T00:00:00.000Z",
        responseUpdatedAt="2027-01-15T08:00:00.000Z",
    )

    repo.mark_deactivation_disable_attempted(record=deepcopy(record))

    update = table.updates[-1]
    assert "attribute_not_exists(disableAttemptedAt)" in str(update["ConditionExpression"])
    update_values = update["ExpressionAttributeValues"]
    assert isinstance(update_values, dict)
    assert update_values[":state"] == "SIGNOUT_COMPLETED"
    assert ":next" not in update_values
    assert record["state"] == DeactivationState.SIGNOUT_COMPLETED.value


def test_deactivation_disable_marker_cas_reports_concurrent_owner() -> None:
    table = FakeTable()
    repo = repository(table)
    claim = repo.claim_deactivation(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="target-1",
        expected_version=1,
        request_id=None,
    )
    record = table.items[str(claim.record["id"])]
    record.update(
        state=DeactivationState.SIGNOUT_COMPLETED.value,
        disableAttemptedAt="2027-01-15T08:00:00.000Z",
    )
    table.reject_update = True

    with pytest.raises(InvitationSagaConcurrentTransitionError):
        repo.mark_deactivation_disable_attempted(record=deepcopy(record))


def test_deactivation_completion_stores_terminal_http_status() -> None:
    table = FakeTable()
    repo = repository(table)
    claim = repo.claim_deactivation(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="target-1",
        expected_version=1,
        request_id=None,
    )
    record = table.items[str(claim.record["id"])]
    record.update(
        state=DeactivationState.DISABLE_COMPLETED.value,
        cognitoSub=str(IDS[2]),
        domainRole="OPERATOR",
        resultingVersion=2,
        responseUserId="target-1",
        responseFullName="Synthetic User",
        responseEmail="synthetic@example.test",
        responseRole="OPERATOR",
        responseStatus="INACTIVE",
        responseVersion=2,
        responseCreatedAt="2026-01-01T00:00:00.000Z",
        responseUpdatedAt="2027-01-15T08:00:00.000Z",
    )

    repo.store_deactivation_completed(record=deepcopy(record))

    assert record["state"] == DeactivationState.COMPLETED.value
    assert record["httpStatus"] == 200
    replay = repo.claim_deactivation(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="target-1",
        expected_version=1,
        request_id=None,
    )
    assert replay.created is False
    assert replay.record["responseEmail"] == "synthetic@example.test"


def test_reactivation_claim_namespace_hash_lease_stable_ids_and_privacy() -> None:
    table = FakeTable()
    repo = repository(table)
    kwargs: Any = dict(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="target-1",
        expected_version=3,
        request_id=None,
    )

    claim = repo.claim_reactivation(**kwargs)
    record = claim.record

    assert claim.created and record["operation"] == REACTIVATE_USER_OPERATION
    assert record["state"] == ReactivationState.CLAIMED.value
    assert record["requestHash"] == reactivation_request_hash(
        user_id="target-1", expected_version=3
    )
    assert record["eventId"] == str(IDS[0])
    assert record["correlationId"] == str(IDS[1])
    assert record["startedAt"] == "2027-01-15T08:00:00.000Z"
    assert record["expiration"] == NOW + IDEMPOTENCY_TTL_SECONDS
    assert record["inProgressExpiration"] == (NOW + IN_PROGRESS_TTL_SECONDS) * 1000
    assert "email" not in repr(record).lower() and "fullName" not in repr(record)

    with pytest.raises(OperationInProgressError):
        repo.claim_reactivation(**kwargs)
    with pytest.raises(IdempotencyKeyReusedError):
        repo.claim_reactivation(**{**kwargs, "expected_version": 4})


def test_reactivation_marker_is_cas_protected_and_required_before_enable() -> None:
    table = FakeTable()
    repo = repository(table)
    claim = repo.claim_reactivation(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="target-1",
        expected_version=3,
        request_id="request-1",
    )

    with pytest.raises(InvitationSagaInvariantError, match="durable enable marker"):
        repo.transition(
            record=claim.record,
            next_state=ReactivationState.ENABLE_DISPATCHING.value,
        )

    repo.mark_reactivation_enable_dispatching(
        record=claim.record,
        role="ADMIN",
        cognito_sub=str(IDS[2]),
        observed_version=3,
        observed_auth_version=7,
    )

    stored = repo.get(str(claim.record["id"]))
    assert stored is not None
    assert stored["state"] == ReactivationState.ENABLE_DISPATCHING.value
    assert stored["domainRole"] == "ADMIN"
    assert stored["cognitoSub"] == str(IDS[2])
    assert stored["observedVersion"] == 3
    assert stored["observedAuthVersion"] == 7
    assert stored["enableAttemptedAt"] == "2027-01-15T08:00:00.000Z"
    assert table.updates[-1]["ConditionExpression"] == (
        "#state = :current AND requestHash = :request_hash "
        "AND inProgressExpiration = :current_lease"
    )

    repo.transition(record=stored, next_state=ReactivationState.COGNITO_ENABLED.value)
    enabled = repo.get(str(claim.record["id"]))
    assert enabled is not None
    with pytest.raises(InvitationSagaInvariantError, match="atomic domain transaction"):
        repo.transition(record=enabled, next_state=ReactivationState.COMPLETED.value)


def test_reactivation_reconciliation_resumes_under_lease_with_stable_context() -> None:
    table = FakeTable()
    repo = repository(table)
    kwargs: Any = dict(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="target-1",
        expected_version=3,
        request_id="request-1",
    )
    claim = repo.claim_reactivation(**kwargs)
    repo.mark_reactivation_enable_dispatching(
        record=claim.record,
        role="OPERATOR",
        cognito_sub=str(IDS[2]),
        observed_version=3,
        observed_auth_version=7,
    )
    dispatching = repo.get(str(claim.record["id"]))
    assert dispatching is not None
    marker = dispatching["enableAttemptedAt"]
    repo.transition(
        record=dispatching,
        next_state=ReactivationState.RECONCILIATION_REQUIRED.value,
    )

    with pytest.raises(OperationInProgressError):
        repo.claim_reactivation(**kwargs)

    resumed = repository(table, clock=lambda: NOW + IN_PROGRESS_TTL_SECONDS + 1).claim_reactivation(
        **kwargs
    )
    assert resumed.created is False
    assert resumed.record["state"] == ReactivationState.RECONCILIATION_REQUIRED.value
    assert resumed.record["eventId"] == claim.record["eventId"]
    assert resumed.record["correlationId"] == claim.record["correlationId"]
    assert resumed.record["startedAt"] == claim.record["startedAt"]

    repository(
        table, clock=lambda: NOW + IN_PROGRESS_TTL_SECONDS + 1
    ).mark_reactivation_enable_dispatching(
        record=resumed.record,
        role="OPERATOR",
        cognito_sub=str(IDS[2]),
        observed_version=3,
        observed_auth_version=7,
    )
    redispatched = repo.get(str(claim.record["id"]))
    assert redispatched is not None
    assert redispatched["state"] == ReactivationState.ENABLE_DISPATCHING.value
    assert redispatched["enableAttemptedAt"] == marker


def test_reactivation_reconciliation_without_marker_cannot_adopt_enable() -> None:
    table = FakeTable()
    repo = repository(table)
    claim = repo.claim_reactivation(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="target-1",
        expected_version=3,
        request_id=None,
    )
    repo.transition(
        record=claim.record,
        next_state=ReactivationState.RECONCILIATION_REQUIRED.value,
    )
    record = repo.get(str(claim.record["id"]))
    assert record is not None

    with pytest.raises(InvitationSagaInvariantError, match="enable context"):
        repo.transition(record=record, next_state=ReactivationState.COGNITO_ENABLED.value)


def test_reactivation_transition_rejects_worker_with_stale_lease() -> None:
    table = FakeTable()
    first = repository(table)
    kwargs: Any = dict(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="target-1",
        expected_version=3,
        request_id=None,
    )
    stale = first.claim_reactivation(**kwargs).record
    resumed_repo = repository(table, clock=lambda: NOW + IN_PROGRESS_TTL_SECONDS + 1)
    resumed = resumed_repo.claim_reactivation(**kwargs).record

    with pytest.raises(InvitationSagaInvariantError, match="CAS mismatch"):
        first.mark_reactivation_enable_dispatching(
            record=stale,
            role="ADMIN",
            cognito_sub=str(IDS[2]),
            observed_version=3,
            observed_auth_version=7,
        )

    current = first.get(str(stale["id"]))
    assert current is not None
    assert current["state"] == ReactivationState.CLAIMED.value
    assert "enableAttemptedAt" not in current

    resumed_repo.mark_reactivation_enable_dispatching(
        record=resumed,
        role="ADMIN",
        cognito_sub=str(IDS[2]),
        observed_version=3,
        observed_auth_version=7,
    )
    current = first.get(str(stale["id"]))
    assert current is not None
    assert current["state"] == ReactivationState.ENABLE_DISPATCHING.value


def test_reactivation_completed_record_is_terminal_and_replayable() -> None:
    table = FakeTable()
    repo = repository(table)
    kwargs: Any = dict(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="target-1",
        expected_version=3,
        request_id="request-1",
    )
    claim = repo.claim_reactivation(**kwargs)
    repo.mark_reactivation_enable_dispatching(
        record=claim.record,
        role="ADMIN",
        cognito_sub=str(IDS[2]),
        observed_version=3,
        observed_auth_version=7,
    )
    stored = table.items[str(claim.record["id"])]
    stored.update(state=ReactivationState.COMPLETED.value, httpStatus=200)

    replay = repo.claim_reactivation(**kwargs)

    assert replay.created is False
    assert replay.record["state"] == ReactivationState.COMPLETED.value
    assert replay.record["eventId"] == claim.record["eventId"]
    assert replay.record["correlationId"] == claim.record["correlationId"]
    with pytest.raises(InvitationSagaInvariantError, match="reactivation saga transition"):
        validate_transition(
            operation=REACTIVATE_USER_OPERATION,
            current_state=ReactivationState.COMPLETED.value,
            next_state=ReactivationState.CLAIMED.value,
        )


@pytest.mark.parametrize("value", [True, "1", 1.0, None, 0, -1])
def test_reactivation_hash_rejects_invalid_expected_version(value: object) -> None:
    with pytest.raises(InvitationSagaInvariantError, match="reactivate-user request hash"):
        reactivation_request_hash(user_id="target-1", expected_version=value)  # type: ignore[arg-type]


def claim_create(repo: InvitationSagaRepository, *, email: str = "admin@example.test") -> Any:
    return repo.claim_create(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        full_name="Admin Example",
        email=email,
        role="ADMIN",
        request_id=None,
    )


def test_create_claim_generates_stable_ids_ttl_and_no_raw_pii() -> None:
    table = FakeTable()
    generated: list[UUID] = []
    values = iter(IDS)

    def identifier_factory() -> UUID:
        value = next(values)
        generated.append(value)
        return value

    repo = repository(table, identifier_factory=identifier_factory)
    first = claim_create(repo)
    record = first.record
    assert first.created is True
    assert record["userId"] == str(IDS[0])
    assert record["eventId"] == str(IDS[1])
    assert record["correlationId"] == str(IDS[2])
    assert record["expiration"] == NOW + IDEMPOTENCY_TTL_SECONDS
    rendered = repr(record)
    assert "Admin Example" not in rendered
    assert "admin@example.test" not in rendered
    assert "requestBody" not in rendered

    table.items[str(record["id"])]["inProgressExpiration"] = NOW * 1000
    second = claim_create(repo)
    assert second.created is False
    assert second.record["userId"] == record["userId"]
    assert second.record["eventId"] == record["eventId"]
    assert second.record["correlationId"] == record["correlationId"]
    assert generated == IDS


def test_same_key_different_create_hash_is_rejected() -> None:
    table = FakeTable()
    claim_create(repository(table))
    with pytest.raises(IdempotencyKeyReusedError):
        claim_create(repository(table), email="different@example.test")


def test_active_create_claim_is_in_progress() -> None:
    table = FakeTable()
    claim_create(repository(table))
    with pytest.raises(OperationInProgressError):
        claim_create(repository(table))


def test_request_hashes_are_operation_and_payload_specific() -> None:
    assert create_request_hash(
        full_name="  Ａdmin   Example ", email=" ADMIN@EXAMPLE.TEST ", role="ADMIN"
    ) == create_request_hash(full_name="Admin Example", email="admin@example.test", role="ADMIN")
    assert create_request_hash(
        full_name="Admin Example", email="admin@example.test", role="ADMIN"
    ) != create_request_hash(full_name="Admin Example", email="admin@example.test", role="OPERATOR")
    assert resend_request_hash(user_id="user-1", expected_version=1) != resend_request_hash(
        user_id="user-1", expected_version=2
    )


def test_create_transitions_and_invalid_transition() -> None:
    table = FakeTable()
    repo = repository(table)
    record = claim_create(repo).record
    cognito_sub = "55555555-5555-4555-8555-555555555555"
    repo.store_cognito_created(
        record=record,
        cognito_sub=cognito_sub,
        evidence=CognitoIdentityEvidence.CREATE_SUCCESS,
    )
    record.update(
        state=CreateSagaState.COGNITO_CREATED.value,
        cognitoSub=cognito_sub,
        cognitoEvidence=CognitoIdentityEvidence.CREATE_SUCCESS.value,
    )
    for state in (
        CreateSagaState.DDB_COMMITTED,
        CreateSagaState.INVITATION_DISPATCHING,
        CreateSagaState.INVITATION_SENT,
    ):
        repo.transition(record=record, next_state=state.value)
        record["state"] = state.value
    assert (
        table.items[str(record["id"])]["inProgressExpiration"]
        == (NOW + IN_PROGRESS_TTL_SECONDS) * 1000
    )
    repo.store_completed(record=record, http_status=201, response_user_id=str(record["userId"]))
    completed = repo.get(str(record["id"]))
    assert completed is not None
    replay = replay_from_record(completed)
    assert replay.http_status == 201
    assert replay.response_user_id == record["userId"]
    assert "fullName" not in completed and "email" not in completed
    with pytest.raises(InvitationSagaInvariantError):
        repo.transition(record=completed, next_state=CreateSagaState.CLAIMED.value)


def test_all_declared_saga_transitions_are_valid() -> None:
    for create_current, create_next_states in CREATE_TRANSITIONS.items():
        for create_next in create_next_states:
            validate_transition(
                operation="create-user",
                current_state=create_current.value,
                next_state=create_next.value,
            )
    for resend_current, resend_next_states in RESEND_TRANSITIONS.items():
        for resend_next in resend_next_states:
            validate_transition(
                operation=RESEND_INVITATION_OPERATION,
                current_state=resend_current.value,
                next_state=resend_next.value,
            )
    for current, next_states in REACTIVATION_TRANSITIONS.items():
        for next_state in next_states:
            validate_transition(
                operation=REACTIVATE_USER_OPERATION,
                current_state=current.value,
                next_state=next_state.value,
            )
    with pytest.raises(InvitationSagaInvariantError):
        validate_transition(
            operation=REACTIVATE_USER_OPERATION,
            current_state=ReactivationState.COMPLETED.value,
            next_state=ReactivationState.CLAIMED.value,
        )


def test_completed_concurrent_cas_is_recoverable_but_not_silent() -> None:
    table = FakeTable()
    repo = repository(table)
    record = claim_create(repo).record
    cognito_sub = "55555555-5555-4555-8555-555555555555"
    table.items[str(record["id"])].update(
        state=CreateSagaState.COGNITO_CREATED.value,
        cognitoSub=cognito_sub,
        cognitoEvidence=CognitoIdentityEvidence.CREATE_SUCCESS.value,
    )
    with pytest.raises(InvitationSagaConcurrentTransitionError):
        repo.store_cognito_created(
            record=record,
            cognito_sub=cognito_sub,
            evidence=CognitoIdentityEvidence.CREATE_SUCCESS,
        )


def test_incompatible_stale_cas_is_an_invariant_error() -> None:
    table = FakeTable()
    repo = repository(table)
    record = claim_create(repo).record
    table.items[str(record["id"])]["state"] = CreateSagaState.DDB_COMMITTED.value
    with pytest.raises(InvitationSagaInvariantError, match="CAS mismatch"):
        repo.store_cognito_created(
            record=record,
            cognito_sub="55555555-5555-4555-8555-555555555555",
            evidence=CognitoIdentityEvidence.CREATE_SUCCESS,
        )


def test_ddb_committed_transition_can_join_domain_transaction() -> None:
    table = FakeTable()
    repo = repository(table)
    record = claim_create(repo).record
    record.update(
        state=CreateSagaState.COGNITO_CREATED.value,
        cognitoSub="55555555-5555-4555-8555-555555555555",
        cognitoEvidence=CognitoIdentityEvidence.CREATE_SUCCESS.value,
    )
    item = repo.build_transaction_transition(
        record=record, next_state=CreateSagaState.DDB_COMMITTED.value
    )
    update = item["Update"]
    assert isinstance(update, dict)
    assert update["TableName"] == "idempotency"
    assert "requestHash = :request_hash" in str(update["ConditionExpression"])
    deserializer = TypeDeserializer()
    values = update["ExpressionAttributeValues"]
    assert isinstance(values, dict)
    assert deserializer.deserialize(values[":next"]) == "DDB_COMMITTED"
    assert deserializer.deserialize(values[":updated"]) == record["startedAt"]
    assert ":lease" not in values

    with pytest.raises(InvitationSagaInvariantError, match="restricted"):
        repo.build_transaction_transition(
            record=record,
            next_state=CreateSagaState.RECONCILIATION_REQUIRED.value,
        )


def test_ddb_transaction_hook_is_stable_when_wall_clock_changes() -> None:
    table = FakeTable()
    current_time = [NOW]
    repo = repository(table, clock=lambda: current_time[0])
    record = claim_create(repo).record
    record.update(
        state=CreateSagaState.COGNITO_CREATED.value,
        cognitoSub="55555555-5555-4555-8555-555555555555",
        cognitoEvidence=CognitoIdentityEvidence.CREATE_SUCCESS.value,
    )
    first = repo.build_transaction_transition(
        record=record, next_state=CreateSagaState.DDB_COMMITTED.value
    )
    current_time[0] += 300
    second = repo.build_transaction_transition(
        record=record, next_state=CreateSagaState.DDB_COMMITTED.value
    )
    assert first == second


def test_compensated_business_failure_is_durable_and_replayable() -> None:
    table = FakeTable()
    repo = repository(table)
    record = claim_create(repo).record
    cognito_sub = "55555555-5555-4555-8555-555555555555"
    repo.store_cognito_created(
        record=record,
        cognito_sub=cognito_sub,
        evidence=CognitoIdentityEvidence.CREATE_SUCCESS,
    )
    record.update(
        state=CreateSagaState.COGNITO_CREATED.value,
        cognitoSub=cognito_sub,
        cognitoEvidence=CognitoIdentityEvidence.CREATE_SUCCESS.value,
    )
    repo.begin_cognito_compensation(
        record=record,
        http_status=409,
        error_code="EMAIL_ALREADY_EXISTS",
    )
    record.update(
        state=CreateSagaState.COMPENSATING.value,
        terminalHttpStatus=409,
        terminalErrorCode="EMAIL_ALREADY_EXISTS",
    )
    repo.complete_compensation(record=record)

    completed = repo.get(str(record["id"]))
    assert completed is not None
    replay = replay_from_record(completed)
    assert replay.http_status == 409
    assert replay.error_code == "EMAIL_ALREADY_EXISTS"
    assert replay.response_user_id is None


def test_existing_create_claim_rejects_corrupted_stable_identity() -> None:
    table = FakeTable()
    repo = repository(table)
    record = claim_create(repo).record
    table.items[str(record["id"])]["userId"] = "not-a-uuid"
    table.items[str(record["id"])]["inProgressExpiration"] = NOW * 1000
    with pytest.raises(InvitationSagaInvariantError, match="stable identifiers"):
        claim_create(repo)


def test_cognito_transition_requires_identity_and_reconciliation_is_durable() -> None:
    table = FakeTable()
    repo = repository(table)
    record = claim_create(repo).record
    with pytest.raises(InvitationSagaInvariantError, match="reconciled identity"):
        repo.transition(record=record, next_state=CreateSagaState.COGNITO_CREATED.value)

    repo.store_cognito_reconciliation_required(
        record=record,
        reason=CognitoReconciliationReason.IDENTITY_INCOMPATIBLE,
    )
    stored = table.items[str(record["id"])]
    assert stored["state"] == CreateSagaState.RECONCILIATION_REQUIRED.value
    assert stored["errorCode"] == CognitoReconciliationReason.IDENTITY_INCOMPATIBLE.value


def test_create_retryable_and_uncertain_states_are_distinct() -> None:
    table = FakeTable()
    repo = repository(table)
    record = claim_create(repo).record
    record["state"] = CreateSagaState.INVITATION_DISPATCHING.value
    table.items[str(record["id"])]["state"] = record["state"]
    repo.store_delivery_failure(
        record=record,
        retryable_state=CreateSagaState.INVITATION_RETRYABLE.value,
        error_code=INVITATION_DELIVERY_FAILED,
    )
    stored = table.items[str(record["id"])]
    assert stored["state"] == "INVITATION_RETRYABLE"
    assert stored["errorCode"] == INVITATION_DELIVERY_FAILED

    other = claim_create(repository(FakeTable())).record
    other["state"] = CreateSagaState.INVITATION_DISPATCHING.value
    other_table = FakeTable()
    other_table.items[str(other["id"])] = deepcopy(other)
    other_repo = repository(other_table)
    other_repo.store_delivery_failure(
        record=other,
        retryable_state=CreateSagaState.RECONCILIATION_REQUIRED.value,
        error_code=INVITATION_DELIVERY_UNCERTAIN,
    )
    assert other_table.items[str(other["id"])]["state"] == "RECONCILIATION_REQUIRED"


def test_create_delivery_retry_clears_failure_before_successful_replay() -> None:
    table = FakeTable()
    repo = repository(table)
    record = claim_create(repo).record
    cognito_sub = "55555555-5555-4555-8555-555555555555"
    record.update(
        state=CreateSagaState.INVITATION_DISPATCHING.value,
        cognitoSub=cognito_sub,
        cognitoEvidence=CognitoIdentityEvidence.CREATE_SUCCESS.value,
    )
    table.items[str(record["id"])].update(record)
    repo.store_delivery_failure(
        record=record,
        retryable_state=CreateSagaState.INVITATION_RETRYABLE.value,
        error_code=INVITATION_DELIVERY_FAILED,
    )
    record["state"] = CreateSagaState.INVITATION_RETRYABLE.value
    repo.transition(record=record, next_state=CreateSagaState.INVITATION_DISPATCHING.value)
    stored = table.items[str(record["id"])]
    assert "errorCode" not in stored
    assert "httpStatus" not in stored

    record["state"] = CreateSagaState.INVITATION_DISPATCHING.value
    repo.transition(record=record, next_state=CreateSagaState.INVITATION_SENT.value)
    record["state"] = CreateSagaState.INVITATION_SENT.value
    repo.store_completed(record=record, http_status=201, response_user_id=str(record["userId"]))
    replay = replay_from_record(table.items[str(record["id"])])
    assert replay.http_status == 201


def test_resend_namespace_replay_mismatch_and_completed_204() -> None:
    table = FakeTable()
    repo = repository(table)
    claim = repo.claim_resend(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="user-1",
        expected_version=1,
        request_id="request-1",
    )
    record = claim.record
    assert record["operation"] == RESEND_INVITATION_OPERATION
    assert f"#{RESEND_INVITATION_OPERATION}#" in str(record["id"])
    for state in (ResendSagaState.DISPATCHING, ResendSagaState.SENT):
        repo.transition(record=record, next_state=state.value)
        record["state"] = state.value
    repo.store_completed(record=record, http_status=204)
    record.update(state="COMPLETED", httpStatus=204)
    replay = replay_from_record(record)
    assert replay.http_status == 204
    assert replay.response_user_id is None

    replayed = repo.claim_resend(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="user-1",
        expected_version=1,
        request_id="different-request",
    )
    assert replayed.created is False
    with pytest.raises(IdempotencyKeyReusedError):
        repo.claim_resend(
            environment="dev",
            actor_id="actor-1",
            idempotency_key=KEY,
            user_id="user-1",
            expected_version=2,
            request_id=None,
        )


def test_resend_ambiguous_state_cannot_dispatch_again() -> None:
    table = FakeTable()
    repo = repository(table)
    record = repo.claim_resend(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="user-1",
        expected_version=1,
        request_id=None,
    ).record
    record["state"] = ResendSagaState.DISPATCHING.value
    table.items[str(record["id"])]["state"] = record["state"]
    repo.store_delivery_failure(
        record=record,
        retryable_state=ResendSagaState.RECONCILIATION_REQUIRED.value,
        error_code=INVITATION_DELIVERY_UNCERTAIN,
    )
    record["state"] = ResendSagaState.RECONCILIATION_REQUIRED.value
    with pytest.raises(InvitationSagaInvariantError):
        repo.transition(record=record, next_state=ResendSagaState.DISPATCHING.value)


def test_resend_deterministic_failure_can_retry_dispatch() -> None:
    table = FakeTable()
    repo = repository(table)
    record = repo.claim_resend(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="user-1",
        expected_version=1,
        request_id=None,
    ).record
    record["state"] = ResendSagaState.DISPATCHING.value
    table.items[str(record["id"])]["state"] = record["state"]
    repo.store_delivery_failure(
        record=record,
        retryable_state=ResendSagaState.RETRYABLE.value,
        error_code=INVITATION_DELIVERY_FAILED,
    )
    record["state"] = ResendSagaState.RETRYABLE.value
    repo.transition(record=record, next_state=ResendSagaState.DISPATCHING.value)
    assert table.items[str(record["id"])]["state"] == ResendSagaState.DISPATCHING.value


def test_resend_completion_hook_is_stable_and_atomic_ready() -> None:
    table = FakeTable()
    repo = repository(table)
    record = repo.claim_resend(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="user-1",
        expected_version=1,
        request_id="request-1",
    ).record
    record["state"] = ResendSagaState.SENT.value
    table.items[str(record["id"])]["state"] = record["state"]

    first = repo.build_resend_completion_transition(record=record)
    second = repo.build_resend_completion_transition(record=record)

    assert first == second
    update = first["Update"]
    assert isinstance(update, dict)
    assert "#state = :sent" in str(update["ConditionExpression"])
    values = update["ExpressionAttributeValues"]
    assert isinstance(values, dict)
    decoded = {key: TypeDeserializer().deserialize(value) for key, value in values.items()}
    assert decoded[":completed"] == "COMPLETED"
    assert decoded[":status"] == 204

    with pytest.raises(InvitationSagaInvariantError, match="restricted"):
        repo.build_resend_completion_transition(record={**record, "state": "DISPATCHING"})


def test_delivery_failure_state_and_code_must_match() -> None:
    table = FakeTable()
    repo = repository(table)
    record = claim_create(repo).record
    record["state"] = CreateSagaState.INVITATION_DISPATCHING.value
    table.items[str(record["id"])]["state"] = record["state"]
    with pytest.raises(InvitationSagaInvariantError, match="state and code mismatch"):
        repo.store_delivery_failure(
            record=record,
            retryable_state=CreateSagaState.INVITATION_RETRYABLE.value,
            error_code=INVITATION_DELIVERY_UNCERTAIN,
        )


def test_role_change_claim_namespace_hash_ttl_stable_ids_and_privacy() -> None:
    table = FakeTable()
    repo = repository(table)
    claim = repo.claim_role_change(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="user-1",
        role="ADMIN",
        expected_version=1,
        request_id=None,
    )
    record = claim.record
    assert record["operation"] == CHANGE_USER_ROLE_OPERATION
    assert record["state"] == RoleChangeState.CLAIMED.value
    assert record["eventId"] == str(IDS[0])
    assert record["correlationId"] == str(IDS[1])
    assert record["expiration"] == NOW + IDEMPOTENCY_TTL_SECONDS
    assert record["requestHash"] == role_change_request_hash(
        user_id="user-1", role="ADMIN", expected_version=1
    )
    assert "email" not in repr(record).lower()
    assert "fullName" not in repr(record)

    table.items[str(record["id"])]["inProgressExpiration"] = NOW * 1000
    replay = repo.claim_role_change(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="user-1",
        role="ADMIN",
        expected_version=1,
        request_id="different",
    )
    assert replay.record["eventId"] == record["eventId"]
    assert replay.record["correlationId"] == record["correlationId"]


def test_role_change_claim_mismatch_and_active_execution() -> None:
    table = FakeTable()
    repo = repository(table)
    repo.claim_role_change(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="user-1",
        role="ADMIN",
        expected_version=1,
        request_id=None,
    )
    with pytest.raises(OperationInProgressError):
        repo.claim_role_change(
            environment="dev",
            actor_id="actor-1",
            idempotency_key=KEY,
            user_id="user-1",
            role="ADMIN",
            expected_version=1,
            request_id=None,
        )
    with pytest.raises(IdempotencyKeyReusedError):
        repo.claim_role_change(
            environment="dev",
            actor_id="actor-1",
            idempotency_key=KEY,
            user_id="user-1",
            role="OPERATOR",
            expected_version=1,
            request_id=None,
        )


def test_role_change_completion_hook_is_atomic_ready_and_contains_no_pii() -> None:
    table = FakeTable()
    repo = repository(table)
    record = repo.claim_role_change(
        environment="dev",
        actor_id="actor-1",
        idempotency_key=KEY,
        user_id="user-1",
        role="ADMIN",
        expected_version=1,
        request_id="request-1",
    ).record
    response: dict[str, object] = {
        "userId": "user-1",
        "fullName": "Synthetic User",
        "email": "synthetic@example.test",
        "role": "ADMIN",
        "status": "INVITED",
        "version": 2,
        "createdAt": "2026-01-01T00:00:00.000Z",
        "updatedAt": "2027-01-15T08:00:00.000Z",
    }
    transition = repo.build_role_change_completion_transition(record=record, response=response)
    rendered = repr(transition)
    assert "Synthetic User" not in rendered
    assert "synthetic@example.test" not in rendered
    update = transition["Update"]
    assert isinstance(update, dict)
    decoded = {
        key: TypeDeserializer().deserialize(value)
        for key, value in update["ExpressionAttributeValues"].items()
    }
    assert decoded[":completed"] == "COMPLETED"
    assert decoded[":status"] == 200
    assert decoded[":value3"] == 2
