import json
from copy import deepcopy
from dataclasses import replace
from typing import Any

import boto3  # type: ignore[import-untyped]
import pytest
from boto3.dynamodb.types import TypeDeserializer  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from botocore.stub import Stubber  # type: ignore[import-untyped]
from students_api.errors import (
    StudentEmailAlreadyExistsError,
    StudentUpdateInvariantError,
    StudentUpdateUnresolvedError,
    StudentVersionConflictError,
)
from students_api.repositories.student_repository import StudentRepository
from students_api.repositories.update_transaction import PUBLIC_FIELDS, UpdateTransactionContext


class Client:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.error = error

    def transact_write_items(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {}

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("No recovery reads in this primitive")


class Table:
    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError

    def query(self, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError


CURRENT = {
    "studentId": "student-1",
    "registrationNumber": "MAT-1",
    "status": "INACTIVE",
    "createdAt": "2020-01-01T00:00:00.000Z",
    "createdBy": "creator",
    "updatedAt": "2020-01-01T00:00:00.000Z",
    "version": 3,
    "fullName": "Aluno Teste",
    "studentEmail": "old@example.com",
    "normalizedEmail": "old@example.com",
    "phone": "+5511999999999",
    "birthDate": "2000-01-01",
}
CONTEXT = UpdateTransactionContext(
    actor_id="actor",
    correlation_id="correlation",
    event_id="event",
    occurred_at="2026-09-10T12:00:00.000Z",
    audit_expires_at=1900000000,
    idempotency_id="update-student#scoped-id",
    request_hash="request-hash",
    client_request_token="stable-transaction-token",
    in_progress_expiration=1_000_000,
)


def run(client: Any, *, email: bool = False) -> None:
    target = {k: CURRENT[k] for k in ("fullName", "studentEmail", "phone", "birthDate")}
    target["fullName"] = "Novo Nome"
    if email:
        target["studentEmail"] = "new@example.com"
    StudentRepository(
        Table(), client=client, students_table_name="students", audit_table_name="audit"
    ).update_student(
        current=CURRENT,
        target=target,
        expected_version=3,
        context=CONTEXT,
        idempotency_table_name="idempotency",
    )


def decode(values: dict[str, Any]) -> dict[str, Any]:
    return {k: TypeDeserializer().deserialize(v) for k, v in values.items()}


@pytest.mark.parametrize("email", [False, True])
def test_atomic_update(email: bool) -> None:
    client = Client()
    run(client, email=email)
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["ClientRequestToken"] == CONTEXT.client_request_token
    items = call["TransactItems"]
    assert len(items) == (5 if email else 3)
    profile = items[0]["Update"]
    names = profile["ExpressionAttributeNames"]
    values = decode(profile["ExpressionAttributeValues"])
    assert "#version = :expected" in profile["ConditionExpression"]
    assert "attribute_exists(#pk)" in profile["ConditionExpression"]
    assert values[":expected"] == 3
    assigned = {
        names[left.strip()]: values[right.strip()]
        for left, right in (part.split("=") for part in profile["UpdateExpression"][4:].split(","))
    }
    assert assigned["version"] == 4
    assert assigned["updatedAt"] == CONTEXT.occurred_at
    assert assigned["updatedBy"] == CONTEXT.actor_id
    assert assigned["normalizedName"] == "novo nome"
    assert assigned["GSI1SK"] == assigned["GSI2SK"] == "NAME#novo nome#STUDENT#student-1"
    assert (
        not {"studentId", "registrationNumber", "status", "createdAt", "createdBy"}
        & assigned.keys()
    )
    audit = decode(items[-2]["Put"]["Item"])
    assert audit["eventType"] == "STUDENT_UPDATED" and audit["result"] == "SUCCESS"
    assert audit["resourceId"] == CURRENT["studentId"]
    assert audit["actorId"] == CONTEXT.actor_id
    assert audit["correlationId"] == CONTEXT.correlation_id
    assert audit["occurredAt"] == CONTEXT.occurred_at
    assert audit["changes"] == {
        "fields": ["fullName", "studentEmail"] if email else ["fullName"],
        "version": {"from": 3, "to": 4},
    }
    assert "Novo Nome" not in str(audit) and "@example.com" not in str(audit)
    idem = items[-1]["Update"]
    iv = decode(idem["ExpressionAttributeValues"])
    assert iv[":pending"] == "INPROGRESS" and iv[":completed"] == "COMPLETED"
    for guard in (
        "#status = :pending",
        "#validation = :hash",
    ):
        assert guard in idem["ConditionExpression"]
    assert decode(idem["Key"])["id"] == CONTEXT.idempotency_id
    assert iv[":hash"] == CONTEXT.request_hash
    response = json.loads(iv[":data"])
    assert set(response) == set(PUBLIC_FIELDS)
    assert response["version"] == 4 and response["status"] == "INACTIVE"
    assert response["studentId"] == CURRENT["studentId"]
    assert response["registrationNumber"] == CURRENT["registrationNumber"]
    assert response["createdAt"] == CURRENT["createdAt"]
    assert "createdBy" not in response
    if email:
        assert decode(items[1]["Put"]["Item"])["PK"] == "UNIQUE#EMAIL#new@example.com"
        assert items[1]["Put"]["ConditionExpression"] == (
            "attribute_not_exists(PK) AND attribute_not_exists(SK)"
        )
        assert decode(items[2]["Delete"]["Key"])["PK"] == "UNIQUE#EMAIL#old@example.com"
        assert "#owner = :owner" in items[2]["Delete"]["ConditionExpression"]
    else:
        assert "UNIQUE#EMAIL" not in str(items)
    keys = []
    for item in items:
        op = next(iter(item.values()))
        key = decode(op.get("Key", op.get("Item")))
        keys.append((op["TableName"], key.get("PK", key.get("id")), key.get("SK")))
    assert len(keys) == len(set(keys))
    # SDK validates the real low-level request shape locally, without any AWS call.
    sdk = boto3.client(
        "dynamodb",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    with Stubber(sdk) as stub:
        stub.add_response("transact_write_items", {}, call)
        run(sdk, email=email)
        stub.assert_no_pending_responses()


def test_effective_completion_is_guarded_by_exact_claim_generation() -> None:
    client = Client()
    run(client)

    completion = client.calls[0]["TransactItems"][-1]["Update"]
    values = decode(completion["ExpressionAttributeValues"])
    assert completion["ExpressionAttributeNames"]["#lease"] == "in_progress_expiration"
    assert "#lease = :lease" in completion["ConditionExpression"]
    assert values[":lease"] == CONTEXT.in_progress_expiration


def test_email_change_synchronizes_profile_and_reservation_normalized_email() -> None:
    client = Client()
    run(client, email=True)

    items = client.calls[0]["TransactItems"]
    profile = items[0]["Update"]
    names = profile["ExpressionAttributeNames"]
    values = decode(profile["ExpressionAttributeValues"])
    assigned = {
        names[left.strip()]: values[right.strip()]
        for left, right in (part.split("=") for part in profile["UpdateExpression"][4:].split(","))
    }
    assert assigned["studentEmail"] == assigned["normalizedEmail"] == "new@example.com"
    assert decode(items[1]["Put"]["Item"])["PK"] == (f"UNIQUE#EMAIL#{assigned['normalizedEmail']}")


@pytest.mark.parametrize(
    ("failed", "expected"),
    [
        ([0], StudentVersionConflictError),
        ([1], StudentEmailAlreadyExistsError),
        ([0, 1], StudentVersionConflictError),
        ([2], StudentUpdateInvariantError),
        ([4], StudentUpdateInvariantError),
        ([3], StudentUpdateInvariantError),
        ([0, 2], StudentUpdateInvariantError),
    ],
)
def test_conditional_failures(failed: list[int], expected: type[Exception]) -> None:
    reasons = [{"Code": "ConditionalCheckFailed" if i in failed else "None"} for i in range(5)]
    error = ClientError(
        {"Error": {"Code": "TransactionCanceledException"}, "CancellationReasons": reasons},
        "TransactWriteItems",
    )
    with pytest.raises(expected):
        run(Client(error), email=True)


@pytest.mark.parametrize(
    "reasons",
    [
        None,
        [],
        [{"Code": "ConditionalCheckFailed"}],
        [{"Code": "TransactionConflict"}] * 5,
        [{"Code": "None"}] * 5,
        [{"Code": "ConditionalCheckFailed"}, {}, {}, {}, {}],
    ],
)
def test_insufficient_evidence_is_unresolved(reasons: object) -> None:
    error = ClientError(
        {"Error": {"Code": "TransactionCanceledException"}, "CancellationReasons": reasons},
        "TransactWriteItems",
    )
    with pytest.raises(StudentUpdateUnresolvedError):
        run(Client(error), email=True)


def test_transport_timeout_is_not_version_conflict() -> None:
    error = TimeoutError()
    with pytest.raises(StudentUpdateUnresolvedError) as result:
        run(Client(error))
    assert result.value.__cause__ is error


def test_phone_only_does_not_touch_name_indexes_or_reservations() -> None:
    client = Client()
    target = {k: CURRENT[k] for k in ("fullName", "studentEmail", "phone", "birthDate")}
    target["phone"] = "+5521999999999"
    StudentRepository(
        Table(), client=client, students_table_name="students", audit_table_name="audit"
    ).update_student(
        current=CURRENT,
        target=target,
        expected_version=3,
        context=CONTEXT,
        idempotency_table_name="idempotency",
    )
    items = client.calls[0]["TransactItems"]
    assert len(items) == 3
    names = items[0]["Update"]["ExpressionAttributeNames"].values()
    assert not {
        "GSI1SK",
        "GSI2SK",
        "normalizedName",
        "normalizedEmail",
        "fullName",
        "studentEmail",
    } & set(names)
    assert decode(items[1]["Put"]["Item"])["changes"]["fields"] == ["phone"]


def test_noop_is_rejected_without_transaction() -> None:
    client = Client()
    target = {k: CURRENT[k] for k in ("fullName", "studentEmail", "phone", "birthDate")}
    with pytest.raises(StudentUpdateInvariantError):
        StudentRepository(
            Table(), client=client, students_table_name="students", audit_table_name="audit"
        ).update_student(
            current=CURRENT,
            target=target,
            expected_version=3,
            context=CONTEXT,
            idempotency_table_name="idempotency",
        )
    assert client.calls == []


def test_rejects_mismatched_current_version_without_transaction() -> None:
    client = Client()
    target = {k: CURRENT[k] for k in ("fullName", "studentEmail", "phone", "birthDate")}
    target["phone"] = "+5521999999999"
    with pytest.raises(StudentUpdateInvariantError):
        StudentRepository(
            Table(), client=client, students_table_name="students", audit_table_name="audit"
        ).update_student(
            current={**CURRENT, "version": 2},
            target=target,
            expected_version=3,
            context=CONTEXT,
            idempotency_table_name="idempotency",
        )
    assert client.calls == []


@pytest.mark.parametrize("token", ["", "x" * 37])
def test_rejects_client_request_token_outside_sdk_limits(token: str) -> None:
    client = Client()
    target = {k: CURRENT[k] for k in ("fullName", "studentEmail", "phone", "birthDate")}
    target["phone"] = "+5521999999999"
    with pytest.raises(StudentUpdateInvariantError):
        StudentRepository(
            Table(), client=client, students_table_name="students", audit_table_name="audit"
        ).update_student(
            current=CURRENT,
            target=target,
            expected_version=3,
            context=replace(CONTEXT, client_request_token=token),
            idempotency_table_name="idempotency",
        )
    assert client.calls == []


def test_non_cancellation_service_error_remains_unresolved() -> None:
    with pytest.raises(StudentUpdateUnresolvedError):
        run(Client(ClientError({"Error": {"Code": "InternalServerError"}}, "TransactWriteItems")))


def test_same_generation_retries_use_identical_transaction_payload_and_token() -> None:
    client = Client()

    run(client, email=True)
    run(client, email=True)

    assert client.calls[0] == client.calls[1]


class RollbackClient(Client):
    def __init__(self, failed_index: int) -> None:
        super().__init__()
        self.failed_index = failed_index
        self.state: dict[str, object] = {
            "profile": deepcopy(CURRENT),
            "newReservation": None,
            "oldReservation": {"studentId": "student-1"},
            "audit": None,
            "idempotency": {
                "status": "INPROGRESS",
                "validation": CONTEXT.request_hash,
                "in_progress_expiration": CONTEXT.in_progress_expiration,
            },
        }

    def transact_write_items(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        reasons = [
            {"Code": "ConditionalCheckFailed" if index == self.failed_index else "None"}
            for index in range(len(kwargs["TransactItems"]))
        ]
        raise ClientError(
            {"Error": {"Code": "TransactionCanceledException"}, "CancellationReasons": reasons},
            "TransactWriteItems",
        )


def test_duplicate_email_rolls_back_every_transaction_participant() -> None:
    client = RollbackClient(failed_index=1)
    before = deepcopy(client.state)

    with pytest.raises(StudentEmailAlreadyExistsError):
        run(client, email=True)

    assert client.state == before
    assert len(client.calls[0]["TransactItems"]) == 5


def test_old_email_reservation_wrong_owner_is_invariant_and_rolls_back() -> None:
    client = RollbackClient(failed_index=2)
    client.state["oldReservation"] = {"studentId": "other-student"}
    before = deepcopy(client.state)

    with pytest.raises(StudentUpdateInvariantError):
        run(client, email=True)

    assert client.state == before
    old_reservation_delete = client.calls[0]["TransactItems"][2]["Delete"]
    assert "#owner = :owner" in old_reservation_delete["ConditionExpression"]


class StaleCompletionClient(Client):
    def __init__(self) -> None:
        super().__init__()
        self.state: dict[str, object] = {
            "profile": deepcopy(CURRENT),
            "newReservation": None,
            "oldReservation": {"studentId": "student-1"},
            "audit": None,
            "idempotency": {
                "status": "INPROGRESS",
                "validation": CONTEXT.request_hash,
                "in_progress_expiration": CONTEXT.in_progress_expiration + 61_000,
            },
        }

    def transact_write_items(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        items = kwargs["TransactItems"]
        completion = items[-1]["Update"]
        names = completion["ExpressionAttributeNames"]
        values = decode(completion["ExpressionAttributeValues"])
        protects_lease = (
            names.get("#lease") == "in_progress_expiration"
            and "#lease = :lease" in completion["ConditionExpression"]
            and values.get(":lease") == CONTEXT.in_progress_expiration
        )
        if protects_lease:
            reasons = [{"Code": "None"} for _ in items]
            reasons[-1] = {"Code": "ConditionalCheckFailed"}
            raise ClientError(
                {
                    "Error": {"Code": "TransactionCanceledException"},
                    "CancellationReasons": reasons,
                },
                "TransactWriteItems",
            )
        self.state.update(
            profile={**CURRENT, "studentEmail": "new@example.com", "version": 4},
            newReservation={"studentId": "student-1"},
            oldReservation=None,
            audit={"eventType": "STUDENT_UPDATED"},
            idempotency={"status": "COMPLETED"},
        )
        return {}


def test_stale_worker_effective_completion_fails_atomically() -> None:
    client = StaleCompletionClient()
    before = deepcopy(client.state)

    with pytest.raises(StudentUpdateInvariantError):
        run(client, email=True)

    assert client.state == before
