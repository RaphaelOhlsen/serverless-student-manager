import json
from decimal import Decimal
from typing import Any

import pytest
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from students_api.errors import (
    IdempotencyKeyReusedError,
    OperationInProgressError,
    StudentLifecycleInvariantError,
    StudentLifecycleUnresolvedError,
)
from students_api.idempotency import LifecycleOperation, StudentLifecycleIdempotency

RESPONSE: dict[str, object] = {
    "studentId": "student-1",
    "registrationNumber": "MAT-1",
    "fullName": "Aluno Teste",
    "studentEmail": "student@example.invalid",
    "phone": "+12025550123",
    "birthDate": "2000-01-01",
    "status": "INACTIVE",
    "version": 4,
    "createdAt": "2020-01-01T00:00:00.000Z",
    "updatedAt": "2026-09-11T12:00:00.000Z",
}
REASON = "Motivo sintético seguro"


def decode(item: dict[str, Any]) -> dict[str, Any]:
    return {key: TypeDeserializer().deserialize(value) for key, value in item.items()}


def encode(item: dict[str, Any]) -> dict[str, Any]:
    return {key: TypeSerializer().serialize(value) for key, value in item.items()}


class Client:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_put: Exception | None = None
        self.fail_update: Exception | None = None

    def put_item(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("put", kwargs))
        if self.fail_put is not None:
            raise self.fail_put
        item = decode(kwargs["Item"])
        key = item["id"]
        if key in self.items:
            values = decode(kwargs.get("ExpressionAttributeValues", {}))
            now = values.get(":now")
            if not isinstance(now, (int, Decimal)) or self.items[key].get("expiration", now) >= now:
                raise self._conditional_failure("PutItem")
        self.items[key] = item
        return {}

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get", kwargs))
        item = self.items.get(decode(kwargs["Key"])["id"])
        return {"Item": encode(item)} if item is not None else {}

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("update", kwargs))
        if self.fail_update is not None:
            raise self.fail_update
        key = decode(kwargs["Key"])["id"]
        values = decode(kwargs["ExpressionAttributeValues"])
        item = self.items[key]
        if not self._condition_matches_generation(item, kwargs, values):
            raise self._conditional_failure("UpdateItem")
        if ":new_lease" in values:
            item["in_progress_expiration"] = values[":new_lease"]
        else:
            item.update(status=values[":completed"], data=values[":data"])
        return {}

    def delete_item(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("delete", kwargs))
        key = decode(kwargs["Key"])["id"]
        values = decode(kwargs["ExpressionAttributeValues"])
        item = self.items[key]
        if not self._condition_matches_generation(item, kwargs, values):
            raise self._conditional_failure("DeleteItem")
        del self.items[key]
        return {}

    @staticmethod
    def _condition_matches_generation(
        item: dict[str, Any],
        request: dict[str, Any],
        values: dict[str, Any],
    ) -> bool:
        if ":pending" in values and item.get("status") != values[":pending"]:
            return False
        if ":hash" in values and item.get("validation") != values[":hash"]:
            return False
        condition = request.get("ConditionExpression", "")
        names = request.get("ExpressionAttributeNames", {})
        if names.get("#lease") == "in_progress_expiration" and "#lease" in condition:
            expected = values.get(":lease", values.get(":old_lease"))
            if (
                not isinstance(expected, (int, Decimal))
                or item.get("in_progress_expiration") != expected
            ):
                return False
        if "#expiration" in condition and ":now" in values:
            expiration = item.get("expiration")
            if not isinstance(expiration, (int, Decimal)) or expiration < values[":now"]:
                return False
        return True

    @staticmethod
    def _conditional_failure(operation: str) -> ClientError:
        return ClientError(
            {"Error": {"Code": "ConditionalCheckFailedException"}},
            operation,
        )


def acquire(
    target: StudentLifecycleIdempotency,
    *,
    operation: LifecycleOperation = "deactivate-student",
    payload: dict[str, str | int] | None = None,
    actor: str = "actor-1",
) -> Any:
    return target.acquire(
        operation=operation,
        environment="dev",
        actor_id=actor,
        idempotency_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        student_id="student-1",
        payload=payload or {"expectedVersion": 3, "reason": REASON},
    )


