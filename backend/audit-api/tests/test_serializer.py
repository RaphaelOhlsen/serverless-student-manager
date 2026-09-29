import pytest
from audit_api.errors import AuditEventDataInvariantError
from audit_api.serializer import serialize_public_event


def stored_event() -> dict[str, object]:
    return {
        "eventId": "event-1",
        "eventType": "STUDENT_UPDATED",
        "resourceType": "STUDENT",
        "resourceId": "student-1",
        "actorId": "admin-1",
        "occurredAt": "2026-09-28T14:30:00.000Z",
        "result": "SUCCESS",
        "correlationId": "correlation-1",
        "changes": {"email": {"from": "old@example.test", "to": "new@example.test"}},
        "reason": "private",
        "actorType": "USER",
        "operationId": "operation-1",
        "observedVersion": 4,
        "expiresAt": 1_800_000_000,
        "PK": "RESOURCE#STUDENT#student-1",
        "SK": "TS#2026-09-28T14:30:00.000Z#EVENT#event-1",
        "GSI1PK": "ACTOR#admin-1",
        "GSI3SK": "TS#2026-09-28T14:30:00.000Z#EVENT#event-1",
    }


def test_serializer_exposes_exact_public_projection() -> None:
    result = serialize_public_event(stored_event())

    assert result == {
        "eventId": "event-1",
        "eventType": "STUDENT_UPDATED",
        "resourceType": "STUDENT",
        "resourceId": "student-1",
        "actorId": "admin-1",
        "occurredAt": "2026-09-28T14:30:00.000Z",
        "result": "SUCCESS",
        "correlationId": "correlation-1",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("eventId", None),
        ("eventType", ""),
        ("resourceType", "COURSE"),
        ("occurredAt", "2026-09-28T14:30:00+00:00"),
        ("result", "DENIED"),
        ("correlationId", 12),
    ],
)
def test_serializer_fails_closed_on_malformed_required_field(field: str, value: object) -> None:
    item = stored_event()
    item[field] = value

    with pytest.raises(AuditEventDataInvariantError):
        serialize_public_event(item)
