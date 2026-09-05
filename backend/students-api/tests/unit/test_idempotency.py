from typing import Any

import pytest
from aws_lambda_powertools.utilities.idempotency import BasePersistenceLayer
from aws_lambda_powertools.utilities.idempotency.exceptions import (
    IdempotencyItemAlreadyExistsError,
    IdempotencyItemNotFoundError,
)
from aws_lambda_powertools.utilities.idempotency.persistence.datarecord import DataRecord
from students_api.errors import IdempotencyKeyReusedError, OperationInProgressError
from students_api.idempotency import CreateStudentIdempotency


class MemoryPersistence(BasePersistenceLayer):
    def __init__(self) -> None:
        super().__init__()  # type: ignore[no-untyped-call]
        self.records: dict[str, DataRecord] = {}

    def _get_record(self, idempotency_key: str) -> DataRecord:
        if idempotency_key not in self.records:
            raise IdempotencyItemNotFoundError
        return self.records[idempotency_key]

    def _put_record(self, data_record: DataRecord) -> None:
        existing = self.records.get(data_record.idempotency_key)
        if existing is not None:
            self._validate_payload(data_payload=data_record, stored_data_record=existing)
            raise IdempotencyItemAlreadyExistsError(old_data_record=existing)
        self.records[data_record.idempotency_key] = data_record

    def _update_record(self, data_record: DataRecord) -> None:
        self.records[data_record.idempotency_key] = data_record

    def _delete_record(self, data_record: DataRecord) -> None:
        self.records.pop(data_record.idempotency_key, None)


def data(payload: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "environment": "dev",
        "actorId": "user-1",
        "operation": "create-student",
        "idempotencyKey": "11111111-1111-4111-8111-111111111111",
        "payload": payload or {"registrationNumber": "MAT-1"},
    }


def test_replays_completed_response_with_integer_types() -> None:
    idempotency = CreateStudentIdempotency(MemoryPersistence())
    calls = 0

    def action() -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"studentId": "student-1", "version": 1}

    first = idempotency.execute(data=data(), action=action)
    second = idempotency.execute(data=data(), action=action)

    assert first == second == {"studentId": "student-1", "version": 1}
    assert type(second["version"]) is int
    assert calls == 1


def test_rejects_same_key_with_different_normalized_payload() -> None:
    idempotency = CreateStudentIdempotency(MemoryPersistence())
    idempotency.execute(data=data(), action=lambda: {"version": 1})

    with pytest.raises(IdempotencyKeyReusedError):
        idempotency.execute(
            data=data({"registrationNumber": "MAT-2"}),
            action=lambda: {"version": 1},
        )


def test_reports_concurrent_operation() -> None:
    idempotency = CreateStudentIdempotency(MemoryPersistence())

    def action() -> dict[str, object]:
        with pytest.raises(OperationInProgressError):
            idempotency.execute(data=data(), action=lambda: {"version": 2})
        return {"version": 1}

    assert idempotency.execute(data=data(), action=action) == {"version": 1}


def test_transient_failure_removes_inprogress_and_allows_retry() -> None:
    idempotency = CreateStudentIdempotency(MemoryPersistence())

    with pytest.raises(RuntimeError):
        idempotency.execute(data=data(), action=lambda: (_ for _ in ()).throw(RuntimeError()))

    assert idempotency.execute(data=data(), action=lambda: {"version": 1}) == {"version": 1}
