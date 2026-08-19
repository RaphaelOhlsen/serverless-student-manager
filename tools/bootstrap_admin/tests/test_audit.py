from tools.bootstrap_admin.audit import build_user_created_audit_event


def test_build_user_created_audit_event_uses_approved_conventions() -> None:
    item = build_user_created_audit_event(
        user_id="user-123",
        github_actor="RaphaelOhlsen",
        event_id="event-123",
        correlation_id="correlation-123",
        occurred_at="2026-08-19T20:00:00Z",
        expires_at=1784664000,
    )

    assert item == {
        "PK": "RESOURCE#USER#user-123",
        "SK": "TS#2026-08-19T20:00:00Z#EVENT#event-123",
        "eventId": "event-123",
        "eventType": "USER_CREATED",
        "resourceType": "USER",
        "resourceId": "user-123",
        "actorId": "github:RaphaelOhlsen",
        "occurredAt": "2026-08-19T20:00:00Z",
        "result": "SUCCESS",
        "correlationId": "correlation-123",
        "GSI1PK": "ACTOR#github:RaphaelOhlsen",
        "GSI1SK": "TS#2026-08-19T20:00:00Z#EVENT#event-123",
        "GSI2PK": "CORRELATION#correlation-123",
        "GSI2SK": "TS#2026-08-19T20:00:00Z#EVENT#event-123",
        "GSI3PK": "PERIOD#2026-08",
        "GSI3SK": "TS#2026-08-19T20:00:00Z#EVENT#event-123",
        "expiresAt": 1784664000,
    }
