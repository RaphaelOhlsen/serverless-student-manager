import json
from dataclasses import replace
from typing import Any

import boto3  # type: ignore[import-untyped]
import pytest
from boto3.dynamodb.types import TypeDeserializer  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from botocore.stub import Stubber  # type: ignore[import-untyped]
from students_api.errors import (
    StudentLifecycleConditionError,
    StudentLifecycleInvariantError,
    StudentLifecycleUnresolvedError,
)
from students_api.repositories.lifecycle_transaction import (
    LifecycleAuditEvent,
    LifecycleIdempotencyCompletion,
    LifecycleTransition,
)
from students_api.repositories.student_repository import StudentRepository
from students_api.repositories.update_transaction import PUBLIC_FIELDS


class Client:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.error = error

    def transact_write_items(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return {}

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("Lifecycle persistence must not read")


class Table:
    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError

    def query(self, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError


REASON = "Motivo sintético de teste"
AUDIT_EVENT = LifecycleAuditEvent(
    actor_id="actor",
    correlation_id="correlation",
    event_id="event",
    occurred_at="2026-09-11T12:00:00.000Z",
    audit_expires_at=1900000000,
    reason=REASON,
)
IDEMPOTENCY = LifecycleIdempotencyCompletion(
    idempotency_id="deactivate-student#scoped-id",
    request_hash="request-hash",
    client_request_token="stable-lifecycle-token",
)


def response(*, status: str, version: int) -> dict[str, object]:
    value: dict[str, object] = {
        "studentId": "student-1",
        "registrationNumber": "MAT-1",
        "fullName": "Aluno Teste",
        "studentEmail": "student@example.invalid",
        "phone": "+12025550123",
        "birthDate": "2000-01-01",
        "status": status,
        "version": version,
        "createdAt": "2026-01-01T00:00:00.000Z",
        "updatedAt": AUDIT_EVENT.occurred_at,
    }
    assert set(value) == set(PUBLIC_FIELDS)
    return value


def transition(*, deactivate: bool = True) -> LifecycleTransition:
    source, target = ("ACTIVE", "INACTIVE") if deactivate else ("INACTIVE", "ACTIVE")
    audit_event = AUDIT_EVENT if deactivate else replace(AUDIT_EVENT, reason=None)
    idempotency = (
        IDEMPOTENCY
        if deactivate
        else replace(IDEMPOTENCY, idempotency_id="reactivate-student#scoped-id")
    )
    return LifecycleTransition(
        student_id="student-1",
        expected_version=3,
        source_status=source,
        target_status=target,
        public_response=response(status=target, version=4),
        audit_event=audit_event,
        idempotency=idempotency,
    )


def run(client: Any, *, deactivate: bool = True) -> None:
    StudentRepository(
        Table(), client=client, students_table_name="students", audit_table_name="audit"
    ).transition_student_lifecycle(
        transition=transition(deactivate=deactivate),
        idempotency_table_name="idempotency",
    )


def decode(values: dict[str, Any]) -> dict[str, Any]:
    return {key: TypeDeserializer().deserialize(value) for key, value in values.items()}


@pytest.mark.parametrize(
    ("deactivate", "source", "target", "event_type"),
    [
        (True, "ACTIVE", "INACTIVE", "STUDENT_DEACTIVATED"),
        (False, "INACTIVE", "ACTIVE", "STUDENT_REACTIVATED"),
    ],
)
def test_effective_transition_is_one_valid_three_item_transaction(
    deactivate: bool, source: str, target: str, event_type: str
) -> None:
    client = Client()
    run(client, deactivate=deactivate)

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["ClientRequestToken"] == IDEMPOTENCY.client_request_token
    items = call["TransactItems"]
    assert len(items) == 3
    assert [next(iter(item)) for item in items] == ["Update", "Put", "Update"]

    profile = items[0]["Update"]
    names = profile["ExpressionAttributeNames"]
    values = decode(profile["ExpressionAttributeValues"])
    for condition in (
        "attribute_exists(#pk)",
        "attribute_exists(#sk)",
        "#version = :expected",
        "#status = :source",
    ):
        assert condition in profile["ConditionExpression"]
    assert values[":expected"] == 3
    assert values[":source"] == source
    assigned = {
        names[left.strip()]: values[right.strip()]
        for left, right in (part.split("=") for part in profile["UpdateExpression"][4:].split(","))
    }
    assert assigned == {
        "status": target,
        "GSI1PK": f"STATUS#{target}",
        "version": 4,
        "updatedAt": AUDIT_EVENT.occurred_at,
        "updatedBy": AUDIT_EVENT.actor_id,
    }

    audit = decode(items[1]["Put"]["Item"])
    assert audit["eventType"] == event_type
    assert audit["result"] == "SUCCESS"
    assert audit["changes"] == {
        "status": {"from": source, "to": target},
        "version": {"from": 3, "to": 4},
    }
    if deactivate:
        assert audit["reason"] == REASON
    else:
        assert "reason" not in audit
    assert "Aluno Teste" not in str(audit)
    assert "@example.invalid" not in str(audit)

    idempotency = items[2]["Update"]
    idempotency_values = decode(idempotency["ExpressionAttributeValues"])
    assert (
        decode(idempotency["Key"])["id"]
        == transition(deactivate=deactivate).idempotency.idempotency_id
    )
    assert idempotency_values[":pending"] == "INPROGRESS"
    assert idempotency_values[":completed"] == "COMPLETED"
    assert idempotency_values[":hash"] == IDEMPOTENCY.request_hash
    assert "#status = :pending" in idempotency["ConditionExpression"]
    assert "#validation = :hash" in idempotency["ConditionExpression"]
    replay = json.loads(idempotency_values[":data"])
    assert replay == response(status=target, version=4)
    assert REASON not in idempotency_values[":data"]

    serialized = str(items)
    assert "UNIQUE#EMAIL" not in serialized
    assert "UNIQUE#REGISTRATION" not in serialized
    assert "deactivatedAt" not in serialized
    assert "deactivatedBy" not in serialized

    keys = []
    for item in items:
        operation = next(iter(item.values()))
        key = decode(operation.get("Key", operation.get("Item")))
        keys.append((operation["TableName"], key.get("PK", key.get("id")), key.get("SK")))
    assert len(keys) == len(set(keys))

    sdk = boto3.client(
        "dynamodb",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    with Stubber(sdk) as stub:
        stub.add_response("transact_write_items", {}, call)
        run(sdk, deactivate=deactivate)
        stub.assert_no_pending_responses()


def transaction_error(reasons: object) -> ClientError:
    return ClientError(
        {"Error": {"Code": "TransactionCanceledException"}, "CancellationReasons": reasons},
        "TransactWriteItems",
    )


def test_profile_condition_failure_remains_neutral() -> None:
    error = transaction_error(
        [{"Code": "ConditionalCheckFailed"}, {"Code": "None"}, {"Code": "None"}]
    )
    with pytest.raises(StudentLifecycleConditionError) as result:
        run(Client(error))
    assert result.value.__cause__ is error
    assert str(result.value) == ""


@pytest.mark.parametrize("failed", [{1}, {2}, {0, 1}, {0, 2}, {1, 2}])
def test_audit_or_idempotency_condition_failure_is_invariant(failed: set[int]) -> None:
    reasons = [
        {"Code": "ConditionalCheckFailed" if index in failed else "None"} for index in range(3)
    ]
    with pytest.raises(StudentLifecycleInvariantError):
        run(Client(transaction_error(reasons)))


@pytest.mark.parametrize(
    "error",
    [
        transaction_error(None),
        transaction_error([]),
        transaction_error([{"Code": "ConditionalCheckFailed"}]),
        transaction_error([{"Code": "TransactionConflict"}] * 3),
        transaction_error([{"Code": "None"}] * 3),
        ClientError({"Error": {"Code": "InternalServerError"}}, "TransactWriteItems"),
        TimeoutError(),
    ],
)
def test_incomplete_or_uncertain_result_is_unresolved(error: Exception) -> None:
    with pytest.raises(StudentLifecycleUnresolvedError) as result:
        run(Client(error))
    assert result.value.__cause__ is error


@pytest.mark.parametrize(
    "value",
    [
        replace(transition(), source_status="INACTIVE"),
        replace(transition(), target_status="ACTIVE"),
        replace(transition(), expected_version=0),
        replace(transition(), public_response={**response(status="INACTIVE", version=4), "x": 1}),
        replace(transition(), public_response=response(status="INACTIVE", version=3)),
        replace(transition(), audit_event=replace(AUDIT_EVENT, reason=None)),
        replace(transition(deactivate=False), audit_event=AUDIT_EVENT),
        replace(transition(), idempotency=replace(IDEMPOTENCY, client_request_token="")),
        replace(transition(), idempotency=replace(IDEMPOTENCY, client_request_token="x" * 37)),
    ],
)
def test_invalid_transition_is_rejected_before_write(value: LifecycleTransition) -> None:
    client = Client()
    with pytest.raises(StudentLifecycleInvariantError) as result:
        StudentRepository(
            Table(), client=client, students_table_name="students", audit_table_name="audit"
        ).transition_student_lifecycle(
            transition=value,
            idempotency_table_name="idempotency",
        )
    assert client.calls == []
    assert REASON not in str(result.value)


def test_reason_is_excluded_from_audit_event_repr() -> None:
    assert REASON not in repr(AUDIT_EVENT)
