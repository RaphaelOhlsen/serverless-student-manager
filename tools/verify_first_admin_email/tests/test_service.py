from datetime import UTC, datetime
from typing import Literal

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError  # type: ignore[import-untyped]

from tools.verify_first_admin_email.audit import (
    build_first_admin_email_verification_audit_event,
)
from tools.verify_first_admin_email.discovery import (
    FirstAdminEmailTarget,
    VerifyFirstAdminEmailDiscoveryResult,
)
from tools.verify_first_admin_email.idempotency import (
    build_verify_first_admin_email_started_record,
)
from tools.verify_first_admin_email.service import (
    VerifyFirstAdminEmailResult,
    VerifyFirstAdminEmailService,
    VerifyFirstAdminEmailServiceConfig,
    VerifyFirstAdminEmailTerminalState,
)

_OPERATION_ID = "123e4567-e89b-42d3-a456-426614174000"
_EVENT_ID = "223e4567-e89b-42d3-a456-426614174001"
_CORRELATION_ID = "323e4567-e89b-42d3-a456-426614174002"
_USER_ID = "423e4567-e89b-42d3-a456-426614174003"
_OCCURRED_AT = "2026-08-31T14:25:40.123Z"
_BASE_TIME = datetime(2026, 8, 31, 14, 25, 40, 123000, tzinfo=UTC)
_AUDIT_EXPIRES_AT = 1_795_962_340
_IDEMPOTENCY_EXPIRATION = 1_788_272_740


class FakeClock:
    def __init__(self) -> None:
        self.calls = 0

    def now(self) -> datetime:
        self.calls += 1
        return _BASE_TIME


class FakeIdGenerator:
    def __init__(self) -> None:
        self.values = [_EVENT_ID, _CORRELATION_ID]
        self.calls = 0

    def new_uuid4(self) -> str:
        self.calls += 1
        return self.values.pop(0)


class FakeIdempotencyRepository:
    def __init__(
        self,
        *,
        existing: dict[str, object] | None = None,
        events: list[str] | None = None,
        create_error: Exception | None = None,
        transition_error: Exception | None = None,
        get_outcomes: list[dict[str, object] | None | Exception] | None = None,
    ) -> None:
        self.existing = existing
        self.events = events if events is not None else []
        self.get_calls: list[str] = []
        self.created: list[dict[str, object]] = []
        self.transitions: list[dict[str, object]] = []
        self.create_error = create_error
        self.transition_error = transition_error
        self.get_outcomes = list(get_outcomes or [])

    def get(self, record_id: str) -> dict[str, object] | None:
        self.events.append("idempotency:get")
        self.get_calls.append(record_id)
        outcome = self.get_outcomes.pop(0) if self.get_outcomes else self.existing
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def create_started(self, record: dict[str, object]) -> None:
        self.events.append("idempotency:create")
        self.created.append(record)
        if self.create_error is not None:
            raise self.create_error

    def transition_state(self, **kwargs: object) -> None:
        self.events.append(f"idempotency:transition:{kwargs['next_state']}")
        self.transitions.append(dict(kwargs))
        if self.transition_error is not None:
            raise self.transition_error


