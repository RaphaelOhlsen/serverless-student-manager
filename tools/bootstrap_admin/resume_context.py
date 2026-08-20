from dataclasses import dataclass
from typing import Literal, cast

from tools.bootstrap_admin.ids import validate_uuid4

ResumeInvitationState = Literal[
    "STARTED",
    "COMPLETED",
    "RECONCILIATION_REQUIRED",
]

_RESUME_INVITATION_STATES = frozenset(
    {
        "STARTED",
        "COMPLETED",
        "RECONCILIATION_REQUIRED",
    }
)


@dataclass(frozen=True)
class ResumeInvitationContext:
    record_id: str
    environment: str
    operation: str
    target: str
    operation_id: str
    payload_hash: str
    state: ResumeInvitationState
    correlation_id: str
    actor_id: str
    created_at: str
    updated_at: str
    expiration: int


class InvalidResumeInvitationRecordError(ValueError):
    pass


def parse_resume_invitation_context(
    record: dict[str, object],
    *,
    expected_environment: str,
    expected_operation_id: str,
) -> ResumeInvitationContext:
    record_id = _required_string(record, "id")
    environment = _required_string(record, "environment")
    operation = _required_string(record, "operation")
    target = _required_string(record, "target")
    operation_id = _required_uuid(record, "operationId")
    payload_hash = _required_string(record, "payloadHash")
    state_value = _required_string(record, "state")
    correlation_id = _required_uuid(record, "correlationId")
    actor_id = _required_string(record, "actorId")
    created_at = _required_string(record, "createdAt")
    updated_at = _required_string(record, "updatedAt")
    expiration = _required_integer(record, "expiration")

    if environment != expected_environment:
        raise InvalidResumeInvitationRecordError(
            "resume invitation record environment is incompatible"
        )
    if operation != "resume-first-admin-invitation":
        raise InvalidResumeInvitationRecordError(
            "resume invitation record operation is incompatible"
        )
    if target != "first-admin":
        raise InvalidResumeInvitationRecordError(
            "resume invitation record target is incompatible"
        )
    if operation_id != expected_operation_id:
        raise InvalidResumeInvitationRecordError(
            "resume invitation record operationId is incompatible"
        )
    if state_value not in _RESUME_INVITATION_STATES:
        raise InvalidResumeInvitationRecordError(
            "resume invitation record state is unknown"
        )

    expected_record_id = (
        f"NONHTTP#{environment}#resume-first-admin-invitation#first-admin#"
        f"{operation_id}"
    )
    if record_id != expected_record_id:
        raise InvalidResumeInvitationRecordError(
            "resume invitation record id is incompatible"
        )

    return ResumeInvitationContext(
        record_id=record_id,
        environment=environment,
        operation=operation,
        target=target,
        operation_id=operation_id,
        payload_hash=payload_hash,
        state=cast(ResumeInvitationState, state_value),
        correlation_id=correlation_id,
        actor_id=actor_id,
        created_at=created_at,
        updated_at=updated_at,
        expiration=expiration,
    )


def _required_string(record: dict[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or value == "":
        raise InvalidResumeInvitationRecordError(
            f"resume invitation record field {field} must be a non-empty string"
        )
    return value


def _required_integer(record: dict[str, object], field: str) -> int:
    value = record.get(field)
    if type(value) is not int:
        raise InvalidResumeInvitationRecordError(
            f"resume invitation record field {field} must be an integer"
        )
    return value


def _required_uuid(record: dict[str, object], field: str) -> str:
    value = _required_string(record, field)
    try:
        return validate_uuid4(value)
    except ValueError:
        raise InvalidResumeInvitationRecordError(
            f"resume invitation record field {field} must be a canonical UUIDv4"
        ) from None
