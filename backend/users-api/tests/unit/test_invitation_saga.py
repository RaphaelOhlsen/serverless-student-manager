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
    CREATE_TRANSITIONS,
    IDEMPOTENCY_TTL_SECONDS,
    IN_PROGRESS_TTL_SECONDS,
    INVITATION_DELIVERY_FAILED,
    INVITATION_DELIVERY_UNCERTAIN,
    RESEND_INVITATION_OPERATION,
    RESEND_TRANSITIONS,
    CognitoIdentityEvidence,
    CognitoReconciliationReason,
    CreateSagaState,
    ResendSagaState,
    create_request_hash,
    replay_from_record,
    resend_request_hash,
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
