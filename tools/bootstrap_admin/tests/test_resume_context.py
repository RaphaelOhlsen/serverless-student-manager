from dataclasses import FrozenInstanceError

import pytest

from tools.bootstrap_admin.resume_context import (
    InvalidResumeInvitationRecordError,
    ResumeInvitationContext,
    parse_resume_invitation_context,
)
from tools.bootstrap_admin.service_models import ResumeInvitationResult

_OPERATION_ID = "123e4567-e89b-42d3-a456-426614174000"
_CORRELATION_ID = "223e4567-e89b-42d3-a456-426614174001"


def _record(*, state: str = "STARTED") -> dict[str, object]:
    return {
        "id": (
            "NONHTTP#dev#resume-first-admin-invitation#first-admin#"
            f"{_OPERATION_ID}"
        ),
        "environment": "dev",
        "operation": "resume-first-admin-invitation",
        "target": "first-admin",
        "operationId": _OPERATION_ID,
        "payloadHash": "payload-hash",
        "state": state,
        "correlationId": _CORRELATION_ID,
        "actorId": "github:raphael",
        "createdAt": "2026-08-20T13:45:12.347Z",
        "updatedAt": "2026-08-20T13:45:12.347Z",
        "expiration": 1_777_258_712,
    }


def _parse(record: dict[str, object]) -> ResumeInvitationContext:
    return parse_resume_invitation_context(
        record,
        expected_environment="dev",
        expected_operation_id=_OPERATION_ID,
    )


@pytest.mark.parametrize(
    "state",
    ["STARTED", "COMPLETED", "RECONCILIATION_REQUIRED"],
)
def test_parse_resume_invitation_context_accepts_approved_states(state: str) -> None:
    context = _parse(_record(state=state))

    assert context == ResumeInvitationContext(
        record_id=(
            "NONHTTP#dev#resume-first-admin-invitation#first-admin#"
            f"{_OPERATION_ID}"
        ),
        environment="dev",
        operation="resume-first-admin-invitation",
        target="first-admin",
        operation_id=_OPERATION_ID,
        payload_hash="payload-hash",
        state=state,  # type: ignore[arg-type]
        correlation_id=_CORRELATION_ID,
        actor_id="github:raphael",
        created_at="2026-08-20T13:45:12.347Z",
        updated_at="2026-08-20T13:45:12.347Z",
        expiration=1_777_258_712,
    )


def test_parse_resume_invitation_context_accepts_unknown_extra_attribute() -> None:
    record = _record()
    record["futureAttribute"] = "future-value"

    context = _parse(record)

    assert context.operation_id == _OPERATION_ID
    assert context.state == "STARTED"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operation", "bootstrap-admin"),
        ("target", "another-target"),
        ("environment", "prod"),
        ("operationId", "323e4567-e89b-42d3-a456-426614174002"),
        ("operationId", "not-a-uuid"),
        ("correlationId", "not-a-uuid"),
        ("state", "INVITATION_SENT"),
        ("id", "NONHTTP#dev#resume-first-admin-invitation#first-admin#wrong"),
    ],
)
def test_parse_resume_invitation_context_rejects_incompatible_identity_or_state(
    field: str,
    value: object,
) -> None:
    record = _record()
    record[field] = value

    with pytest.raises(InvalidResumeInvitationRecordError):
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
        "correlationId",
        "actorId",
        "createdAt",
        "updatedAt",
        "expiration",
    ],
)
def test_parse_resume_invitation_context_rejects_missing_required_field(
    field: str,
) -> None:
    record = _record()
    del record[field]

    with pytest.raises(InvalidResumeInvitationRecordError):
        _parse(record)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", 123),
        ("environment", ""),
        ("operation", ""),
        ("target", ""),
        ("operationId", ""),
        ("payloadHash", ""),
        ("state", ""),
        ("correlationId", ""),
        ("actorId", ""),
        ("createdAt", ""),
        ("updatedAt", ""),
        ("expiration", "1777258712"),
        ("expiration", False),
    ],
)
def test_parse_resume_invitation_context_rejects_invalid_type_or_empty_string(
    field: str,
    value: object,
) -> None:
    record = _record()
    record[field] = value

    with pytest.raises(InvalidResumeInvitationRecordError):
        _parse(record)


@pytest.mark.parametrize("state", ["COMPLETED", "RECONCILIATION_REQUIRED"])
def test_resume_invitation_result_accepts_terminal_states(state: str) -> None:
    result = ResumeInvitationResult(
        operation_id=_OPERATION_ID,
        state=state,  # type: ignore[arg-type]
        replayed=True,
    )

    assert result.state == state
    assert not hasattr(result, "user_id")


def test_resume_invitation_result_is_immutable() -> None:
    result = ResumeInvitationResult(
        operation_id=_OPERATION_ID,
        state="COMPLETED",
        replayed=False,
    )

    with pytest.raises(FrozenInstanceError):
        result.replayed = True  # type: ignore[misc]
