from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from tools.bootstrap_admin.service import FirstAdminBootstrapService
from tools.bootstrap_admin.service_models import FirstAdminBootstrapConfig

_OPERATION_ID = "123e4567-e89b-42d3-a456-426614174000"
_USER_ID = "223e4567-e89b-42d3-a456-426614174001"
_EVENT_ID = "323e4567-e89b-42d3-a456-426614174002"
_CORRELATION_ID = "423e4567-e89b-42d3-a456-426614174003"


class FakeClock:
    def __init__(self, values: list[datetime], events: list[str]) -> None:
        self._values = values
        self._events = events
        self.calls = 0

    def now(self) -> datetime:
        self.calls += 1
        self._events.append(f"clock:{self.calls}")
        return self._values.pop(0)


class FakeIdGenerator:
    def __init__(self, values: list[str], events: list[str]) -> None:
        self._values = values
        self._events = events
        self.calls = 0

    def new_uuid4(self) -> str:
        self.calls += 1
        self._events.append(f"uuid:{self.calls}")
        return self._values.pop(0)


class FakeIdempotencyRepository:
    def __init__(
        self,
        events: list[str],
        *,
        existing: dict[str, object] | None = None,
    ) -> None:
        self._events = events
        self._existing = existing
        self.get_calls: list[str] = []
        self.started_records: list[dict[str, object]] = []
        self.transitions: list[dict[str, object]] = []

    def get(self, record_id: str) -> dict[str, object] | None:
        self._events.append("idempotency:get")
        self.get_calls.append(record_id)
        return self._existing

    def create_started(self, record: dict[str, object]) -> None:
        self._events.append("idempotency:create_started")
        self.started_records.append(record)

    def transition_state(
        self,
        *,
        record_id: str,
        operation: str,
        current_state: str,
        next_state: str,
        updated_at: str,
        cognito_sub: str | None = None,
    ) -> None:
        self._events.append(f"idempotency:transition:{next_state}")
        call: dict[str, object] = {
            "record_id": record_id,
            "operation": operation,
            "current_state": current_state,
            "next_state": next_state,
            "updated_at": updated_at,
        }
        if cognito_sub is not None:
            call["cognito_sub"] = cognito_sub
        self.transitions.append(call)


class FakeCognitoRepository:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.create_calls: list[dict[str, str]] = []
        self.resend_calls: list[dict[str, str]] = []

    def create_suppressed_user(
        self,
        *,
        user_pool_id: str,
        user_id: str,
        email: str,
    ) -> str:
        self._events.append("cognito:create_suppressed")
        self.create_calls.append(
            {
                "user_pool_id": user_pool_id,
                "user_id": user_id,
                "email": email,
            }
        )
        return "cognito-sub-123"

    def resend_invitation(self, *, user_pool_id: str, user_id: str) -> None:
        self._events.append("cognito:resend")
        self.resend_calls.append(
            {
                "user_pool_id": user_pool_id,
                "user_id": user_id,
            }
        )


class FakeProvisioningRepository:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.calls: list[dict[str, Any]] = []

    def persist_first_admin_with_audit(self, **kwargs: Any) -> None:
        self._events.append("provisioning:persist")
        self.calls.append(dict(kwargs))


def _config() -> FirstAdminBootstrapConfig:
    return FirstAdminBootstrapConfig(
        environment="dev",
        user_pool_id="pool-123",
        users_table_name="users-table",
        audit_table_name="audit-table",
        audit_retention_days=90,
    )


