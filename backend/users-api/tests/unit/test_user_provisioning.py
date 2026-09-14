import pytest
from users_api.services.user_provisioning import build_user_provisioning_items
from users_api.validation import CreateUserInput

USER_ID = "11111111-1111-4111-8111-111111111111"
COGNITO_SUB = "22222222-2222-4222-8222-222222222222"
EVENT_ID = "33333333-3333-4333-8333-333333333333"
KEY = "44444444-4444-4444-8444-444444444444"
STARTED_AT = "2026-09-14T12:00:00.000Z"


def record() -> dict[str, object]:
    return {
        "id": "HTTP#dev#actor-1#create-user#key",
        "state": "COGNITO_CREATED",
        "userId": USER_ID,
        "cognitoSub": COGNITO_SUB,
        "actorId": "actor-1",
        "eventId": EVENT_ID,
        "correlationId": "request-1",
        "startedAt": STARTED_AT,
        "idempotencyKey": KEY,
    }


@pytest.mark.parametrize("role", ["ADMIN", "OPERATOR"])
def test_builds_approved_five_item_domain_shapes(role: str) -> None:
    user = CreateUserInput("Ágata Silva", "ágata silva", "admin@example.test", role)
    items = build_user_provisioning_items(record=record(), user=user, audit_retention_days=90)

    assert items.profile == {
        "PK": f"USER#{USER_ID}",
        "SK": "PROFILE",
        "userId": USER_ID,
        "cognitoSub": COGNITO_SUB,
        "fullName": "Ágata Silva",
        "normalizedName": "ágata silva",
        "email": "admin@example.test",
        "role": role,
        "status": "INVITED",
        "version": 1,
        "authVersion": 1,
        "createdAt": STARTED_AT,
        "createdBy": "actor-1",
        "updatedAt": STARTED_AT,
        "updatedBy": "actor-1",
        "GSI1PK": "USERS",
        "GSI1SK": f"NAME#ágata silva#USER#{USER_ID}",
    }
    assert items.unique_email == {
        "PK": "UNIQUE#EMAIL#admin@example.test",
        "SK": "UNIQUE",
        "userId": USER_ID,
    }
    assert items.authorization == {
        "PK": f"COGNITO#{COGNITO_SUB}",
        "SK": "AUTHORIZATION",
        "userId": USER_ID,
        "role": role,
        "status": "INVITED",
        "authVersion": 1,
    }
    assert items.audit["eventType"] == "USER_INVITED"
    assert items.audit["eventId"] == EVENT_ID
    assert items.audit["GSI1PK"] == "ACTOR#actor-1"
    assert items.audit["GSI2PK"] == "CORRELATION#request-1"
    assert items.audit["GSI3PK"] == "PERIOD#2026-09"
    assert items.client_request_token == KEY
    rendered_audit = repr(items.audit)
    assert "admin@example.test" not in rendered_audit
    assert "Ágata Silva" not in rendered_audit
    assert "CONTROL#ACTIVE_ADMIN_COUNT" not in repr(items)


def test_retries_rebuild_identical_items_and_client_request_token() -> None:
    user = CreateUserInput("Admin Example", "admin example", "admin@example.test", "ADMIN")
    first = build_user_provisioning_items(record=record(), user=user, audit_retention_days=90)
    second = build_user_provisioning_items(record=record(), user=user, audit_retention_days=90)
    assert first == second
