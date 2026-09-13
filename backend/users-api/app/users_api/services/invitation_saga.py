import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from users_api.errors import InvitationSagaInvariantError
from users_api.validation import normalize_admin_user_email, normalize_admin_user_full_name

CREATE_USER_OPERATION: Final = "create-user"
RESEND_INVITATION_OPERATION: Final = "resend-user-invitation"
IDEMPOTENCY_TTL_SECONDS: Final = 24 * 60 * 60
IN_PROGRESS_TTL_SECONDS: Final = 60
INVITATION_DELIVERY_FAILED: Final = "INVITATION_DELIVERY_FAILED"
INVITATION_DELIVERY_UNCERTAIN: Final = "INVITATION_DELIVERY_UNCERTAIN"


class CreateSagaState(StrEnum):
    CLAIMED = "CLAIMED"
    COGNITO_CREATED = "COGNITO_CREATED"
    DDB_COMMITTED = "DDB_COMMITTED"
    INVITATION_DISPATCHING = "INVITATION_DISPATCHING"
    INVITATION_RETRYABLE = "INVITATION_RETRYABLE"
    INVITATION_SENT = "INVITATION_SENT"
    COMPLETED = "COMPLETED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class ResendSagaState(StrEnum):
    CLAIMED = "CLAIMED"
    DISPATCHING = "DISPATCHING"
    RETRYABLE = "RETRYABLE"
    SENT = "SENT"
    COMPLETED = "COMPLETED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


CREATE_TRANSITIONS: Final = {
    CreateSagaState.CLAIMED: {
        CreateSagaState.COGNITO_CREATED,
        CreateSagaState.RECONCILIATION_REQUIRED,
    },
    CreateSagaState.COGNITO_CREATED: {
        CreateSagaState.DDB_COMMITTED,
        CreateSagaState.RECONCILIATION_REQUIRED,
    },
    CreateSagaState.DDB_COMMITTED: {
        CreateSagaState.INVITATION_DISPATCHING,
        CreateSagaState.RECONCILIATION_REQUIRED,
    },
    CreateSagaState.INVITATION_DISPATCHING: {
        CreateSagaState.INVITATION_RETRYABLE,
        CreateSagaState.INVITATION_SENT,
        CreateSagaState.RECONCILIATION_REQUIRED,
    },
    CreateSagaState.INVITATION_RETRYABLE: {
        CreateSagaState.INVITATION_DISPATCHING,
        CreateSagaState.RECONCILIATION_REQUIRED,
    },
    CreateSagaState.INVITATION_SENT: {
        CreateSagaState.COMPLETED,
        CreateSagaState.RECONCILIATION_REQUIRED,
    },
    CreateSagaState.COMPLETED: set(),
    CreateSagaState.RECONCILIATION_REQUIRED: set(),
}

RESEND_TRANSITIONS: Final = {
    ResendSagaState.CLAIMED: {
        ResendSagaState.DISPATCHING,
        ResendSagaState.RECONCILIATION_REQUIRED,
    },
    ResendSagaState.DISPATCHING: {
        ResendSagaState.RETRYABLE,
        ResendSagaState.SENT,
        ResendSagaState.RECONCILIATION_REQUIRED,
    },
    ResendSagaState.RETRYABLE: {
        ResendSagaState.DISPATCHING,
        ResendSagaState.RECONCILIATION_REQUIRED,
    },
    ResendSagaState.SENT: {
        ResendSagaState.COMPLETED,
        ResendSagaState.RECONCILIATION_REQUIRED,
    },
    ResendSagaState.COMPLETED: set(),
    ResendSagaState.RECONCILIATION_REQUIRED: set(),
}


@dataclass(frozen=True)
class SagaClaim:
    record: dict[str, object]
    created: bool


@dataclass(frozen=True)
class StoredReplay:
    http_status: int
    response_user_id: str | None


def create_request_hash(*, full_name: str, email: str, role: str) -> str:
    normalized_full_name = normalize_admin_user_full_name(full_name)
    normalized_email = normalize_admin_user_email(email)
    if role not in {"ADMIN", "OPERATOR"}:
        raise InvitationSagaInvariantError("invalid role for create-user request hash")
    return _hash(
        {
            "operation": CREATE_USER_OPERATION,
            "fullName": normalized_full_name,
            "email": normalized_email,
            "role": role,
        }
    )


def resend_request_hash(*, user_id: str, expected_version: int) -> str:
    return _hash(
        {
            "operation": RESEND_INVITATION_OPERATION,
            "targetUserId": user_id,
            "expectedVersion": expected_version,
        }
    )


def validate_transition(*, operation: str, current_state: str, next_state: str) -> None:
    try:
        if operation == CREATE_USER_OPERATION:
            create_current = CreateSagaState(current_state)
            create_next = CreateSagaState(next_state)
            if create_next not in CREATE_TRANSITIONS[create_current]:
                raise InvitationSagaInvariantError(
                    f"invalid invitation saga transition: {current_state} -> {next_state}"
                )
            return
        if operation == RESEND_INVITATION_OPERATION:
            resend_current = ResendSagaState(current_state)
            resend_next = ResendSagaState(next_state)
            if resend_next not in RESEND_TRANSITIONS[resend_current]:
                raise InvitationSagaInvariantError(
                    f"invalid invitation saga transition: {current_state} -> {next_state}"
                )
            return
        raise InvitationSagaInvariantError("unsupported invitation saga operation")
    except ValueError:
        raise InvitationSagaInvariantError("unknown invitation saga state") from None


def replay_from_record(record: dict[str, object]) -> StoredReplay:
    if record.get("state") != "COMPLETED":
        raise InvitationSagaInvariantError("invitation saga is not completed")
    status = record.get("httpStatus")
    if type(status) is not int or status not in {201, 204}:
        raise InvitationSagaInvariantError("completed invitation saga has invalid HTTP status")
    response_user_id = record.get("responseUserId")
    if status == 201 and (not isinstance(response_user_id, str) or not response_user_id):
        raise InvitationSagaInvariantError("create replay is missing response user ID")
    if status == 204 and response_user_id is not None:
        raise InvitationSagaInvariantError("resend replay must not contain a response user ID")
    return StoredReplay(status, response_user_id if isinstance(response_user_id, str) else None)


def _hash(value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
