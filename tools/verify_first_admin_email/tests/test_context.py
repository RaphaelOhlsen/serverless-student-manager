import pytest

from tools.verify_first_admin_email.context import (
    InvalidVerifyFirstAdminEmailRecordError,
    VerifyFirstAdminEmailContext,
    parse_verify_first_admin_email_context,
)
from tools.verify_first_admin_email.idempotency import (
    build_verify_first_admin_email_started_record,
)

_OPERATION_ID = "123e4567-e89b-42d3-a456-426614174000"
_EVENT_ID = "323e4567-e89b-42d3-a456-426614174002"
_CORRELATION_ID = "223e4567-e89b-42d3-a456-426614174001"
_OCCURRED_AT = "2026-08-28T17:10:00.000Z"
_AUDIT_EXPIRES_AT = 1_785_252_200


def _record() -> dict[str, object]:
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


def test_parse_context_maps_canonical_record() -> None:
    context = parse_verify_first_admin_email_context(
        _record(),
        expected_environment="dev",
        expected_operation_id=_OPERATION_ID,
    )

    assert context == VerifyFirstAdminEmailContext(
        record_id=(f"NONHTTP#dev#verify-first-admin-email#first-admin#{_OPERATION_ID}"),
        environment="dev",
        operation="verify-first-admin-email",
        target="first-admin",
        operation_id=_OPERATION_ID,
        payload_hash=("1e79147440f3071256d852615a858fa0b107398317c8a739f5f4d386ed2b135a"),
        state="STARTED",
        event_id=_EVENT_ID,
        correlation_id=_CORRELATION_ID,
        occurred_at=_OCCURRED_AT,
        audit_expires_at=_AUDIT_EXPIRES_AT,
        actor_id="github:raphael",
        created_at=_OCCURRED_AT,
        updated_at=_OCCURRED_AT,
        expiration=1_777_258_712,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("environment", "prod"),
        ("operation", "bootstrap-admin"),
        ("target", "other-target"),
        ("operationId", "323e4567-e89b-42d3-a456-426614174002"),
        ("state", "UNKNOWN"),
    ],
)
def test_parse_context_rejects_incompatible_record(
    field: str,
    value: object,
) -> None:
    record = _record()
    record[field] = value

    with pytest.raises(InvalidVerifyFirstAdminEmailRecordError):
        parse_verify_first_admin_email_context(
            record,
            expected_environment="dev",
            expected_operation_id=_OPERATION_ID,
        )


def test_parse_context_rejects_incompatible_record_id() -> None:
    record = _record()
    record["id"] = "NONHTTP#dev#verify-first-admin-email#other-target#invalid"

    with pytest.raises(InvalidVerifyFirstAdminEmailRecordError):
        parse_verify_first_admin_email_context(
            record,
            expected_environment="dev",
            expected_operation_id=_OPERATION_ID,
        )


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "environment",
        "operation",
        "target",
        "operationId",
        "payloadHash",
        "state",
        "eventId",
        "correlationId",
        "occurredAt",
        "auditExpiresAt",
        "actorId",
        "createdAt",
        "updatedAt",
        "expiration",
    ],
)
def test_parse_context_rejects_missing_required_field(field: str) -> None:
    record = _record()
    del record[field]

    with pytest.raises(InvalidVerifyFirstAdminEmailRecordError):
        parse_verify_first_admin_email_context(
            record,
            expected_environment="dev",
            expected_operation_id=_OPERATION_ID,
        )


@pytest.mark.parametrize("field", ["eventId", "correlationId"])
def test_parse_context_rejects_invalid_deterministic_uuid(field: str) -> None:
    record = _record()
    record[field] = "not-a-uuid"

    with pytest.raises(InvalidVerifyFirstAdminEmailRecordError, match=field):
        parse_verify_first_admin_email_context(
            record,
            expected_environment="dev",
            expected_operation_id=_OPERATION_ID,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("eventId", 123),
        ("correlationId", 123),
        ("occurredAt", 123),
        ("auditExpiresAt", "1785252200"),
        ("actorId", 123),
    ],
)
def test_parse_context_rejects_invalid_deterministic_metadata_type(
    field: str,
    value: object,
) -> None:
    record = _record()
    record[field] = value

    with pytest.raises(InvalidVerifyFirstAdminEmailRecordError, match=field):
        parse_verify_first_admin_email_context(
            record,
            expected_environment="dev",
            expected_operation_id=_OPERATION_ID,
        )


@pytest.mark.parametrize(
    "occurred_at",
    [
        "2026-08-28T17:10:00Z",
        "2026-08-28 17:10:00.000Z",
        "2026-08-28T17:10:00.000+00:00",
        "2026-02-30T17:10:00.000Z",
    ],
)
def test_parse_context_rejects_invalid_occurred_at_format(occurred_at: str) -> None:
    record = _record()
    record["occurredAt"] = occurred_at

    with pytest.raises(InvalidVerifyFirstAdminEmailRecordError, match="occurredAt"):
        parse_verify_first_admin_email_context(
            record,
            expected_environment="dev",
            expected_operation_id=_OPERATION_ID,
        )


def test_parse_context_rejects_bool_audit_expiration() -> None:
    record = _record()
    record["auditExpiresAt"] = True

    with pytest.raises(InvalidVerifyFirstAdminEmailRecordError, match="auditExpiresAt"):
        parse_verify_first_admin_email_context(
            record,
            expected_environment="dev",
            expected_operation_id=_OPERATION_ID,
        )
