import json
from typing import Any

import boto3  # type: ignore[import-untyped]
import pytest
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from botocore.stub import Stubber  # type: ignore[import-untyped]
from students_api.errors import (
    IdempotencyKeyReusedError,
    OperationInProgressError,
    StudentUpdateInvariantError,
    StudentUpdateUnresolvedError,
)
from students_api.idempotency import UpdateStudentIdempotency

RESPONSE: dict[str, object] = {
    "studentId": "student-1",
    "registrationNumber": "MAT-1",
    "fullName": "Novo Nome",
    "studentEmail": "maria@example.com",
    "phone": "+5511999999999",
    "birthDate": "2000-01-01",
    "status": "ACTIVE",
    "version": 4,
    "createdAt": "2020-01-01T00:00:00.000Z",
    "updatedAt": "2026-09-11T12:00:00.000Z",
}


def decode(item: dict[str, Any]) -> dict[str, Any]:
    return {key: TypeDeserializer().deserialize(value) for key, value in item.items()}


def encode(item: dict[str, Any]) -> dict[str, Any]:
    return {key: TypeSerializer().serialize(value) for key, value in item.items()}


class Client:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_update: Exception | None = None

    def put_item(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("put", kwargs))
        item = decode(kwargs["Item"])
        key = item["id"]
        if key in self.items:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        self.items[key] = item
        return {}

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get", kwargs))
        key = decode(kwargs["Key"])["id"]
        item = self.items.get(key)
        return {"Item": encode(item)} if item is not None else {}

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("update", kwargs))
        if self.fail_update is not None:
            raise self.fail_update
        values = decode(kwargs["ExpressionAttributeValues"])
        key = decode(kwargs["Key"])["id"]
        item = self.items[key]
        assert item["status"] == values[":pending"]
        assert item["validation"] == values[":hash"]
        item.update(status=values[":completed"], data=values[":data"])
        return {}

    def delete_item(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("delete", kwargs))
        values = decode(kwargs["ExpressionAttributeValues"])
        key = decode(kwargs["Key"])["id"]
        item = self.items[key]
        assert item["status"] == values[":pending"]
        assert item["validation"] == values[":hash"]
        del self.items[key]
        return {}


def acquire(
    idempotency: UpdateStudentIdempotency,
    *,
    payload: dict[str, str | int] | None = None,
) -> Any:
    return idempotency.acquire(
        environment="dev",
        actor_id="actor-1",
        idempotency_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        student_id="student-1",
        payload=payload or {"expectedVersion": 3, "fullName": "Novo Nome"},
    )


def test_acquires_scoped_record_with_24_hour_ttl_and_canonical_hash() -> None:
    first_client = Client()
    first = acquire(
        UpdateStudentIdempotency(first_client, "idempotency", clock=lambda: 1000),
        payload={"fullName": "Novo Nome", "expectedVersion": 3, "phone": "+5521999999999"},
    )
    second_client = Client()
    second = acquire(
        UpdateStudentIdempotency(second_client, "idempotency", clock=lambda: 1000),
        payload={"phone": "+5521999999999", "expectedVersion": 3, "fullName": "Novo Nome"},
    )
    item = first_client.items[first.idempotency_id]
    assert first.idempotency_id.startswith("update-student#")
    assert first.request_hash == second.request_hash
    assert item["status"] == "INPROGRESS"
    assert item["validation"] == first.request_hash
    assert item["expiration"] == 87400


def test_identity_and_request_scope_change_hashes() -> None:
    baseline_client = Client()
    baseline = acquire(UpdateStudentIdempotency(baseline_client, "idempotency"))
    actor_client = Client()
    actor = UpdateStudentIdempotency(actor_client, "idempotency").acquire(
        environment="dev",
        actor_id="actor-2",
        idempotency_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        student_id="student-1",
        payload={"expectedVersion": 3, "fullName": "Novo Nome"},
    )
    student_client = Client()
    student = UpdateStudentIdempotency(student_client, "idempotency").acquire(
        environment="dev",
        actor_id="actor-1",
        idempotency_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        student_id="student-2",
        payload={"expectedVersion": 3, "fullName": "Novo Nome"},
    )
    assert actor.idempotency_id != baseline.idempotency_id
    assert student.idempotency_id == baseline.idempotency_id
    assert student.request_hash != baseline.request_hash