def test_scoped_claim_has_24_hour_ttl_and_stores_no_reason() -> None:
    client = Client()
    record = acquire(StudentLifecycleIdempotency(client, "idempotency", clock=lambda: 1000))
    item = client.items[record.idempotency_id]

    assert record.idempotency_id.startswith("deactivate-student#")
    assert item == {
        "id": record.idempotency_id,
        "status": "INPROGRESS",
        "expiration": 87400,
        "in_progress_expiration": 1060000,
        "validation": record.request_hash,
    }
    assert REASON not in str(item)
    assert getattr(record, "in_progress_expiration", None) == 1060000


def test_hash_is_canonical_and_changes_with_semantic_request() -> None:
    first = acquire(
        StudentLifecycleIdempotency(Client(), "idempotency"),
        payload={"reason": REASON, "expectedVersion": 3},
    )
    reordered = acquire(
        StudentLifecycleIdempotency(Client(), "idempotency"),
        payload={"expectedVersion": 3, "reason": REASON},
    )
    changed = acquire(
        StudentLifecycleIdempotency(Client(), "idempotency"),
        payload={"expectedVersion": 4, "reason": REASON},
    )
    assert first.request_hash == reordered.request_hash
    assert changed.request_hash != first.request_hash


def test_operation_and_actor_scope_identities() -> None:
    baseline = acquire(StudentLifecycleIdempotency(Client(), "idempotency"))
    actor = acquire(StudentLifecycleIdempotency(Client(), "idempotency"), actor="actor-2")
    reactivate = acquire(
        StudentLifecycleIdempotency(Client(), "idempotency"),
        operation="reactivate-student",
        payload={"expectedVersion": 3},
    )
    assert len({baseline.idempotency_id, actor.idempotency_id, reactivate.idempotency_id}) == 3
    assert reactivate.request_hash != baseline.request_hash


def test_completed_claim_replays_exact_public_response_consistently() -> None:
    client = Client()
    target = StudentLifecycleIdempotency(client, "idempotency")
    record = acquire(target)
    client.items[record.idempotency_id].update(status="COMPLETED", data=json.dumps(RESPONSE))

    assert acquire(target).response == RESPONSE
    get = next(call for name, call in client.calls if name == "get")
    assert get["ConsistentRead"] is True


def test_same_key_different_request_uses_canonical_conflict() -> None:
    client = Client()
    target = StudentLifecycleIdempotency(client, "idempotency")
    acquire(target)
    with pytest.raises(IdempotencyKeyReusedError):
        acquire(target, payload={"expectedVersion": 3, "reason": "Outro motivo seguro"})


def test_matching_live_inprogress_uses_canonical_inprogress_error() -> None:
    client = Client()
    acquire(StudentLifecycleIdempotency(client, "idempotency", clock=lambda: 1000))
    with pytest.raises(OperationInProgressError):
        acquire(StudentLifecycleIdempotency(client, "idempotency", clock=lambda: 1059))


def test_expired_matching_inprogress_is_reclaimed_with_monotonic_lease() -> None:
    client = Client()
    first = acquire(StudentLifecycleIdempotency(client, "idempotency", clock=lambda: 1000))
    old_lease = client.items[first.idempotency_id]["in_progress_expiration"]

    reclaimed = acquire(StudentLifecycleIdempotency(client, "idempotency", clock=lambda: 1061))

    expected = max(1_121_000, old_lease + 1)
    assert getattr(reclaimed, "in_progress_expiration", None) == expected
    assert client.items[first.idempotency_id]["in_progress_expiration"] == expected


@pytest.mark.parametrize("winner", ["completed", "live", "impossible"])
def test_lost_reclaim_cas_rereads_and_classifies_winner(winner: str) -> None:
    class ReclaimRaceClient(Client):
        def update_item(self, **kwargs: Any) -> dict[str, Any]:
            values = decode(kwargs["ExpressionAttributeValues"])
            if ":new_lease" not in values:
                return super().update_item(**kwargs)
            self.calls.append(("update", kwargs))
            key = decode(kwargs["Key"])["id"]
            item = self.items[key]
            if winner == "completed":
                item.update(status="COMPLETED", data=json.dumps(RESPONSE))
            elif winner == "live":
                item["in_progress_expiration"] = values[":new_lease"] + 1
            else:
                item["status"] = "FAILED"
            raise self._conditional_failure("UpdateItem")

    client = ReclaimRaceClient()
    first = acquire(StudentLifecycleIdempotency(client, "idempotency", clock=lambda: 1000))
    target = StudentLifecycleIdempotency(client, "idempotency", clock=lambda: 1061)

    if winner == "completed":
        assert acquire(target).response == RESPONSE
    elif winner == "live":
        with pytest.raises(OperationInProgressError):
            acquire(target)
    else:
        with pytest.raises(StudentLifecycleInvariantError):
            acquire(target)

    assert len([call for name, call in client.calls if name == "update"]) == 1
    assert len([call for name, call in client.calls if name == "get"]) == 2
    assert first.idempotency_id in client.items


