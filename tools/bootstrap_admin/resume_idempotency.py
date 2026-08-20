import hashlib
import json

from tools.bootstrap_admin.idempotency import IdempotencyConflictError


def resume_invitation_payload_hash() -> str:
    payload = {"target": "first-admin"}
    canonical_payload = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def build_resume_invitation_started_record(
    *,
    environment: str,
    operation_id: str,
    correlation_id: str,
    actor_id: str,
    created_at: str,
    expiration: int,
) -> dict[str, object]:
    return {
        "id": (
            f"NONHTTP#{environment}#resume-first-admin-invitation#first-admin#"
            f"{operation_id}"
        ),
        "environment": environment,
        "operation": "resume-first-admin-invitation",
        "target": "first-admin",
        "operationId": operation_id,
        "payloadHash": resume_invitation_payload_hash(),
        "state": "STARTED",
        "correlationId": correlation_id,
        "actorId": actor_id,
        "createdAt": created_at,
        "updatedAt": created_at,
        "expiration": expiration,
    }


def validate_resume_invitation_existing_record(
    existing: dict[str, object],
) -> None:
    if existing.get("payloadHash") != resume_invitation_payload_hash():
        raise IdempotencyConflictError(
            "operationId already exists with an incompatible payload"
        )
