from typing import Literal

VerifyFirstAdminEmailAuditResult = Literal["SUCCESS", "FAILURE"]


def build_first_admin_email_verification_audit_event(
    *,
    user_id: str,
    actor_id: str,
    event_id: str,
    operation_id: str,
    correlation_id: str,
    occurred_at: str,
    result: VerifyFirstAdminEmailAuditResult,
    expires_at: int,
) -> dict[str, object]:
    sort_key = f"TS#{occurred_at}#EVENT#{event_id}"
    period = occurred_at[:7]

    return {
        "PK": f"RESOURCE#USER#{user_id}",
        "SK": sort_key,
        "eventId": event_id,
        "eventType": "FIRST_ADMIN_EMAIL_VERIFICATION",
        "resourceType": "USER",
        "resourceId": user_id,
        "actorId": actor_id,
        "actorType": "OPERATIONAL_WORKFLOW",
        "operationId": operation_id,
        "occurredAt": occurred_at,
        "result": result,
        "correlationId": correlation_id,
        "GSI1PK": f"ACTOR#{actor_id}",
        "GSI1SK": sort_key,
        "GSI2PK": f"CORRELATION#{correlation_id}",
        "GSI2SK": sort_key,
        "GSI3PK": f"PERIOD#{period}",
        "GSI3SK": sort_key,
        "expiresAt": expires_at,
    }


def audit_event_matches(
    *,
    expected: dict[str, object],
    actual: dict[str, object],
) -> bool:
    return actual == expected
