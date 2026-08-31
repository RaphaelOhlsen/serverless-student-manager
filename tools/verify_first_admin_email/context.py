import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from tools.bootstrap_admin.ids import validate_uuid4

VerifyFirstAdminEmailState = Literal[
    "STARTED",
    "COMPLETED",
    "RECONCILIATION_REQUIRED",
]

_VERIFY_FIRST_ADMIN_EMAIL_STATES = frozenset(
    {
        "STARTED",
        "COMPLETED",
        "RECONCILIATION_REQUIRED",
    }
)
_UTC_RFC3339_MILLIS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


@dataclass(frozen=True)
class VerifyFirstAdminEmailContext:
    record_id: str
    environment: str
    operation: str
    target: str
    operation_id: str
    payload_hash: str
    state: VerifyFirstAdminEmailState
    event_id: str
    correlation_id: str
    occurred_at: str
    audit_expires_at: int
    actor_id: str
    created_at: str
    updated_at: str
    expiration: int


class InvalidVerifyFirstAdminEmailRecordError(ValueError):
    pass


def parse_verify_first_admin_email_context(
    record: dict[str, object],
    *,
    expected_environment: str,
    expected_operation_id: str,
) -> VerifyFirstAdminEmailContext:
    record_id = _required_string(record, "id")
    environment = _required_string(record, "environment")
    operation = _required_string(record, "operation")
    target = _required_string(record, "target")
    operation_id = _required_uuid(record, "operationId")
    payload_hash = _required_string(record, "payloadHash")
    state_value = _required_string(record, "state")
    event_id = _required_uuid(record, "eventId")
    correlation_id = _required_uuid(record, "correlationId")
    occurred_at = _required_utc_rfc3339_millis(record, "occurredAt")
    audit_expires_at = _required_integer(record, "auditExpiresAt")
    actor_id = _required_string(record, "actorId")
    created_at = _required_string(record, "createdAt")
    updated_at = _required_string(record, "updatedAt")
    expiration = _required_integer(record, "expiration")

    if environment != expected_environment:
        raise InvalidVerifyFirstAdminEmailRecordError(
            "verify first admin email record environment is incompatible"
        )
    if operation != "verify-first-admin-email":
        raise InvalidVerifyFirstAdminEmailRecordError(
            "verify first admin email record operation is incompatible"
        )
    if target != "first-admin":
        raise InvalidVerifyFirstAdminEmailRecordError(
            "verify first admin email record target is incompatible"
        )
    if operation_id != expected_operation_id:
        raise InvalidVerifyFirstAdminEmailRecordError(
            "verify first admin email record operationId is incompatible"
        )
    if state_value not in _VERIFY_FIRST_ADMIN_EMAIL_STATES:
        raise InvalidVerifyFirstAdminEmailRecordError(
            "verify first admin email record state is unknown"
        )

    expected_record_id = (
        f"NONHTTP#{environment}#verify-first-admin-email#first-admin#{operation_id}"
    )
    if record_id != expected_record_id:
        raise InvalidVerifyFirstAdminEmailRecordError(
            "verify first admin email record id is incompatible"
        )

    return VerifyFirstAdminEmailContext(
        record_id=record_id,
        environment=environment,
        operation=operation,
        target=target,
        operation_id=operation_id,
        payload_hash=payload_hash,
        state=cast(VerifyFirstAdminEmailState, state_value),
        event_id=event_id,
        correlation_id=correlation_id,
        occurred_at=occurred_at,
        audit_expires_at=audit_expires_at,
        actor_id=actor_id,
        created_at=created_at,
        updated_at=updated_at,
        expiration=expiration,
    )


def _required_string(record: dict[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or value == "":
        raise InvalidVerifyFirstAdminEmailRecordError(
            f"verify first admin email record field {field} must be a non-empty string"
        )
    return value


def _required_integer(record: dict[str, object], field: str) -> int:
    value = record.get(field)
    if type(value) is not int:
        raise InvalidVerifyFirstAdminEmailRecordError(
            f"verify first admin email record field {field} must be an integer"
        )
    return value


def _required_uuid(record: dict[str, object], field: str) -> str:
    value = _required_string(record, field)
    try:
        return validate_uuid4(value)
    except ValueError:
        raise InvalidVerifyFirstAdminEmailRecordError(
            f"verify first admin email record field {field} must be a canonical UUIDv4"
        ) from None


def _required_utc_rfc3339_millis(record: dict[str, object], field: str) -> str:
    value = _required_string(record, field)
    if _UTC_RFC3339_MILLIS_PATTERN.fullmatch(value) is None:
        raise InvalidVerifyFirstAdminEmailRecordError(
            f"verify first admin email record field {field} "
            "must be UTC RFC3339 with millisecond precision"
        )
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        raise InvalidVerifyFirstAdminEmailRecordError(
            f"verify first admin email record field {field} "
            "must be UTC RFC3339 with millisecond precision"
        ) from None
    return value
