from copy import deepcopy

import pytest

from tools.bootstrap_admin.context import (
    BootstrapContext,
    InvalidBootstrapRecordError,
    parse_bootstrap_context,
)

_OPERATION_ID = "123e4567-e89b-42d3-a456-426614174000"
_USER_ID = "223e4567-e89b-42d3-a456-426614174001"
_EVENT_ID = "323e4567-e89b-42d3-a456-426614174002"
_CORRELATION_ID = "423e4567-e89b-42d3-a456-426614174003"


def _record(
    *,
    state: str = "STARTED",
    cognito_sub: str | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "id": f"NONHTTP#dev#bootstrap-admin#first-admin#{_OPERATION_ID}",
        "environment": "dev",
        "operation": "bootstrap-admin",
        "target": "first-admin",
        "operationId": _OPERATION_ID,
        "payloadHash": "payload-hash",
        "state": state,
        "userId": _USER_ID,
        "eventId": _EVENT_ID,
        "correlationId": _CORRELATION_ID,
        "occurredAt": "2026-08-20T13:45:12.347Z",
        "auditExpiresAt": 1_787_243_112,
        "actorId": "github:raphael",
        "createdAt": "2026-08-20T13:45:12.347Z",
        "updatedAt": "2026-08-20T13:45:12.347Z",
        "expiration": 1_777_258_712,
    }
    if cognito_sub is not None:
        record["cognitoSub"] = cognito_sub
    return record


def _parse(record: dict[str, object]) -> BootstrapContext:
    return parse_bootstrap_context(
        record,
        expected_environment="dev",
        expected_operation_id=_OPERATION_ID,
    )


def test_parse_started_record_without_cognito_sub_maps_all_fields() -> None:
    context = _parse(_record())

    assert context == BootstrapContext(
        record_id=f"NONHTTP#dev#bootstrap-admin#first-admin#{_OPERATION_ID}",
        environment="dev",
        operation="bootstrap-admin",
        target="first-admin",
        operation_id=_OPERATION_ID,
        payload_hash="payload-hash",
        state="STARTED",
        user_id=_USER_ID,
        event_id=_EVENT_ID,
        correlation_id=_CORRELATION_ID,
        occurred_at="2026-08-20T13:45:12.347Z",
        audit_expires_at=1_787_243_112,
        actor_id="github:raphael",
        created_at="2026-08-20T13:45:12.347Z",
        updated_at="2026-08-20T13:45:12.347Z",
        expiration=1_777_258_712,
        cognito_sub=None,
    )


def test_parse_cognito_created_record_with_cognito_sub() -> None:
    context = _parse(_record(state="COGNITO_CREATED", cognito_sub="sub-123"))

    assert context.state == "COGNITO_CREATED"
    assert context.cognito_sub == "sub-123"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("environment", "prod"),
        ("operation", "another-operation"),
        ("target", "another-target"),
        ("operationId", "523e4567-e89b-42d3-a456-426614174004"),
        ("operationId", "invalid-uuid"),
        ("userId", "invalid-uuid"),
        ("eventId", "invalid-uuid"),
        ("correlationId", "invalid-uuid"),
        ("id", "NONHTTP#dev#bootstrap-admin#first-admin#wrong"),
        ("state", "UNKNOWN"),
    ],
)
def test_parse_rejects_incompatible_identity_or_state(field: str, value: object) -> None:
    record = _record()
    record[field] = value

    with pytest.raises(InvalidBootstrapRecordError):
        _parse(record)


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
        "userId",
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
def test_parse_rejects_missing_required_field(field: str) -> None:
    record = _record()
    del record[field]

    with pytest.raises(InvalidBootstrapRecordError):
        _parse(record)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", 123),
        ("payloadHash", ""),
        ("occurredAt", ""),
        ("createdAt", ""),
        ("updatedAt", ""),
        ("actorId", ""),
        ("auditExpiresAt", "1779"),
        ("expiration", False),
    ],
)
def test_parse_rejects_incorrect_type_or_empty_required_string(
    field: str,
    value: object,
) -> None:
    record = _record()
    record[field] = value

    with pytest.raises(InvalidBootstrapRecordError):
        _parse(record)


@pytest.mark.parametrize(
    "state",
    [
        "COGNITO_CREATED",
        "PERSISTENCE_COMPLETED",
        "INVITATION_SENT",
        "COMPLETED",
        "COMPENSATED",
    ],
)
def test_parse_requires_cognito_sub_after_cognito_creation(state: str) -> None:
    with pytest.raises(InvalidBootstrapRecordError, match="cognitoSub"):
        _parse(_record(state=state))


def test_parse_accepts_reconciliation_required_without_cognito_sub() -> None:
    context = _parse(_record(state="RECONCILIATION_REQUIRED"))

    assert context.cognito_sub is None


def test_parse_rejects_empty_cognito_sub_when_present() -> None:
    record = deepcopy(_record())
    record["cognitoSub"] = ""

    with pytest.raises(InvalidBootstrapRecordError, match="cognitoSub"):
        _parse(record)
