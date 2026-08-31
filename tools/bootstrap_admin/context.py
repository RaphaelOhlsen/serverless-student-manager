from dataclasses import dataclass
from typing import Literal, cast

from tools.bootstrap_admin.ids import validate_uuid4

BootstrapState = Literal[
    "STARTED",
    "COGNITO_CREATED",
    "PERSISTENCE_COMPLETED",
    "INVITATION_SENT",
    "COMPLETED",
    "COMPENSATED",
    "RECONCILIATION_REQUIRED",
]

_BOOTSTRAP_STATES = frozenset(
    {
        "STARTED",
        "COGNITO_CREATED",
        "PERSISTENCE_COMPLETED",
        "INVITATION_SENT",
        "COMPLETED",
        "COMPENSATED",
        "RECONCILIATION_REQUIRED",
    }
)
_STATES_REQUIRING_COGNITO_SUB = frozenset(
    {
        "COGNITO_CREATED",
        "PERSISTENCE_COMPLETED",
        "INVITATION_SENT",
        "COMPLETED",
        "COMPENSATED",
    }
)


@dataclass(frozen=True)
class BootstrapContext:
    record_id: str
    environment: str
    operation: str
    target: str
    operation_id: str
    payload_hash: str
    state: BootstrapState
    user_id: str
    event_id: str
    correlation_id: str
    occurred_at: str
    audit_expires_at: int
    actor_id: str
    created_at: str
    updated_at: str
    expiration: int
    cognito_email_verified_required: bool
    cognito_sub: str | None


class InvalidBootstrapRecordError(ValueError):
    pass


def parse_bootstrap_context(
    record: dict[str, object],
    *,
    expected_environment: str,
    expected_operation_id: str,
) -> BootstrapContext:
    record_id = _required_string(record, "id")
    environment = _required_string(record, "environment")
    operation = _required_string(record, "operation")
    target = _required_string(record, "target")
    operation_id = _required_uuid(record, "operationId")
    payload_hash = _required_string(record, "payloadHash")
    state_value = _required_string(record, "state")
    user_id = _required_uuid(record, "userId")
    event_id = _required_uuid(record, "eventId")
    correlation_id = _required_uuid(record, "correlationId")
    occurred_at = _required_string(record, "occurredAt")
    audit_expires_at = _required_integer(record, "auditExpiresAt")
    actor_id = _required_string(record, "actorId")
    created_at = _required_string(record, "createdAt")
    updated_at = _required_string(record, "updatedAt")
    expiration = _required_integer(record, "expiration")

    cognito_email_verified_required = record.get(
        "cognitoEmailVerifiedRequired",
        False,
    )
    if type(cognito_email_verified_required) is not bool:
        raise InvalidBootstrapRecordError(
            "bootstrap record field cognitoEmailVerifiedRequired must be a boolean when present"
        )

    if environment != expected_environment:
        raise InvalidBootstrapRecordError("bootstrap record environment is incompatible")
    if operation != "bootstrap-admin":
        raise InvalidBootstrapRecordError("bootstrap record operation is incompatible")
    if target != "first-admin":
        raise InvalidBootstrapRecordError("bootstrap record target is incompatible")
    if operation_id != expected_operation_id:
        raise InvalidBootstrapRecordError("bootstrap record operationId is incompatible")
    if state_value not in _BOOTSTRAP_STATES:
        raise InvalidBootstrapRecordError("bootstrap record state is unknown")

    expected_record_id = f"NONHTTP#{environment}#bootstrap-admin#first-admin#{operation_id}"
    if record_id != expected_record_id:
        raise InvalidBootstrapRecordError("bootstrap record id is incompatible")

    cognito_sub = _optional_nonempty_string(record, "cognitoSub")
    if state_value in _STATES_REQUIRING_COGNITO_SUB and cognito_sub is None:
        raise InvalidBootstrapRecordError(
            f"bootstrap record state {state_value} requires cognitoSub"
        )

    return BootstrapContext(
        record_id=record_id,
        environment=environment,
        operation=operation,
        target=target,
        operation_id=operation_id,
        payload_hash=payload_hash,
        state=cast(BootstrapState, state_value),
        user_id=user_id,
        event_id=event_id,
        correlation_id=correlation_id,
        occurred_at=occurred_at,
        audit_expires_at=audit_expires_at,
        actor_id=actor_id,
        created_at=created_at,
        updated_at=updated_at,
        expiration=expiration,
        cognito_email_verified_required=cognito_email_verified_required,
        cognito_sub=cognito_sub,
    )


def _required_string(record: dict[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or value == "":
        raise InvalidBootstrapRecordError(
            f"bootstrap record field {field} must be a non-empty string"
        )
    return value


def _required_integer(record: dict[str, object], field: str) -> int:
    value = record.get(field)
    if type(value) is not int:
        raise InvalidBootstrapRecordError(f"bootstrap record field {field} must be an integer")
    return value


def _required_uuid(record: dict[str, object], field: str) -> str:
    value = _required_string(record, field)
    try:
        return validate_uuid4(value)
    except ValueError:
        raise InvalidBootstrapRecordError(
            f"bootstrap record field {field} must be a canonical UUIDv4"
        ) from None


def _optional_nonempty_string(
    record: dict[str, object],
    field: str,
) -> str | None:
    if field not in record:
        return None

    value = record[field]
    if not isinstance(value, str) or value == "":
        raise InvalidBootstrapRecordError(
            f"bootstrap record field {field} must be a non-empty string when present"
        )
    return value
