from dataclasses import dataclass
from datetime import datetime, timedelta

from users_api.errors import InvitationSagaInvariantError
from users_api.validation import CreateUserInput, validate_idempotency_key


@dataclass(frozen=True)
class UserProvisioningItems:
    profile: dict[str, object]
    unique_email: dict[str, object]
    authorization: dict[str, object]
    audit: dict[str, object]
    client_request_token: str


def build_user_provisioning_items(
    *,
    record: dict[str, object],
    user: CreateUserInput,
    audit_retention_days: int,
) -> UserProvisioningItems:
    user_id = _required_string(record, "userId")
    cognito_sub = _required_string(record, "cognitoSub")
    actor_id = _required_string(record, "actorId")
    event_id = _required_string(record, "eventId")
    correlation_id = _required_string(record, "correlationId")
    occurred_at = _required_string(record, "startedAt")
    idempotency_key = validate_idempotency_key(_required_string(record, "idempotencyKey"))
    if record.get("state") != "COGNITO_CREATED":
        raise InvitationSagaInvariantError("provisioning requires COGNITO_CREATED")
    if user.role not in {"ADMIN", "OPERATOR"}:
        raise InvitationSagaInvariantError("provisioning role is invalid")
    try:
        timestamp = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
    except ValueError:
        raise InvitationSagaInvariantError("provisioning timestamp is invalid") from None
    if timestamp.tzinfo is None or not occurred_at.endswith("Z") or audit_retention_days <= 0:
        raise InvitationSagaInvariantError("provisioning timestamp or retention is invalid")

    profile: dict[str, object] = {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "userId": user_id,
        "cognitoSub": cognito_sub,
        "fullName": user.full_name,
        "normalizedName": user.normalized_name,
        "email": user.email,
        "role": user.role,
        "status": "INVITED",
        "version": 1,
        "authVersion": 1,
        "createdAt": occurred_at,
        "createdBy": actor_id,
        "updatedAt": occurred_at,
        "updatedBy": actor_id,
        "GSI1PK": "USERS",
        "GSI1SK": f"NAME#{user.normalized_name}#USER#{user_id}",
    }
    unique_email: dict[str, object] = {
        "PK": f"UNIQUE#EMAIL#{user.email}",
        "SK": "UNIQUE",
        "userId": user_id,
    }
    authorization: dict[str, object] = {
        "PK": f"COGNITO#{cognito_sub}",
        "SK": "AUTHORIZATION",
        "userId": user_id,
        "role": user.role,
        "status": "INVITED",
        "authVersion": 1,
    }
    sort_key = f"TS#{occurred_at}#EVENT#{event_id}"
    audit: dict[str, object] = {
        "PK": f"RESOURCE#USER#{user_id}",
        "SK": sort_key,
        "eventId": event_id,
        "eventType": "USER_INVITED",
        "resourceType": "USER",
        "resourceId": user_id,
        "actorId": actor_id,
        "occurredAt": occurred_at,
        "result": "SUCCESS",
        "correlationId": correlation_id,
        "changes": {
            "role": {"from": None, "to": user.role},
            "status": {"from": None, "to": "INVITED"},
            "version": {"from": None, "to": 1},
        },
        "GSI1PK": f"ACTOR#{actor_id}",
        "GSI1SK": sort_key,
        "GSI2PK": f"CORRELATION#{correlation_id}",
        "GSI2SK": sort_key,
        "GSI3PK": f"PERIOD#{occurred_at[:7]}",
        "GSI3SK": sort_key,
        "expiresAt": int((timestamp + timedelta(days=audit_retention_days)).timestamp()),
    }
    return UserProvisioningItems(
        profile=profile,
        unique_email=unique_email,
        authorization=authorization,
        audit=audit,
        client_request_token=idempotency_key,
    )


def _required_string(record: dict[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise InvitationSagaInvariantError("provisioning saga context is invalid")
    return value