def _build_service(
    *,
    existing: dict[str, object] | None = None,
) -> tuple[
    FirstAdminBootstrapService,
    list[str],
    FakeClock,
    FakeIdGenerator,
    FakeIdempotencyRepository,
    FakeCognitoRepository,
    FakeProvisioningRepository,
]:
    events: list[str] = []
    base = datetime(2026, 8, 20, 13, 45, 12, 347891, tzinfo=UTC)
    clock = FakeClock(
        [base + timedelta(minutes=offset) for offset in range(5)],
        events,
    )
    id_generator = FakeIdGenerator(
        [_USER_ID, _EVENT_ID, _CORRELATION_ID],
        events,
    )
    idempotency = FakeIdempotencyRepository(events, existing=existing)
    cognito = FakeCognitoRepository(events)
    provisioning = FakeProvisioningRepository(events)
    service = FirstAdminBootstrapService(
        config=_config(),
        clock=clock,
        id_generator=id_generator,
        idempotency_repository=idempotency,
        cognito_repository=cognito,
        provisioning_repository=provisioning,
    )
    return (
        service,
        events,
        clock,
        id_generator,
        idempotency,
        cognito,
        provisioning,
    )


def test_bootstrap_first_admin_executes_deterministic_happy_path() -> None:
    (
        service,
        events,
        clock,
        id_generator,
        idempotency,
        cognito,
        provisioning,
    ) = _build_service()

    result = service.bootstrap_first_admin(
        full_name="  Maria   DA Silva  ",
        email="  Admin@Example.COM ",
        operation_id=_OPERATION_ID,
        actor_id="github:raphael",
    )

    record_id = f"NONHTTP#dev#bootstrap-admin#first-admin#{_OPERATION_ID}"
    assert result.operation_id == _OPERATION_ID
    assert result.user_id == _USER_ID
    assert result.state == "COMPLETED"
    assert result.replayed is False
    assert id_generator.calls == 3
    assert clock.calls == 5
    assert idempotency.get_calls == [record_id]

    assert len(idempotency.started_records) == 1
    started = idempotency.started_records[0]
    assert started == {
        "id": record_id,
        "environment": "dev",
        "operation": "bootstrap-admin",
        "target": "first-admin",
        "operationId": _OPERATION_ID,
        "payloadHash": "4cabbbd2f7ce477bb5d60430ca49752a89836f7d54a174836b87085aa420a3e8",
        "state": "STARTED",
        "userId": _USER_ID,
        "eventId": _EVENT_ID,
        "correlationId": _CORRELATION_ID,
        "occurredAt": "2026-08-20T13:45:12.347Z",
        "auditExpiresAt": 1_795_009_512,
        "actorId": "github:raphael",
        "createdAt": "2026-08-20T13:45:12.347Z",
        "updatedAt": "2026-08-20T13:45:12.347Z",
        "expiration": 1_787_319_912,
    }
    for forbidden in ("clientRequestToken", "fullName", "email", "normalizedEmail"):
        assert forbidden not in started

    assert cognito.create_calls == [
        {
            "user_pool_id": "pool-123",
            "user_id": _USER_ID,
            "email": "admin@example.com",
        }
    ]
    assert cognito.resend_calls == [
        {
            "user_pool_id": "pool-123",
            "user_id": _USER_ID,
        }
    ]

    assert idempotency.transitions == [
        {
            "record_id": record_id,
            "operation": "bootstrap-admin",
            "current_state": "STARTED",
            "next_state": "COGNITO_CREATED",
            "updated_at": "2026-08-20T13:46:12.347Z",
            "cognito_sub": "cognito-sub-123",
        },
        {
            "record_id": record_id,
            "operation": "bootstrap-admin",
            "current_state": "COGNITO_CREATED",
            "next_state": "PERSISTENCE_COMPLETED",
            "updated_at": "2026-08-20T13:47:12.347Z",
        },
        {
            "record_id": record_id,
            "operation": "bootstrap-admin",
            "current_state": "PERSISTENCE_COMPLETED",
            "next_state": "INVITATION_SENT",
            "updated_at": "2026-08-20T13:48:12.347Z",
        },
        {
            "record_id": record_id,
            "operation": "bootstrap-admin",
            "current_state": "INVITATION_SENT",
            "next_state": "COMPLETED",
            "updated_at": "2026-08-20T13:49:12.347Z",
        },
    ]

    assert len(provisioning.calls) == 1
    persistence = provisioning.calls[0]
    assert persistence["users_table_name"] == "users-table"
    assert persistence["audit_table_name"] == "audit-table"
    assert persistence["client_request_token"] == _OPERATION_ID
    assert persistence["user_profile"] == {
        "PK": f"USER#{_USER_ID}",
        "SK": "PROFILE",
        "userId": _USER_ID,
        "cognitoSub": "cognito-sub-123",
        "fullName": "  Maria   DA Silva  ",
        "normalizedName": "maria da silva",
        "email": "admin@example.com",
        "role": "ADMIN",
        "status": "INVITED",
        "authVersion": 1,
        "createdAt": "2026-08-20T13:45:12.347Z",
        "createdBy": "github:raphael",
        "updatedAt": "2026-08-20T13:45:12.347Z",
        "updatedBy": "github:raphael",
        "GSI1PK": "USERS",
        "GSI1SK": f"NAME#maria da silva#USER#{_USER_ID}",
    }
    assert persistence["unique_email"] == {
        "PK": "UNIQUE#EMAIL#admin@example.com",
        "SK": "UNIQUE",
        "userId": _USER_ID,
    }
    assert persistence["cognito_projection"] == {
        "PK": "COGNITO#cognito-sub-123",
        "SK": "AUTHORIZATION",
        "userId": _USER_ID,
        "role": "ADMIN",
        "status": "INVITED",
        "authVersion": 1,
    }
    assert persistence["bootstrap_marker"] == {
        "PK": "CONTROL#FIRST_ADMIN_BOOTSTRAP",
        "SK": "CONTROL",
        "userId": _USER_ID,
        "operationId": _OPERATION_ID,
        "createdAt": "2026-08-20T13:45:12.347Z",
        "createdBy": "github:raphael",
    }
    audit_event = persistence["audit_event"]
    assert isinstance(audit_event, dict)
    assert audit_event["eventId"] == _EVENT_ID
    assert audit_event["eventType"] == "USER_CREATED"
    assert audit_event["actorId"] == "github:raphael"
    assert audit_event["occurredAt"] == started["createdAt"]
    assert audit_event["correlationId"] == _CORRELATION_ID
    assert audit_event["result"] == "SUCCESS"
    assert audit_event["expiresAt"] == started["auditExpiresAt"]
    assert "CONTROL#ACTIVE_ADMIN_COUNT" not in repr(persistence)

    assert events == [
        "idempotency:get",
        "uuid:1",
        "uuid:2",
        "uuid:3",
        "clock:1",
        "idempotency:create_started",
        "cognito:create_suppressed",
        "clock:2",
        "idempotency:transition:COGNITO_CREATED",
        "provisioning:persist",
        "clock:3",
        "idempotency:transition:PERSISTENCE_COMPLETED",
        "cognito:resend",
        "clock:4",
        "idempotency:transition:INVITATION_SENT",
        "clock:5",
        "idempotency:transition:COMPLETED",
    ]


