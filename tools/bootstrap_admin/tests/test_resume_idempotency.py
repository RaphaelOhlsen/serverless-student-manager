import pytest

from tools.bootstrap_admin.idempotency import (
    IdempotencyConflictError,
    is_valid_state_transition,
)
from tools.bootstrap_admin.resume_idempotency import (
    build_resume_invitation_started_record,
    resume_invitation_payload_hash,
    validate_resume_invitation_existing_record,
)

_OPERATION_ID = "123e4567-e89b-42d3-a456-426614174000"
_CORRELATION_ID = "223e4567-e89b-42d3-a456-426614174001"
_EXPECTED_PAYLOAD_HASH = "1e79147440f3071256d852615a858fa0b107398317c8a739f5f4d386ed2b135a"


def _build_started_record() -> dict[str, object]:
    return build_resume_invitation_started_record(
        environment="dev",
        operation_id=_OPERATION_ID,
        correlation_id=_CORRELATION_ID,
        actor_id="github:raphael",
        created_at="2026-08-20T13:45:12.347Z",
        expiration=1_777_258_712,
    )


def test_resume_invitation_payload_hash_matches_canonical_payload_contract() -> None:
    assert resume_invitation_payload_hash() == _EXPECTED_PAYLOAD_HASH


def test_resume_invitation_payload_hash_is_deterministic_and_has_no_inputs() -> None:
    assert resume_invitation_payload_hash() == resume_invitation_payload_hash()


def test_resume_invitation_started_record_matches_exact_schema() -> None:
    record = _build_started_record()

    assert record == {
        "id": (f"NONHTTP#dev#resume-first-admin-invitation#first-admin#{_OPERATION_ID}"),
        "environment": "dev",
        "operation": "resume-first-admin-invitation",
        "target": "first-admin",
        "operationId": _OPERATION_ID,
        "payloadHash": _EXPECTED_PAYLOAD_HASH,
        "state": "STARTED",
        "correlationId": _CORRELATION_ID,
        "actorId": "github:raphael",
        "createdAt": "2026-08-20T13:45:12.347Z",
        "updatedAt": "2026-08-20T13:45:12.347Z",
        "expiration": 1_777_258_712,
    }
    assert set(record) == {
        "id",
        "environment",
        "operation",
        "target",
        "operationId",
        "payloadHash",
        "state",
        "correlationId",
        "actorId",
        "createdAt",
        "updatedAt",
        "expiration",
    }


def test_resume_invitation_started_record_excludes_forbidden_fields() -> None:
    record = _build_started_record()

    forbidden_fields = {
        "userId",
        "cognitoSub",
        "eventId",
        "occurredAt",
        "auditExpiresAt",
        "originalBootstrapOperationId",
        "fullName",
        "email",
    }
    assert forbidden_fields.isdisjoint(record)


def test_resume_invitation_started_record_preserves_expiration() -> None:
    record = _build_started_record()

    assert record["expiration"] == 1_777_258_712
    assert record["createdAt"] == record["updatedAt"]


def test_validate_resume_invitation_existing_record_accepts_canonical_payload() -> None:
    validate_resume_invitation_existing_record(_build_started_record())


def test_validate_resume_invitation_existing_record_rejects_payload_mismatch() -> None:
    record = _build_started_record()
    record["payloadHash"] = "different-payload-hash"

    with pytest.raises(IdempotencyConflictError):
        validate_resume_invitation_existing_record(record)


def test_resume_invitation_state_machine_accepts_only_approved_transitions() -> None:
    assert is_valid_state_transition(
        operation="resume-first-admin-invitation",
        current_state="STARTED",
        next_state="COMPLETED",
    )
    assert is_valid_state_transition(
        operation="resume-first-admin-invitation",
        current_state="STARTED",
        next_state="RECONCILIATION_REQUIRED",
    )


@pytest.mark.parametrize("next_state", ["INVITATION_SENT", "COMPENSATED"])
def test_resume_invitation_state_machine_rejects_bootstrap_states(
    next_state: str,
) -> None:
    assert not is_valid_state_transition(
        operation="resume-first-admin-invitation",
        current_state="STARTED",
        next_state=next_state,
    )


@pytest.mark.parametrize("state", ["COMPLETED", "RECONCILIATION_REQUIRED"])
def test_resume_invitation_terminal_states_do_not_advance(state: str) -> None:
    assert not is_valid_state_transition(
        operation="resume-first-admin-invitation",
        current_state=state,
        next_state="STARTED",
    )
