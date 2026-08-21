import hashlib
import json


def _build_payload_hash(
    *,
    full_name: str,
    normalized_email: str,
) -> str:
    payload = {
        "fullName": full_name,
        "normalizedEmail": normalized_email,
        "role": "ADMIN",
    }

    canonical_payload = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def build_started_record(
    *,
    environment: str,
    operation_id: str,
    correlation_id: str,
    user_id: str,
    event_id: str,
    full_name: str,
    normalized_email: str,
    created_at: str,
    occurred_at: str,
    audit_expires_at: int,
    actor_id: str,
    expiration: int,
) -> dict[str, object]:
    return {
        "id": (f"NONHTTP#{environment}#bootstrap-admin#first-admin#{operation_id}"),
        "environment": environment,
        "operation": "bootstrap-admin",
        "target": "first-admin",
        "operationId": operation_id,
        "payloadHash": _build_payload_hash(
            full_name=full_name,
            normalized_email=normalized_email,
        ),
        "state": "STARTED",
        "userId": user_id,
        "eventId": event_id,
        "correlationId": correlation_id,
        "occurredAt": occurred_at,
        "auditExpiresAt": audit_expires_at,
        "actorId": actor_id,
        "createdAt": created_at,
        "updatedAt": created_at,
        "expiration": expiration,
    }


class IdempotencyConflictError(RuntimeError):
    pass


def validate_existing_record(
    existing: dict[str, object],
    *,
    full_name: str,
    normalized_email: str,
) -> None:
    expected_hash = _build_payload_hash(
        full_name=full_name,
        normalized_email=normalized_email,
    )

    if existing.get("payloadHash") != expected_hash:
        raise IdempotencyConflictError("operationId already exists with an incompatible payload")


_VALID_STATE_TRANSITIONS_BY_OPERATION: dict[str, dict[str, set[str]]] = {
    "bootstrap-admin": {
        "STARTED": {
            "COGNITO_CREATED",
            "RECONCILIATION_REQUIRED",
        },
        "COGNITO_CREATED": {
            "PERSISTENCE_COMPLETED",
            "COMPENSATED",
            "RECONCILIATION_REQUIRED",
        },
        "PERSISTENCE_COMPLETED": {
            "INVITATION_SENT",
            "RECONCILIATION_REQUIRED",
        },
        "INVITATION_SENT": {
            "COMPLETED",
            "RECONCILIATION_REQUIRED",
        },
        "COMPLETED": set(),
        "COMPENSATED": set(),
        "RECONCILIATION_REQUIRED": set(),
    },
    "resume-first-admin-invitation": {
        "STARTED": {
            "COMPLETED",
            "RECONCILIATION_REQUIRED",
        },
        "COMPLETED": set(),
        "RECONCILIATION_REQUIRED": set(),
    },
}


def is_valid_state_transition(
    *,
    operation: str,
    current_state: str,
    next_state: str,
) -> bool:
    operation_transitions = _VALID_STATE_TRANSITIONS_BY_OPERATION.get(operation, {})
    return next_state in operation_transitions.get(current_state, set())
