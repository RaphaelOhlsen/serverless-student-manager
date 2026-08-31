import pytest

from tools.bootstrap_admin.idempotency import IdempotencyConflictError
from tools.verify_first_admin_email.idempotency import (
    build_verify_first_admin_email_started_record,
    validate_verify_first_admin_email_existing_record,
    verify_first_admin_email_payload_hash,
)

_OPERATION_ID = "123e4567-e89b-42d3-a456-426614174000"
_EVENT_ID = "323e4567-e89b-42d3-a456-426614174002"
_CORRELATION_ID = "223e4567-e89b-42d3-a456-426614174001"
_OCCURRED_AT = "2026-08-28T17:10:00.000Z"
_AUDIT_EXPIRES_AT = 1_785_252_200
_EXPECTED_PAYLOAD_HASH = "1e79147440f3071256d852615a858fa0b107398317c8a739f5f4d386ed2b135a"


def _build_started_record() -> dict[str, object]:
    return build_verify_first_admin_email_started_record(
        environment="dev",
        operation_id=_OPERATION_ID,
        event_id=_EVENT_ID,
        correlation_id=_CORRELATION_ID,
        actor_id="github:raphael",
        occurred_at=_OCCURRED_AT,
        audit_expires_at=_AUDIT_EXPIRES_AT,
        created_at=_OCCURRED_AT,
        expiration=1_777_258_712,
    )


def test_payload_hash_matches_canonical_target_contract() -> None:
    assert verify_first_admin_email_payload_hash() == _EXPECTED_PAYLOAD_HASH


def test_started_record_matches_exact_schema() -> None:
    record = _build_started_record()

    assert record == {
        "id": (f"NONHTTP#dev#verify-first-admin-email#first-admin#{_OPERATION_ID}"),
        "environment": "dev",
        "operation": "verify-first-admin-email",
        "target": "first-admin",
        "operationId": _OPERATION_ID,
        "payloadHash": _EXPECTED_PAYLOAD_HASH,
        "state": "STARTED",
        "eventId": _EVENT_ID,
        "correlationId": _CORRELATION_ID,
        "occurredAt": _OCCURRED_AT,
        "auditExpiresAt": _AUDIT_EXPIRES_AT,
        "actorId": "github:raphael",
        "createdAt": _OCCURRED_AT,
        "updatedAt": _OCCURRED_AT,
        "expiration": 1_777_258_712,
    }


def test_started_record_excludes_pii_and_identity_fields() -> None:
    record = _build_started_record()

    forbidden_fields = {
        "email",
        "normalizedEmail",
        "fullName",
        "userId",
        "cognitoSub",
        "username",
    }

    assert forbidden_fields.isdisjoint(record)


def test_validate_existing_record_accepts_canonical_payload() -> None:
    validate_verify_first_admin_email_existing_record(_build_started_record())


def test_validate_existing_record_rejects_payload_mismatch() -> None:
    record = _build_started_record()
    record["payloadHash"] = "different-payload-hash"

    with pytest.raises(IdempotencyConflictError):
        validate_verify_first_admin_email_existing_record(record)


def test_started_record_rebuild_preserves_deterministic_metadata() -> None:
    original = _build_started_record()
    replay = _build_started_record()

    assert replay == original
    assert replay["eventId"] == _EVENT_ID
    assert replay["correlationId"] == _CORRELATION_ID
    assert replay["occurredAt"] == _OCCURRED_AT
    assert replay["auditExpiresAt"] == _AUDIT_EXPIRES_AT
    assert replay["actorId"] == "github:raphael"
