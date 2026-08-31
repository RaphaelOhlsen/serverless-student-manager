import pytest

from tools.verify_first_admin_email.audit import (
    audit_event_matches,
    build_first_admin_email_verification_audit_event,
)

_USER_ID = "123e4567-e89b-42d3-a456-426614174000"
_EVENT_ID = "223e4567-e89b-42d3-a456-426614174001"
_OPERATION_ID = "323e4567-e89b-42d3-a456-426614174002"
_CORRELATION_ID = "423e4567-e89b-42d3-a456-426614174003"
_OCCURRED_AT = "2026-08-31T14:25:40.123Z"
_EXPIRES_AT = 1_793_400_340


def _event(*, result: str = "SUCCESS") -> dict[str, object]:
    return build_first_admin_email_verification_audit_event(
        user_id=_USER_ID,
        actor_id="github:raphael",
        event_id=_EVENT_ID,
        operation_id=_OPERATION_ID,
        correlation_id=_CORRELATION_ID,
        occurred_at=_OCCURRED_AT,
        result=result,
        expires_at=_EXPIRES_AT,
    )


@pytest.mark.parametrize("result", ["SUCCESS", "FAILURE"])
def test_build_audit_event_matches_approved_schema(result: str) -> None:
    event = _event(result=result)
    sort_key = f"TS#{_OCCURRED_AT}#EVENT#{_EVENT_ID}"

    assert event == {
        "PK": f"RESOURCE#USER#{_USER_ID}",
        "SK": sort_key,
        "eventId": _EVENT_ID,
        "eventType": "FIRST_ADMIN_EMAIL_VERIFICATION",
        "resourceType": "USER",
        "resourceId": _USER_ID,
        "actorId": "github:raphael",
        "actorType": "OPERATIONAL_WORKFLOW",
        "operationId": _OPERATION_ID,
        "occurredAt": _OCCURRED_AT,
        "result": result,
        "correlationId": _CORRELATION_ID,
        "GSI1PK": "ACTOR#github:raphael",
        "GSI1SK": sort_key,
        "GSI2PK": f"CORRELATION#{_CORRELATION_ID}",
        "GSI2SK": sort_key,
        "GSI3PK": "PERIOD#2026-08",
        "GSI3SK": sort_key,
        "expiresAt": _EXPIRES_AT,
    }


def test_build_audit_event_is_deterministic_and_excludes_pii() -> None:
    first = _event()
    second = _event()

    assert second == first
    assert {
        "email",
        "fullName",
        "cognitoSub",
        "password",
        "temporaryPassword",
        "tokens",
        "TOTP",
        "changes",
    }.isdisjoint(first)


@pytest.mark.parametrize(
    ("field", "different_value"),
    [
        ("eventType", "OTHER_EVENT"),
        ("result", "FAILURE"),
        ("operationId", "different-operation"),
        ("actorId", "github:different"),
        ("resourceId", "different-user"),
        ("correlationId", "different-correlation"),
        ("occurredAt", "2026-09-01T00:00:00.000Z"),
        ("eventId", "different-event"),
        ("expiresAt", 1),
    ],
)
def test_audit_event_matches_rejects_deterministic_difference(
    field: str,
    different_value: object,
) -> None:
    expected = _event()
    actual = {**expected, field: different_value}

    assert audit_event_matches(expected=expected, actual=actual) is False


def test_audit_event_matches_accepts_only_exact_event() -> None:
    expected = _event()

    assert audit_event_matches(expected=expected, actual=dict(expected)) is True
    assert audit_event_matches(expected=expected, actual={**expected, "extra": "value"}) is False