def test_acquisition_request_matches_installed_dynamodb_sdk_shape() -> None:
    capture = Client()
    acquire(UpdateStudentIdempotency(capture, "idempotency", clock=lambda: 1000))
    expected = capture.calls[0][1]
    sdk = boto3.client(
        "dynamodb",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    with Stubber(sdk) as stub:
        stub.add_response("put_item", {}, expected)
        acquire(UpdateStudentIdempotency(sdk, "idempotency", clock=lambda: 1000))
        stub.assert_no_pending_responses()


def test_completed_replay_returns_stored_response() -> None:
    client = Client()
    idempotency = UpdateStudentIdempotency(client, "idempotency")
    record = acquire(idempotency)
    client.items[record.idempotency_id].update(status="COMPLETED", data=json.dumps(RESPONSE))

    replay = acquire(idempotency)

    assert replay.response == RESPONSE
    get = next(call for name, call in client.calls if name == "get")
    assert get["ConsistentRead"] is True


def test_same_key_different_request_is_rejected() -> None:
    client = Client()
    idempotency = UpdateStudentIdempotency(client, "idempotency")
    acquire(idempotency)

    with pytest.raises(IdempotencyKeyReusedError):
        acquire(idempotency, payload={"expectedVersion": 3, "fullName": "Outro Nome"})


def test_matching_inprogress_reports_operation_in_progress() -> None:
    client = Client()
    idempotency = UpdateStudentIdempotency(client, "idempotency")
    acquire(idempotency)

    with pytest.raises(OperationInProgressError):
        acquire(idempotency)


def test_noop_completion_persists_replay_response() -> None:
    client = Client()
    idempotency = UpdateStudentIdempotency(client, "idempotency")
    record = acquire(idempotency)
    response = {**RESPONSE, "version": 3, "updatedAt": "2025-01-01T00:00:00.000Z"}

    assert idempotency.complete_noop(record, response) == response
    assert acquire(idempotency).response == response


def test_uncertain_noop_completion_recovers_durable_completed_result() -> None:
    client = Client()
    idempotency = UpdateStudentIdempotency(client, "idempotency")
    record = acquire(idempotency)
    stored = {**RESPONSE, "version": 3, "updatedAt": "2025-01-01T00:00:00.000Z"}
    client.items[record.idempotency_id].update(status="COMPLETED", data=json.dumps(stored))
    client.fail_update = TimeoutError()

    assert idempotency.complete_noop(record, stored) == stored


def test_uncertain_noop_still_inprogress_is_not_a_version_conflict() -> None:
    client = Client()
    idempotency = UpdateStudentIdempotency(client, "idempotency")
    record = acquire(idempotency)
    client.fail_update = TimeoutError()

    with pytest.raises(OperationInProgressError):
        idempotency.complete_noop(record, {"version": 3})


def test_uncertain_noop_retries_same_conditional_completion_once() -> None:
    class RetryClient(Client):
        attempts = 0

        def update_item(self, **kwargs: Any) -> dict[str, Any]:
            self.attempts += 1
            if self.attempts == 1:
                raise TimeoutError
            return super().update_item(**kwargs)

    client = RetryClient()
    idempotency = UpdateStudentIdempotency(client, "idempotency")
    record = acquire(idempotency)
    response = {**RESPONSE, "version": 3, "updatedAt": "2025-01-01T00:00:00.000Z"}

    assert idempotency.complete_noop(record, response) == response
    assert client.attempts == 2


def test_release_conditionally_removes_only_matching_inprogress_record() -> None:
    client = Client()
    idempotency = UpdateStudentIdempotency(client, "idempotency")
    record = acquire(idempotency)

    idempotency.release(record)

    assert record.idempotency_id not in client.items


@pytest.mark.parametrize("status", ["FAILED", None])
def test_impossible_persisted_state_is_technical_invariant(status: str | None) -> None:
    client = Client()
    idempotency = UpdateStudentIdempotency(client, "idempotency")
    record = acquire(idempotency)
    if status is None:
        del client.items[record.idempotency_id]["status"]
    else:
        client.items[record.idempotency_id]["status"] = status

    with pytest.raises(StudentUpdateInvariantError):
        idempotency.resolve(record)


def test_transport_failure_during_acquisition_is_unresolved() -> None:
    class FailingClient(Client):
        def put_item(self, **kwargs: Any) -> dict[str, Any]:
            raise TimeoutError

    with pytest.raises(StudentUpdateUnresolvedError):
        acquire(UpdateStudentIdempotency(FailingClient(), "idempotency"))