def test_existing_record_fails_without_partial_replay() -> None:
    service, events, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing={"state": "STARTED"}
    )

    with pytest.raises(NotImplementedError, match="replay is not implemented"):
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:raphael",
        )

    assert events == ["idempotency:get"]
    assert clock.calls == 0
    assert ids.calls == 0
    assert idempotency.started_records == []
    assert idempotency.transitions == []
    assert cognito.create_calls == []
    assert cognito.resend_calls == []
    assert provisioning.calls == []


@pytest.mark.parametrize(
    ("operation_id", "actor_id", "error_match"),
    [
        ("invalid-operation-id", "github:raphael", "canonical UUIDv4"),
        (_OPERATION_ID, "", "actor_id"),
    ],
)
def test_invalid_input_fails_before_any_dependency_call(
    operation_id: str,
    actor_id: str,
    error_match: str,
) -> None:
    service, events, clock, ids, idempotency, cognito, provisioning = _build_service()

    with pytest.raises(ValueError, match=error_match):
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=operation_id,
            actor_id=actor_id,
        )

    assert events == []
    assert clock.calls == 0
    assert ids.calls == 0
    assert idempotency.get_calls == []
    assert cognito.create_calls == []
    assert cognito.resend_calls == []
    assert provisioning.calls == []