def test_noop_completion_is_conditional_and_replayable() -> None:
    client = Client()
    target = StudentLifecycleIdempotency(client, "idempotency")
    record = acquire(target)
    current = {**RESPONSE, "version": 3, "updatedAt": "2025-01-01T00:00:00.000Z"}

    assert target.complete_noop(record, current) == current
    assert acquire(target).response == current
    update = next(call for name, call in client.calls if name == "update")
    assert "#status = :pending" in update["ConditionExpression"]
    assert "#validation = :hash" in update["ConditionExpression"]
    assert update["ExpressionAttributeNames"]["#lease"] == "in_progress_expiration"
    assert "#lease = :lease" in update["ConditionExpression"]
    assert decode(update["ExpressionAttributeValues"])[":lease"] == getattr(
        record, "in_progress_expiration", None
    )


def test_uncertain_noop_resolves_completed_or_reports_inprogress() -> None:
    client = Client()
    target = StudentLifecycleIdempotency(client, "idempotency")
    record = acquire(target)
    client.items[record.idempotency_id].update(status="COMPLETED", data=json.dumps(RESPONSE))
    client.fail_update = TimeoutError()
    assert target.complete_noop(record, RESPONSE) == RESPONSE

    second_client = Client()
    second = StudentLifecycleIdempotency(second_client, "idempotency")
    second_record = acquire(second)
    second_client.fail_update = TimeoutError()
    with pytest.raises(OperationInProgressError):
        second.complete_noop(second_record, RESPONSE)


def test_release_deletes_only_matching_claim() -> None:
    client = Client()
    target = StudentLifecycleIdempotency(client, "idempotency")
    record = acquire(target)
    target.release(record)
    assert record.idempotency_id not in client.items
    delete = next(call for name, call in client.calls if name == "delete")
    assert delete["ExpressionAttributeNames"]["#lease"] == "in_progress_expiration"
    assert "#lease = :lease" in delete["ConditionExpression"]
    assert decode(delete["ExpressionAttributeValues"])[":lease"] == getattr(
        record, "in_progress_expiration", None
    )


def test_stale_worker_cannot_release_reclaimed_generation() -> None:
    client = Client()
    target = StudentLifecycleIdempotency(client, "idempotency", clock=lambda: 1000)
    stale = acquire(target)
    item = client.items[stale.idempotency_id]
    item["in_progress_expiration"] += 61_000

    with pytest.raises(StudentLifecycleInvariantError):
        target.release(stale)

    assert client.items[stale.idempotency_id] is item
    assert item["status"] == "INPROGRESS"


def test_stale_worker_cannot_complete_noop_after_reclaim() -> None:
    client = Client()
    target = StudentLifecycleIdempotency(client, "idempotency", clock=lambda: 1000)
    stale = acquire(target)
    item = client.items[stale.idempotency_id]
    item["in_progress_expiration"] += 61_000

    with pytest.raises(StudentLifecycleInvariantError):
        target.complete_noop(stale, RESPONSE)

    assert item["status"] == "INPROGRESS"
    assert "data" not in item


def test_release_rejects_operation_identity_mismatch_without_delete() -> None:
    client = Client()
    target = StudentLifecycleIdempotency(client, "idempotency")
    record = acquire(target)
    mismatched = type(record)("reactivate-student", record.idempotency_id, record.request_hash)
    with pytest.raises(StudentLifecycleInvariantError):
        target.release(mismatched)
    assert record.idempotency_id in client.items
    assert not any(name == "delete" for name, _ in client.calls)


def test_transport_failure_is_unresolved() -> None:
    client = Client()
    client.fail_put = TimeoutError()
    with pytest.raises(StudentLifecycleUnresolvedError):
        acquire(StudentLifecycleIdempotency(client, "idempotency"))


def test_impossible_persisted_state_is_invariant() -> None:
    client = Client()
    target = StudentLifecycleIdempotency(client, "idempotency")
    record = acquire(target)
    client.items[record.idempotency_id]["status"] = "FAILED"
    with pytest.raises(StudentLifecycleInvariantError):
        target.resolve(record)