class FakeDiscovery:
    def __init__(
        self,
        *results: VerifyFirstAdminEmailDiscoveryResult | Exception,
        events: list[str] | None = None,
    ) -> None:
        self.results = list(results)
        self.events = events if events is not None else []
        self.calls = 0

    def discover(self) -> VerifyFirstAdminEmailDiscoveryResult:
        self.events.append("discovery")
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeCognitoRepository:
    def __init__(
        self,
        *,
        events: list[str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.events = events if events is not None else []
        self.calls: list[dict[str, str]] = []
        self.error = error

    def set_email_verified(self, *, user_pool_id: str, user_id: str) -> None:
        self.events.append("cognito:set_email_verified")
        self.calls.append({"user_pool_id": user_pool_id, "user_id": user_id})
        if self.error is not None:
            raise self.error


class FakeAuditRepository:
    def __init__(
        self,
        *,
        existing: dict[str, object] | None = None,
        replace_put_with: dict[str, object] | None = None,
        events: list[str] | None = None,
        put_error: Exception | None = None,
        get_outcomes: list[dict[str, object] | None | Exception] | None = None,
    ) -> None:
        self.current = existing
        self.replace_put_with = replace_put_with
        self.events = events if events is not None else []
        self.puts: list[dict[str, object]] = []
        self.gets: list[dict[str, str]] = []
        self.put_error = put_error
        self.get_outcomes = list(get_outcomes or [])

    def put_event(
        self,
        *,
        audit_table_name: str,
        event: dict[str, object],
    ) -> None:
        self.events.append("audit:put")
        self.puts.append({"audit_table_name": audit_table_name, "event": event})
        if self.put_error is not None:
            raise self.put_error
        self.current = self.replace_put_with if self.replace_put_with is not None else event

    def get_event(
        self,
        *,
        audit_table_name: str,
        user_id: str,
        occurred_at: str,
        event_id: str,
    ) -> dict[str, object] | None:
        self.events.append("audit:get")
        self.gets.append(
            {
                "audit_table_name": audit_table_name,
                "user_id": user_id,
                "occurred_at": occurred_at,
                "event_id": event_id,
            }
        )
        outcome = self.get_outcomes.pop(0) if self.get_outcomes else self.current
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _aws_error(code: str, *, operation: str = "PutItem") -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": "sanitized"}},
        operation,
    )


def _ambiguous_error() -> ReadTimeoutError:
    return ReadTimeoutError(endpoint_url="https://example.invalid", error="timeout")


def _target() -> FirstAdminEmailTarget:
    return FirstAdminEmailTarget(
        user_id=_USER_ID,
        email="admin@example.com",
        cognito_sub="cognito-sub-123",
    )


def _discovery(
    status: Literal[
        "NEEDS_VERIFICATION",
        "ALREADY_VERIFIED",
        "RECONCILIATION_REQUIRED",
    ],
    *,
    authoritative_user_id: str | None = None,
) -> VerifyFirstAdminEmailDiscoveryResult:
    target = None if status == "RECONCILIATION_REQUIRED" else _target()
    return VerifyFirstAdminEmailDiscoveryResult(
        status=status,
        target=target,
        authoritative_user_id=(target.user_id if target is not None else authoritative_user_id),
    )


def _started_record(*, state: str = "STARTED") -> dict[str, object]:
    record = build_verify_first_admin_email_started_record(
        environment="dev",
        operation_id=_OPERATION_ID,
        event_id=_EVENT_ID,
        correlation_id=_CORRELATION_ID,
        actor_id="github:original",
        occurred_at=_OCCURRED_AT,
        audit_expires_at=_AUDIT_EXPIRES_AT,
        created_at=_OCCURRED_AT,
        expiration=_IDEMPOTENCY_EXPIRATION,
    )
    record["state"] = state
    return record


def _audit_event(
    *,
    result: Literal["SUCCESS", "FAILURE"],
    actor_id: str = "github:original",
) -> dict[str, object]:
    return build_first_admin_email_verification_audit_event(
        user_id=_USER_ID,
        actor_id=actor_id,
        event_id=_EVENT_ID,
        operation_id=_OPERATION_ID,
        correlation_id=_CORRELATION_ID,
        occurred_at=_OCCURRED_AT,
        result=result,
        expires_at=_AUDIT_EXPIRES_AT,
    )


def _service(
    *,
    idempotency: FakeIdempotencyRepository,
    discovery: FakeDiscovery,
    cognito: FakeCognitoRepository | None = None,
    audit: FakeAuditRepository | None = None,
    clock: FakeClock | None = None,
    ids: FakeIdGenerator | None = None,
) -> tuple[
    VerifyFirstAdminEmailService,
    FakeCognitoRepository,
    FakeAuditRepository,
    FakeClock,
    FakeIdGenerator,
]:
    cognito = cognito or FakeCognitoRepository()
    audit = audit or FakeAuditRepository()
    clock = clock or FakeClock()
    ids = ids or FakeIdGenerator()
    return (
        VerifyFirstAdminEmailService(
            config=VerifyFirstAdminEmailServiceConfig(
                environment="dev",
                user_pool_id="us-east-1_example",
                audit_table_name="audit-table",
                audit_retention_days=90,
            ),
            clock=clock,
            id_generator=ids,
            idempotency_repository=idempotency,
            discovery=discovery,
            cognito_repository=cognito,
            audit_repository=audit,
        ),
        cognito,
        audit,
        clock,
        ids,
    )


def _verify(
    service: VerifyFirstAdminEmailService,
    *,
    actor_id: str = "github:caller",
) -> VerifyFirstAdminEmailResult:
    return service.verify_first_admin_email(
        operation_id=_OPERATION_ID,
        actor_id=actor_id,
    )


def test_invalid_operation_id_fails_before_any_effect() -> None:
    events: list[str] = []
    idempotency = FakeIdempotencyRepository(events=events)
    discovery = FakeDiscovery(_discovery("ALREADY_VERIFIED"), events=events)
    service, cognito, audit, clock, ids = _service(
        idempotency=idempotency,
        discovery=discovery,
    )

    with pytest.raises(ValueError, match="canonical UUIDv4"):
        service.verify_first_admin_email(
            operation_id="invalid",
            actor_id="github:caller",
        )

    assert events == []
    assert cognito.calls == []
    assert audit.puts == []
    assert clock.calls == 0
    assert ids.calls == 0


def test_new_operation_creates_started_with_deterministic_metadata_and_no_pii() -> None:
    idempotency = FakeIdempotencyRepository()
    discovery = FakeDiscovery(_discovery("ALREADY_VERIFIED"))
    service, _, _, _, ids = _service(idempotency=idempotency, discovery=discovery)

    result = _verify(service)

    assert result == VerifyFirstAdminEmailResult(
        operation_id=_OPERATION_ID,
        state="COMPLETED",
        replayed=False,
    )
    assert ids.calls == 2
    assert idempotency.created == [
        {
            "id": (f"NONHTTP#dev#verify-first-admin-email#first-admin#{_OPERATION_ID}"),
            "environment": "dev",
            "operation": "verify-first-admin-email",
            "target": "first-admin",
            "operationId": _OPERATION_ID,
            "payloadHash": ("1e79147440f3071256d852615a858fa0b107398317c8a739f5f4d386ed2b135a"),
            "state": "STARTED",
            "eventId": _EVENT_ID,
            "correlationId": _CORRELATION_ID,
            "occurredAt": _OCCURRED_AT,
            "auditExpiresAt": _AUDIT_EXPIRES_AT,
            "actorId": "github:caller",
            "createdAt": _OCCURRED_AT,
            "updatedAt": _OCCURRED_AT,
            "expiration": _IDEMPOTENCY_EXPIRATION,
        }
    ]
    forbidden = {"email", "fullName", "cognitoSub", "userId", "tokens", "TOTP"}
    assert forbidden.isdisjoint(idempotency.created[0])


@pytest.mark.parametrize("state", ["COMPLETED", "RECONCILIATION_REQUIRED"])
def test_terminal_replay_returns_without_effects(
    state: VerifyFirstAdminEmailTerminalState,
) -> None:
    events: list[str] = []
    idempotency = FakeIdempotencyRepository(existing=_started_record(state=state), events=events)
    discovery = FakeDiscovery(events=events)
    cognito = FakeCognitoRepository(events=events)
    audit = FakeAuditRepository(events=events)
    clock = FakeClock()
    ids = FakeIdGenerator()
    service, _, _, _, _ = _service(
        idempotency=idempotency,
        discovery=discovery,
        cognito=cognito,
        audit=audit,
        clock=clock,
        ids=ids,
    )

    result = _verify(service, actor_id="github:different")

    assert result == VerifyFirstAdminEmailResult(
        operation_id=_OPERATION_ID,
        state=state,
        replayed=True,
    )
    assert events == ["idempotency:get"]
    assert idempotency.transitions == []
    assert cognito.calls == []
    assert audit.gets == []
    assert ids.calls == 0
    assert clock.calls == 0


def test_started_replay_preserves_original_metadata_and_actor() -> None:
    idempotency = FakeIdempotencyRepository(existing=_started_record())
    discovery = FakeDiscovery(_discovery("ALREADY_VERIFIED"))
    service, _, audit, _, ids = _service(idempotency=idempotency, discovery=discovery)

    result = _verify(service, actor_id="github:different")

    assert result.replayed is True
    assert ids.calls == 0
    assert idempotency.created == []
    written = audit.puts[0]["event"]
    assert isinstance(written, dict)
    assert written["eventId"] == _EVENT_ID
    assert written["correlationId"] == _CORRELATION_ID
    assert written["occurredAt"] == _OCCURRED_AT
    assert written["expiresAt"] == _AUDIT_EXPIRES_AT
    assert written["actorId"] == "github:original"


def test_already_verified_writes_and_confirms_success_before_completed() -> None:
    events: list[str] = []
    idempotency = FakeIdempotencyRepository(events=events)
    discovery = FakeDiscovery(_discovery("ALREADY_VERIFIED"), events=events)
    cognito = FakeCognitoRepository(events=events)
    audit = FakeAuditRepository(events=events)
    service, _, _, _, _ = _service(
        idempotency=idempotency,
        discovery=discovery,
        cognito=cognito,
        audit=audit,
    )

    result = _verify(service)

    assert result.state == "COMPLETED"
    assert cognito.calls == []
    assert audit.puts[0]["event"] == build_first_admin_email_verification_audit_event(
        user_id=_USER_ID,
        actor_id="github:caller",
        event_id=_EVENT_ID,
        operation_id=_OPERATION_ID,
        correlation_id=_CORRELATION_ID,
        occurred_at=_OCCURRED_AT,
        result="SUCCESS",
        expires_at=_AUDIT_EXPIRES_AT,
    )
    assert events.index("audit:get") < events.index("idempotency:transition:COMPLETED")


def test_incompatible_success_audit_prevents_completed_and_never_mutates() -> None:
    incompatible = {**_audit_event(result="SUCCESS"), "actorId": "github:other"}
    idempotency = FakeIdempotencyRepository()
    discovery = FakeDiscovery(_discovery("ALREADY_VERIFIED"))
    cognito = FakeCognitoRepository()
    audit = FakeAuditRepository(replace_put_with=incompatible)
    service, _, _, _, _ = _service(
        idempotency=idempotency,
        discovery=discovery,
        cognito=cognito,
        audit=audit,
    )

    result = _verify(service)

    assert result.state == "RECONCILIATION_REQUIRED"
    assert [transition["next_state"] for transition in idempotency.transitions] == [
        "RECONCILIATION_REQUIRED"
    ]
    assert cognito.calls == []
    assert len(audit.puts) == 1


def test_initial_reconciliation_without_authoritative_user_id_skips_audit_and_mutation() -> None:
    idempotency = FakeIdempotencyRepository()
    discovery = FakeDiscovery(_discovery("RECONCILIATION_REQUIRED"))
    service, cognito, audit, _, _ = _service(
        idempotency=idempotency,
        discovery=discovery,
    )

    result = _verify(service)

    assert result.state == "RECONCILIATION_REQUIRED"
    assert cognito.calls == []
    assert audit.puts == []
    assert audit.gets == []


def test_initial_reconciliation_with_authoritative_user_id_writes_failure_audit() -> None:
    idempotency = FakeIdempotencyRepository()
    discovery = FakeDiscovery(
        _discovery(
            "RECONCILIATION_REQUIRED",
            authoritative_user_id=_USER_ID,
        )
    )
    service, cognito, audit, _, _ = _service(
        idempotency=idempotency,
        discovery=discovery,
    )

    result = _verify(service)

    assert result.state == "RECONCILIATION_REQUIRED"
    assert cognito.calls == []
    assert audit.puts == [
        {
            "audit_table_name": "audit-table",
            "event": _audit_event(result="FAILURE", actor_id="github:caller"),
        }
    ]
    assert len(audit.gets) == 1


@pytest.mark.parametrize("audit_error", [RuntimeError("explicit"), _ambiguous_error()])
def test_initial_reconciliation_failure_audit_error_does_not_block_terminal(
    audit_error: Exception,
) -> None:
    idempotency = FakeIdempotencyRepository()
    discovery = FakeDiscovery(
        _discovery(
            "RECONCILIATION_REQUIRED",
            authoritative_user_id=_USER_ID,
        )
    )
    audit = FakeAuditRepository(put_error=audit_error)
    service, cognito, _, _, _ = _service(
        idempotency=idempotency,
        discovery=discovery,
        audit=audit,
    )

    assert _verify(service).state == "RECONCILIATION_REQUIRED"
    assert cognito.calls == []


def test_initial_reconciliation_incompatible_failure_audit_is_not_overwritten() -> None:
    incompatible = {**_audit_event(result="FAILURE"), "operationId": "other"}
    audit = FakeAuditRepository(replace_put_with=incompatible)
    discovery = FakeDiscovery(
        _discovery(
            "RECONCILIATION_REQUIRED",
            authoritative_user_id=_USER_ID,
        )
    )
    service, cognito, _, _, _ = _service(
        idempotency=FakeIdempotencyRepository(),
        discovery=discovery,
        audit=audit,
    )

    assert _verify(service).state == "RECONCILIATION_REQUIRED"
    assert len(audit.puts) == 1
    assert audit.current is incompatible
    assert cognito.calls == []


def test_needs_verification_mutates_once_reads_back_and_completes_after_success_audit() -> None:
    events: list[str] = []
    idempotency = FakeIdempotencyRepository(events=events)
    discovery = FakeDiscovery(
        _discovery("NEEDS_VERIFICATION"),
        _discovery("ALREADY_VERIFIED"),
        events=events,
    )
    cognito = FakeCognitoRepository(events=events)
    audit = FakeAuditRepository(events=events)
    service, _, _, _, _ = _service(
        idempotency=idempotency,
        discovery=discovery,
        cognito=cognito,
        audit=audit,
    )

    result = _verify(service)

    assert result.state == "COMPLETED"
    assert cognito.calls == [{"user_pool_id": "us-east-1_example", "user_id": _USER_ID}]
    assert discovery.calls == 2
    assert audit.puts[0]["event"] == build_first_admin_email_verification_audit_event(
        user_id=_USER_ID,
        actor_id="github:caller",
        event_id=_EVENT_ID,
        operation_id=_OPERATION_ID,
        correlation_id=_CORRELATION_ID,
        occurred_at=_OCCURRED_AT,
        result="SUCCESS",
        expires_at=_AUDIT_EXPIRES_AT,
    )
    assert events.index("cognito:set_email_verified") < events.index("audit:put")


def test_read_back_reconciliation_writes_failure_and_never_mutates_twice() -> None:
    idempotency = FakeIdempotencyRepository()
    discovery = FakeDiscovery(
        _discovery("NEEDS_VERIFICATION"),
        _discovery(
            "RECONCILIATION_REQUIRED",
            authoritative_user_id=_USER_ID,
        ),
    )
    service, cognito, audit, _, _ = _service(
        idempotency=idempotency,
        discovery=discovery,
    )

    result = _verify(service)

    assert result.state == "RECONCILIATION_REQUIRED"
    assert len(cognito.calls) == 1
    assert audit.puts[0]["event"] == build_first_admin_email_verification_audit_event(
        user_id=_USER_ID,
        actor_id="github:caller",
        event_id=_EVENT_ID,
        operation_id=_OPERATION_ID,
        correlation_id=_CORRELATION_ID,
        occurred_at=_OCCURRED_AT,
        result="FAILURE",
        expires_at=_AUDIT_EXPIRES_AT,
    )


def test_read_back_reconciliation_without_authoritative_user_id_skips_audit() -> None:
    idempotency = FakeIdempotencyRepository()
    discovery = FakeDiscovery(
        _discovery("NEEDS_VERIFICATION"),
        _discovery("RECONCILIATION_REQUIRED"),
    )
    service, cognito, audit, _, _ = _service(
        idempotency=idempotency,
        discovery=discovery,
    )

    result = _verify(service)

    assert result.state == "RECONCILIATION_REQUIRED"
    assert len(cognito.calls) == 1
    assert audit.puts == []
    assert audit.gets == []


def test_read_back_still_needs_verification_preserves_started_without_second_mutation() -> None:
    idempotency = FakeIdempotencyRepository()
    discovery = FakeDiscovery(
        _discovery("NEEDS_VERIFICATION"),
        _discovery("NEEDS_VERIFICATION"),
    )
    service, cognito, audit, _, _ = _service(
        idempotency=idempotency,
        discovery=discovery,
    )

    with pytest.raises(RuntimeError, match="email verification was not confirmed"):
        _verify(service)

    assert len(cognito.calls) == 1
    assert audit.puts == []
    assert idempotency.transitions == []


@pytest.mark.parametrize("result", ["SUCCESS", "FAILURE"])
def test_started_replay_with_canonical_audit_is_barrier_against_cognito(
    result: Literal["SUCCESS", "FAILURE"],
) -> None:
    events: list[str] = []
    idempotency = FakeIdempotencyRepository(existing=_started_record(), events=events)
    discovery = FakeDiscovery(_discovery("NEEDS_VERIFICATION"), events=events)
    cognito = FakeCognitoRepository(events=events)
    audit = FakeAuditRepository(existing=_audit_event(result=result), events=events)
    service, _, _, _, ids = _service(
        idempotency=idempotency,
        discovery=discovery,
        cognito=cognito,
        audit=audit,
    )

    response = _verify(service)

    expected_state = "COMPLETED" if result == "SUCCESS" else "RECONCILIATION_REQUIRED"
    assert response.state == expected_state
    assert response.replayed is True
    assert events.index("discovery") < events.index("audit:get")
    assert cognito.calls == []
    assert audit.puts == []
    assert ids.calls == 0


def test_started_replay_with_incompatible_audit_never_calls_cognito() -> None:
    incompatible = {**_audit_event(result="SUCCESS"), "operationId": "other-operation"}
    idempotency = FakeIdempotencyRepository(existing=_started_record())
    discovery = FakeDiscovery(_discovery("NEEDS_VERIFICATION"))
    cognito = FakeCognitoRepository()
    audit = FakeAuditRepository(existing=incompatible)
    service, _, _, _, _ = _service(
        idempotency=idempotency,
        discovery=discovery,
        cognito=cognito,
        audit=audit,
    )

    result = _verify(service)

    assert result.state == "RECONCILIATION_REQUIRED"
    assert cognito.calls == []
    assert audit.puts == []


@pytest.mark.parametrize(
    "create_error",
    [_aws_error("ConditionalCheckFailedException"), _ambiguous_error()],
)
def test_uncertain_started_create_reuses_consistently_read_compatible_record(
    create_error: Exception,
) -> None:
    persisted = _started_record(state="COMPLETED")
    idempotency = FakeIdempotencyRepository(
        create_error=create_error,
        get_outcomes=[None, persisted],
    )
    service, cognito, audit, _, ids = _service(
        idempotency=idempotency,
        discovery=FakeDiscovery(),
    )

    result = _verify(service)

    assert result == VerifyFirstAdminEmailResult(_OPERATION_ID, "COMPLETED", True)
    assert len(idempotency.get_calls) == 2
    assert ids.calls == 2
    assert cognito.calls == []
    assert audit.gets == []


def test_uncertain_started_create_with_incompatible_record_has_no_downstream_effects() -> None:
    incompatible = {**_started_record(), "operationId": "other"}
    idempotency = FakeIdempotencyRepository(
        create_error=_aws_error("ConditionalCheckFailedException"),
        get_outcomes=[None, incompatible],
    )
    discovery = FakeDiscovery(_discovery("ALREADY_VERIFIED"))
    service, cognito, audit, _, _ = _service(
        idempotency=idempotency,
        discovery=discovery,
    )

    with pytest.raises(ValueError):
        _verify(service)

    assert discovery.calls == 0
    assert cognito.calls == []
    assert audit.puts == []


@pytest.mark.parametrize("read_outcome", [None, RuntimeError("read unavailable")])
def test_ambiguous_started_create_without_confirmed_record_propagates_original(
    read_outcome: dict[str, object] | None | Exception,
) -> None:
    write_error = _ambiguous_error()
    idempotency = FakeIdempotencyRepository(
        create_error=write_error,
        get_outcomes=[None, read_outcome],
    )
    discovery = FakeDiscovery(_discovery("ALREADY_VERIFIED"))
    service, cognito, _, _, _ = _service(
        idempotency=idempotency,
        discovery=discovery,
    )

    with pytest.raises(Exception) as raised:
        _verify(service)

    if read_outcome is None:
        assert raised.value is write_error
    assert discovery.calls == 0
    assert cognito.calls == []


def test_explicit_cognito_failure_propagates_without_immediate_read_back() -> None:
    error = _aws_error("TooManyRequestsException", operation="AdminUpdateUserAttributes")
    discovery = FakeDiscovery(_discovery("NEEDS_VERIFICATION"))
    cognito = FakeCognitoRepository(error=error)
    idempotency = FakeIdempotencyRepository()
    service, _, audit, _, _ = _service(
        idempotency=idempotency,
        discovery=discovery,
        cognito=cognito,
    )

    with pytest.raises(ClientError) as raised:
        _verify(service)

    assert raised.value is error
    assert discovery.calls == 1
    assert len(cognito.calls) == 1
    assert audit.puts == []
    assert idempotency.transitions == []


@pytest.mark.parametrize(
    ("read_back", "expected_state", "raises_original"),
    [
        (_discovery("ALREADY_VERIFIED"), "COMPLETED", False),
        (_discovery("NEEDS_VERIFICATION"), None, True),
        (
            _discovery(
                "RECONCILIATION_REQUIRED",
                authoritative_user_id=_USER_ID,
            ),
            "RECONCILIATION_REQUIRED",
            False,
        ),
    ],
)
def test_ambiguous_cognito_mutation_reconciles_without_second_mutation(
    read_back: VerifyFirstAdminEmailDiscoveryResult,
    expected_state: str | None,
    raises_original: bool,
) -> None:
    error = _ambiguous_error()
    discovery = FakeDiscovery(_discovery("NEEDS_VERIFICATION"), read_back)
    cognito = FakeCognitoRepository(error=error)
    idempotency = FakeIdempotencyRepository()
    service, _, _, _, _ = _service(
        idempotency=idempotency,
        discovery=discovery,
        cognito=cognito,
    )

    if raises_original:
        with pytest.raises(ReadTimeoutError) as raised:
            _verify(service)
        assert raised.value is error
    else:
        assert _verify(service).state == expected_state

    assert discovery.calls == 2
    assert len(cognito.calls) == 1


def test_cognito_internal_error_uses_authoritative_read_back() -> None:
    error = _aws_error("InternalErrorException", operation="AdminUpdateUserAttributes")
    discovery = FakeDiscovery(
        _discovery("NEEDS_VERIFICATION"),
        _discovery("ALREADY_VERIFIED"),
    )
    cognito = FakeCognitoRepository(error=error)
    service, _, _, _, _ = _service(
        idempotency=FakeIdempotencyRepository(),
        discovery=discovery,
        cognito=cognito,
    )

    assert _verify(service).state == "COMPLETED"
    assert discovery.calls == 2
    assert len(cognito.calls) == 1


@pytest.mark.parametrize("mutation_error", [None, _ambiguous_error()])
def test_inconclusive_cognito_read_back_converges_to_reconciliation(
    mutation_error: Exception | None,
) -> None:
    discovery = FakeDiscovery(
        _discovery("NEEDS_VERIFICATION"),
        RuntimeError("sanitized read failure"),
    )
    cognito = FakeCognitoRepository(error=mutation_error)
    idempotency = FakeIdempotencyRepository()
    service, _, audit, _, _ = _service(
        idempotency=idempotency,
        discovery=discovery,
        cognito=cognito,
    )

    result = _verify(service)

    assert result.state == "RECONCILIATION_REQUIRED"
    assert len(cognito.calls) == 1
    event = audit.puts[0]["event"]
    assert isinstance(event, dict)
    assert event["result"] == "FAILURE"


def test_alias_exists_converges_to_reconciliation_without_read_back() -> None:
    discovery = FakeDiscovery(_discovery("NEEDS_VERIFICATION"))
    cognito = FakeCognitoRepository(
        error=_aws_error("AliasExistsException", operation="AdminUpdateUserAttributes")
    )
    service, _, audit, _, _ = _service(
        idempotency=FakeIdempotencyRepository(),
        discovery=discovery,
        cognito=cognito,
    )

    assert _verify(service).state == "RECONCILIATION_REQUIRED"
    assert discovery.calls == 1
    assert len(cognito.calls) == 1
    event = audit.puts[0]["event"]
    assert isinstance(event, dict)
    assert event["result"] == "FAILURE"


@pytest.mark.parametrize(
    "put_error",
    [_aws_error("ConditionalCheckFailedException"), _ambiguous_error()],
)
def test_uncertain_success_audit_with_identical_event_is_confirmed(
    put_error: Exception,
) -> None:
    audit = FakeAuditRepository(
        put_error=put_error,
        get_outcomes=[_audit_event(result="SUCCESS", actor_id="github:caller")],
    )
    service, _, _, _, _ = _service(
        idempotency=FakeIdempotencyRepository(),
        discovery=FakeDiscovery(_discovery("ALREADY_VERIFIED")),
        audit=audit,
    )

    assert _verify(service).state == "COMPLETED"
    assert len(audit.puts) == 1
    assert len(audit.gets) == 1


@pytest.mark.parametrize("actual", [None, {**_audit_event(result="SUCCESS"), "actorId": "other"}])
def test_uncertain_success_audit_never_fabricates_completed(
    actual: dict[str, object] | None,
) -> None:
    write_error = _ambiguous_error()
    idempotency = FakeIdempotencyRepository()
    audit = FakeAuditRepository(put_error=write_error, get_outcomes=[actual])
    service, cognito, _, _, _ = _service(
        idempotency=idempotency,
        discovery=FakeDiscovery(_discovery("ALREADY_VERIFIED")),
        audit=audit,
    )

    if actual is None:
        with pytest.raises(ReadTimeoutError) as raised:
            _verify(service)
        assert raised.value is write_error
        assert idempotency.transitions == []
    else:
        assert _verify(service).state == "RECONCILIATION_REQUIRED"
    assert cognito.calls == []
    assert len(audit.puts) == 1


def test_success_audit_inconclusive_consistent_read_prevents_completed() -> None:
    read_error = RuntimeError("audit read unavailable")
    idempotency = FakeIdempotencyRepository()
    audit = FakeAuditRepository(get_outcomes=[read_error])
    service, cognito, _, _, _ = _service(
        idempotency=idempotency,
        discovery=FakeDiscovery(_discovery("ALREADY_VERIFIED")),
        audit=audit,
    )

    with pytest.raises(RuntimeError) as raised:
        _verify(service)

    assert raised.value is read_error
    assert idempotency.transitions == []
    assert cognito.calls == []


@pytest.mark.parametrize("audit_failure", [_ambiguous_error(), RuntimeError("audit unavailable")])
def test_failure_audit_unavailability_does_not_block_exceptional_terminal(
    audit_failure: Exception,
) -> None:
    idempotency = FakeIdempotencyRepository()
    audit = FakeAuditRepository(put_error=audit_failure)
    service, cognito, _, _, _ = _service(
        idempotency=idempotency,
        discovery=FakeDiscovery(
            _discovery("NEEDS_VERIFICATION"),
            _discovery(
                "RECONCILIATION_REQUIRED",
                authoritative_user_id=_USER_ID,
            ),
        ),
        audit=audit,
    )

    assert _verify(service).state == "RECONCILIATION_REQUIRED"
    assert len(cognito.calls) == 1
    if isinstance(audit_failure, ReadTimeoutError):
        assert len(audit.gets) == 1


@pytest.mark.parametrize(
    "transition_error",
    [_aws_error("ConditionalCheckFailedException"), _ambiguous_error()],
)
def test_uncertain_terminal_transition_is_confirmed_by_consistent_read(
    transition_error: Exception,
) -> None:
    terminal = _started_record(state="COMPLETED")
    idempotency = FakeIdempotencyRepository(
        transition_error=transition_error,
        get_outcomes=[None, terminal],
    )
    service, _, _, _, _ = _service(
        idempotency=idempotency,
        discovery=FakeDiscovery(_discovery("ALREADY_VERIFIED")),
    )

    assert _verify(service).state == "COMPLETED"
    assert len(idempotency.get_calls) == 2


def test_uncertain_terminal_transition_still_started_propagates_without_repeating_effects() -> None:
    transition_error = _ambiguous_error()
    idempotency = FakeIdempotencyRepository(
        transition_error=transition_error,
        get_outcomes=[None, _started_record()],
    )
    discovery = FakeDiscovery(
        _discovery("NEEDS_VERIFICATION"),
        _discovery("ALREADY_VERIFIED"),
    )
    service, cognito, audit, _, _ = _service(
        idempotency=idempotency,
        discovery=discovery,
    )

    with pytest.raises(ReadTimeoutError) as raised:
        _verify(service)

    assert raised.value is transition_error
    assert len(cognito.calls) == 1
    assert len(audit.puts) == 1


def test_uncertain_reconciliation_transition_still_started_never_mutates() -> None:
    transition_error = _ambiguous_error()
    idempotency = FakeIdempotencyRepository(
        transition_error=transition_error,
        get_outcomes=[None, _started_record()],
    )
    discovery = FakeDiscovery(_discovery("RECONCILIATION_REQUIRED"))
    service, cognito, audit, _, _ = _service(
        idempotency=idempotency,
        discovery=discovery,
    )

    with pytest.raises(ReadTimeoutError) as raised:
        _verify(service)

    assert raised.value is transition_error
    assert discovery.calls == 1
    assert cognito.calls == []
    assert audit.puts == []
