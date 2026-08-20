from collections.abc import Iterable
from datetime import UTC, datetime

import pytest

from tools.bootstrap_admin.idempotency import IdempotencyConflictError
from tools.bootstrap_admin.resume_context import InvalidResumeInvitationRecordError
from tools.bootstrap_admin.resume_discovery import (
    FirstAdminInvitationTarget,
    ResumeDiscoveryResult,
    ResumeInvitationOperationIdConflictError,
)
from tools.bootstrap_admin.resume_idempotency import (
    build_resume_invitation_started_record,
)
from tools.bootstrap_admin.resume_service import (
    ResumeInvitationService,
    ResumeInvitationServiceConfig,
)

_OPERATION_ID = "123e4567-e89b-42d3-a456-426614174000"
_CORRELATION_ID = "223e4567-e89b-42d3-a456-426614174001"
_OTHER_CORRELATION_ID = "323e4567-e89b-42d3-a456-426614174002"
_USER_ID = "423e4567-e89b-42d3-a456-426614174003"
_BASE = datetime(2026, 8, 20, 13, 45, 12, 347891, tzinfo=UTC)
_TRANSITION_TIME = datetime(2026, 8, 20, 13, 46, 0, 123456, tzinfo=UTC)
_CREATED_AT = "2026-08-20T13:45:12.347Z"
_EXPIRATION = 1_787_319_912


class AwsError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        http_status: int | None = None,
    ) -> None:
        super().__init__(code)
        self.response: dict[str, object] = {"Error": {"Code": code}}
        if http_status is not None:
            self.response["ResponseMetadata"] = {"HTTPStatusCode": http_status}


class FakeClock:
    def __init__(self, values: Iterable[datetime]) -> None:
        self._values = iter(values)
        self.calls = 0

    def now(self) -> datetime:
        self.calls += 1
        return next(self._values)


class FakeIdGenerator:
    def __init__(self, values: Iterable[str]) -> None:
        self._values = iter(values)
        self.calls = 0

    def new_uuid4(self) -> str:
        self.calls += 1
        return next(self._values)


class FakeIdempotencyRepository:
    def __init__(self, get_outcomes: Iterable[object] = (None,)) -> None:
        self._get_outcomes = iter(get_outcomes)
        self.get_calls: list[str] = []
        self.created_records: list[dict[str, object]] = []
        self.create_error: BaseException | None = None
        self.transition_errors: list[BaseException | None] = []
        self.transition_calls: list[dict[str, object]] = []

    def get(self, record_id: str) -> dict[str, object] | None:
        self.get_calls.append(record_id)
        outcome = next(self._get_outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        assert outcome is None or isinstance(outcome, dict)
        return outcome

    def create_started(self, record: dict[str, object]) -> None:
        self.created_records.append(record)
        if self.create_error is not None:
            raise self.create_error

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
        self.transition_calls.append(
            {
                "record_id": record_id,
                "operation": operation,
                "current_state": current_state,
                "next_state": next_state,
                "updated_at": updated_at,
                "cognito_sub": cognito_sub,
            }
        )
        if self.transition_errors:
            error = self.transition_errors.pop(0)
            if error is not None:
                raise error


class FakeDiscovery:
    def __init__(self, result: ResumeDiscoveryResult) -> None:
        self.result = result
        self.error: BaseException | None = None
        self.calls: list[str] = []

    def discover(self, *, resume_operation_id: str) -> ResumeDiscoveryResult:
        self.calls.append(resume_operation_id)
        if self.error is not None:
            raise self.error
        return self.result


class FakeInvitationSender:
    def __init__(self, outcomes: Iterable[BaseException | None] = (None,)) -> None:
        self._outcomes = iter(outcomes)
        self.calls: list[dict[str, str]] = []

    def resend_invitation(self, *, user_pool_id: str, user_id: str) -> None:
        self.calls.append({"user_pool_id": user_pool_id, "user_id": user_id})
        outcome = next(self._outcomes)
        if outcome is not None:
            raise outcome


def _target(*, status: str = "INVITED") -> FirstAdminInvitationTarget:
    return FirstAdminInvitationTarget(
        user_id=_USER_ID,
        email="admin@example.com",
        cognito_sub="cognito-sub-123",
        status=status,  # type: ignore[arg-type]
    )


def _discovery_result(status: str = "INVITED_CONSISTENT") -> ResumeDiscoveryResult:
    if status == "RECONCILIATION_REQUIRED":
        return ResumeDiscoveryResult(status=status, target=None)
    target_status = "ACTIVE" if status == "ACTIVE_CONSISTENT" else "INVITED"
    return ResumeDiscoveryResult(
        status=status,  # type: ignore[arg-type]
        target=_target(status=target_status),
    )


def _record(
    *,
    state: str = "STARTED",
    correlation_id: str = _CORRELATION_ID,
    actor_id: str = "github:original",
    created_at: str = _CREATED_AT,
    expiration: int = _EXPIRATION,
    updated_at: str | None = None,
) -> dict[str, object]:
    record = build_resume_invitation_started_record(
        environment="dev",
        operation_id=_OPERATION_ID,
        correlation_id=correlation_id,
        actor_id=actor_id,
        created_at=created_at,
        expiration=expiration,
    )
    record["state"] = state
    if updated_at is not None:
        record["updatedAt"] = updated_at
    return record


def _service(
    *,
    repository: FakeIdempotencyRepository | None = None,
    discovery: FakeDiscovery | None = None,
    sender: FakeInvitationSender | None = None,
    clock_values: Iterable[datetime] = (_BASE, _TRANSITION_TIME),
    id_values: Iterable[str] = (_CORRELATION_ID,),
) -> tuple[
    ResumeInvitationService,
    FakeIdempotencyRepository,
    FakeDiscovery,
    FakeInvitationSender,
    FakeClock,
    FakeIdGenerator,
]:
    repository = repository or FakeIdempotencyRepository()
    discovery = discovery or FakeDiscovery(_discovery_result())
    sender = sender or FakeInvitationSender()
    clock = FakeClock(clock_values)
    ids = FakeIdGenerator(id_values)
    service = ResumeInvitationService(
        config=ResumeInvitationServiceConfig(
            environment="dev",
            user_pool_id="pool-123",
        ),
        clock=clock,
        id_generator=ids,
        idempotency_repository=repository,
        invitation_sender=sender,
        discovery=discovery,
    )
    return service, repository, discovery, sender, clock, ids


def _resume(service: ResumeInvitationService, *, actor_id: str = "github:original"):
    return service.resume_first_admin_invitation(
        operation_id=_OPERATION_ID,
        actor_id=actor_id,
    )


def test_new_invited_operation_creates_exact_started_and_completes() -> None:
    service, repository, discovery, sender, clock, ids = _service()

    result = _resume(service)

    assert result.operation_id == _OPERATION_ID
    assert result.state == "COMPLETED"
    assert result.replayed is False
    assert repository.created_records == [_record()]
    assert repository.get_calls == [
        "NONHTTP#dev#resume-first-admin-invitation#first-admin#"
        f"{_OPERATION_ID}"
    ]
    assert discovery.calls == [_OPERATION_ID]
    assert sender.calls == [{"user_pool_id": "pool-123", "user_id": _USER_ID}]
    assert clock.calls == 2
    assert ids.calls == 1


def test_new_operation_persists_actor_and_exact_24_hour_expiration() -> None:
    service, repository, _, _, _, _ = _service()

    _resume(service, actor_id="github:new-actor")

    record = repository.created_records[0]
    assert record["actorId"] == "github:new-actor"
    assert record["correlationId"] == _CORRELATION_ID
    assert record["createdAt"] == _CREATED_AT
    assert record["updatedAt"] == _CREATED_AT
    assert record["expiration"] == _EXPIRATION


def test_operation_id_is_required_and_never_generated() -> None:
    service, repository, discovery, sender, clock, ids = _service()

    with pytest.raises(ValueError, match="canonical UUIDv4"):
        service.resume_first_admin_invitation(
            operation_id="invalid",
            actor_id="github:actor",
        )

    assert repository.get_calls == []
    assert discovery.calls == []
    assert sender.calls == []
    assert clock.calls == 0
    assert ids.calls == 0


def test_empty_actor_is_rejected_before_any_dependency() -> None:
    service, repository, discovery, sender, clock, ids = _service()

    with pytest.raises(ValueError, match="actor_id"):
        _resume(service, actor_id="")

    assert repository.get_calls == []
    assert discovery.calls == []
    assert sender.calls == []
    assert clock.calls == 0
    assert ids.calls == 0


def test_new_active_operation_completes_without_resend() -> None:
    discovery = FakeDiscovery(_discovery_result("ACTIVE_CONSISTENT"))
    service, repository, discovery, sender, clock, ids = _service(
        discovery=discovery
    )

    result = _resume(service)

    assert result.state == "COMPLETED"
    assert result.replayed is False
    assert sender.calls == []
    assert len(repository.transition_calls) == 1
    assert clock.calls == 2
    assert ids.calls == 1


def test_new_reconciliation_operation_transitions_without_resend() -> None:
    discovery = FakeDiscovery(_discovery_result("RECONCILIATION_REQUIRED"))
    service, repository, _, sender, clock, _ = _service(discovery=discovery)

    result = _resume(service)

    assert result.state == "RECONCILIATION_REQUIRED"
    assert result.replayed is False
    assert sender.calls == []
    assert repository.transition_calls[0]["next_state"] == (
        "RECONCILIATION_REQUIRED"
    )
    assert clock.calls == 2


@pytest.mark.parametrize("state", ["COMPLETED", "RECONCILIATION_REQUIRED"])
def test_terminal_replay_returns_immediately_without_effects(state: str) -> None:
    repository = FakeIdempotencyRepository([_record(state=state)])
    service, repository, discovery, sender, clock, ids = _service(
        repository=repository
    )

    result = _resume(service, actor_id="github:different-executor")

    assert result.state == state
    assert result.replayed is True
    assert discovery.calls == []
    assert sender.calls == []
    assert repository.created_records == []
    assert repository.transition_calls == []
    assert clock.calls == 0
    assert ids.calls == 0


def test_started_replay_preserves_metadata_and_runs_discovery() -> None:
    existing = _record(actor_id="github:original")
    repository = FakeIdempotencyRepository([existing])
    service, repository, discovery, sender, clock, ids = _service(
        repository=repository,
        clock_values=(_TRANSITION_TIME,),
        id_values=(),
    )

    result = _resume(service, actor_id="github:different-executor")

    assert result.replayed is True
    assert repository.created_records == []
    assert discovery.calls == [_OPERATION_ID]
    assert sender.calls == [{"user_pool_id": "pool-123", "user_id": _USER_ID}]
    assert clock.calls == 1
    assert ids.calls == 0
    assert existing["actorId"] == "github:original"
    assert existing["correlationId"] == _CORRELATION_ID


@pytest.mark.parametrize(
    "mutation",
    [
        {"id": "invalid-record-id"},
        {"operation": "bootstrap-admin"},
        {"correlationId": "invalid-uuid"},
    ],
)
def test_invalid_existing_record_fails_before_discovery(
    mutation: dict[str, object],
) -> None:
    existing = _record()
    existing.update(mutation)
    repository = FakeIdempotencyRepository([existing])
    service, repository, discovery, sender, clock, ids = _service(
        repository=repository
    )

    with pytest.raises(InvalidResumeInvitationRecordError):
        _resume(service)

    assert discovery.calls == []
    assert sender.calls == []
    assert repository.transition_calls == []
    assert clock.calls == 0
    assert ids.calls == 0


def test_existing_payload_mismatch_fails_before_discovery() -> None:
    existing = _record()
    existing["payloadHash"] = "different"
    repository = FakeIdempotencyRepository([existing])
    service, repository, discovery, sender, clock, ids = _service(
        repository=repository
    )

    with pytest.raises(IdempotencyConflictError):
        _resume(service)

    assert discovery.calls == []
    assert sender.calls == []
    assert repository.transition_calls == []
    assert clock.calls == 0
    assert ids.calls == 0


@pytest.mark.parametrize(
    "error",
    [
        ResumeInvitationOperationIdConflictError("operationId conflict"),
        RuntimeError("discovery failed"),
    ],
)
def test_discovery_error_propagates_and_keeps_started(error: BaseException) -> None:
    repository = FakeIdempotencyRepository([_record()])
    discovery = FakeDiscovery(_discovery_result())
    discovery.error = error
    service, repository, discovery, sender, clock, ids = _service(
        repository=repository,
        discovery=discovery,
        clock_values=(),
        id_values=(),
    )

    with pytest.raises(type(error), match=str(error)):
        _resume(service)

    assert repository.transition_calls == []
    assert sender.calls == []
    assert clock.calls == 0
    assert ids.calls == 0


@pytest.mark.parametrize(
    "error",
    [
        AwsError("CodeDeliveryFailureException"),
        AwsError("TooManyRequestsException"),
        AwsError("InternalErrorException"),
        TimeoutError("transport timeout"),
    ],
)
def test_non_user_not_found_resend_error_propagates_without_transition(
    error: BaseException,
) -> None:
    repository = FakeIdempotencyRepository([_record()])
    sender = FakeInvitationSender([error])
    service, repository, _, sender, clock, ids = _service(
        repository=repository,
        sender=sender,
        clock_values=(),
        id_values=(),
    )

    with pytest.raises(type(error), match=str(error)):
        _resume(service)

    assert len(sender.calls) == 1
    assert repository.transition_calls == []
    assert clock.calls == 0
    assert ids.calls == 0


def test_user_not_found_resend_transitions_to_reconciliation() -> None:
    repository = FakeIdempotencyRepository([_record()])
    sender = FakeInvitationSender([AwsError("UserNotFoundException")])
    service, repository, _, sender, clock, ids = _service(
        repository=repository,
        sender=sender,
        clock_values=(_TRANSITION_TIME,),
        id_values=(),
    )

    result = _resume(service)

    assert result.state == "RECONCILIATION_REQUIRED"
    assert result.replayed is True
    assert len(sender.calls) == 1
    assert repository.transition_calls[0]["next_state"] == (
        "RECONCILIATION_REQUIRED"
    )
    assert clock.calls == 1
    assert ids.calls == 0


def test_separate_invocations_can_retry_resend_once_each() -> None:
    sender = FakeInvitationSender(
        [AwsError("CodeDeliveryFailureException"), None]
    )
    first_repository = FakeIdempotencyRepository([_record()])
    first_service, _, _, sender, first_clock, _ = _service(
        repository=first_repository,
        sender=sender,
        clock_values=(),
        id_values=(),
    )
    with pytest.raises(AwsError, match="CodeDeliveryFailureException"):
        _resume(first_service)

    second_repository = FakeIdempotencyRepository([_record()])
    second_service, _, _, sender, second_clock, _ = _service(
        repository=second_repository,
        sender=sender,
        clock_values=(_TRANSITION_TIME,),
        id_values=(),
    )
    result = _resume(second_service)

    assert result.state == "COMPLETED"
    assert len(sender.calls) == 2
    assert first_clock.calls == 0
    assert second_clock.calls == 1


@pytest.mark.parametrize(
    "create_error",
    [
        AwsError("ConditionalCheckFailedException"),
        AwsError("InternalServerError", http_status=500),
    ],
)
@pytest.mark.parametrize(
    ("persisted_record", "expected_replayed"),
    [
        (_record(), False),
        (_record(correlation_id=_OTHER_CORRELATION_ID), True),
        (_record(updated_at="2026-08-20T14:00:00.000Z"), False),
    ],
)
def test_create_error_adopts_valid_started_and_classifies_replayed_by_metadata(
    create_error: BaseException,
    persisted_record: dict[str, object],
    expected_replayed: bool,
) -> None:
    repository = FakeIdempotencyRepository([None, persisted_record])
    repository.create_error = create_error
    service, repository, _, sender, clock, ids = _service(repository=repository)

    result = _resume(service)

    assert result.state == "COMPLETED"
    assert result.replayed is expected_replayed
    assert len(repository.created_records) == 1
    assert len(repository.get_calls) == 2
    assert len(sender.calls) == 1
    assert clock.calls == 2
    assert ids.calls == 1


@pytest.mark.parametrize(
    ("persisted_record", "expected_replayed"),
    [
        (_record(state="COMPLETED"), False),
        (
            _record(
                state="COMPLETED",
                correlation_id=_OTHER_CORRELATION_ID,
                actor_id="github:other",
            ),
            True,
        ),
    ],
)
def test_create_error_adopts_terminal_with_attempt_metadata_semantics(
    persisted_record: dict[str, object],
    expected_replayed: bool,
) -> None:
    repository = FakeIdempotencyRepository([None, persisted_record])
    repository.create_error = AwsError("ConditionalCheckFailedException")
    service, repository, discovery, sender, clock, ids = _service(
        repository=repository,
        clock_values=(_BASE,),
    )

    result = _resume(service)

    assert result.state == "COMPLETED"
    assert result.replayed is expected_replayed
    assert discovery.calls == []
    assert sender.calls == []
    assert repository.transition_calls == []
    assert clock.calls == 1
    assert ids.calls == 1


@pytest.mark.parametrize(
    "create_error",
    [
        AwsError("ConditionalCheckFailedException"),
        AwsError("InternalServerError", http_status=500),
    ],
)
def test_create_error_with_missing_reconciled_record_propagates_original(
    create_error: BaseException,
) -> None:
    repository = FakeIdempotencyRepository([None, None])
    repository.create_error = create_error
    service, repository, discovery, sender, _, _ = _service(
        repository=repository,
        clock_values=(_BASE,),
    )

    with pytest.raises(type(create_error), match=str(create_error)):
        _resume(service)

    assert len(repository.created_records) == 1
    assert len(repository.get_calls) == 2
    assert discovery.calls == []
    assert sender.calls == []


def test_create_error_reconciliation_read_failure_propagates_read_error() -> None:
    read_error = RuntimeError("reconciliation read failed")
    repository = FakeIdempotencyRepository([None, read_error])
    repository.create_error = AwsError("ConditionalCheckFailedException")
    service, repository, discovery, sender, _, _ = _service(
        repository=repository,
        clock_values=(_BASE,),
    )

    with pytest.raises(RuntimeError, match="reconciliation read failed"):
        _resume(service)

    assert len(repository.created_records) == 1
    assert discovery.calls == []
    assert sender.calls == []


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ({"id": "invalid"}, InvalidResumeInvitationRecordError),
        ({"payloadHash": "different"}, IdempotencyConflictError),
    ],
)
def test_create_error_reconciled_record_must_be_structural_and_compatible(
    mutation: dict[str, object],
    expected_error: type[BaseException],
) -> None:
    persisted = _record()
    persisted.update(mutation)
    repository = FakeIdempotencyRepository([None, persisted])
    repository.create_error = AwsError("ConditionalCheckFailedException")
    service, repository, discovery, sender, _, _ = _service(
        repository=repository,
        clock_values=(_BASE,),
    )

    with pytest.raises(expected_error):
        _resume(service)

    assert len(repository.created_records) == 1
    assert discovery.calls == []
    assert sender.calls == []


def test_non_ambiguous_create_error_propagates_without_additional_get() -> None:
    repository = FakeIdempotencyRepository([None])
    repository.create_error = AwsError("ValidationException")
    service, repository, discovery, sender, _, _ = _service(
        repository=repository,
        clock_values=(_BASE,),
    )

    with pytest.raises(AwsError, match="ValidationException"):
        _resume(service)

    assert len(repository.created_records) == 1
    assert len(repository.get_calls) == 1
    assert discovery.calls == []
    assert sender.calls == []


@pytest.mark.parametrize(
    ("transition_error", "next_state"),
    [
        (AwsError("InternalServerError", http_status=500), "COMPLETED"),
        (AwsError("ConditionalCheckFailedException"), "COMPLETED"),
        (
            AwsError("InternalServerError", http_status=500),
            "RECONCILIATION_REQUIRED",
        ),
    ],
)
def test_cas_error_with_confirmed_next_state_is_successful(
    transition_error: BaseException,
    next_state: str,
) -> None:
    initial = _record()
    confirmed = _record(state=next_state)
    repository = FakeIdempotencyRepository([initial, confirmed])
    repository.transition_errors = [transition_error]
    discovery_status = (
        "RECONCILIATION_REQUIRED"
        if next_state == "RECONCILIATION_REQUIRED"
        else "ACTIVE_CONSISTENT"
    )
    service, repository, _, sender, clock, ids = _service(
        repository=repository,
        discovery=FakeDiscovery(_discovery_result(discovery_status)),
        clock_values=(_TRANSITION_TIME,),
        id_values=(),
    )

    result = _resume(service)

    assert result.state == next_state
    assert result.replayed is True
    assert len(repository.transition_calls) == 1
    assert len(repository.get_calls) == 2
    assert sender.calls == []
    assert clock.calls == 1
    assert ids.calls == 0


@pytest.mark.parametrize("reconciled", [None, _record(state="STARTED")])
def test_cas_error_not_confirmed_propagates_original(
    reconciled: dict[str, object] | None,
) -> None:
    transition_error = AwsError("InternalServerError", http_status=500)
    repository = FakeIdempotencyRepository([_record(), reconciled])
    repository.transition_errors = [transition_error]
    service, repository, _, sender, clock, _ = _service(
        repository=repository,
        discovery=FakeDiscovery(_discovery_result("ACTIVE_CONSISTENT")),
        clock_values=(_TRANSITION_TIME,),
        id_values=(),
    )

    with pytest.raises(AwsError, match="InternalServerError"):
        _resume(service)

    assert len(repository.transition_calls) == 1
    assert sender.calls == []
    assert clock.calls == 1


def test_cas_reconciliation_read_failure_propagates_read_error() -> None:
    repository = FakeIdempotencyRepository(
        [_record(), RuntimeError("CAS read failed")]
    )
    repository.transition_errors = [
        AwsError("ConditionalCheckFailedException")
    ]
    service, repository, _, _, _, _ = _service(
        repository=repository,
        discovery=FakeDiscovery(_discovery_result("ACTIVE_CONSISTENT")),
        clock_values=(_TRANSITION_TIME,),
        id_values=(),
    )

    with pytest.raises(RuntimeError, match="CAS read failed"):
        _resume(service)

    assert len(repository.transition_calls) == 1


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ({"id": "invalid"}, InvalidResumeInvitationRecordError),
        ({"payloadHash": "different"}, IdempotencyConflictError),
    ],
)
def test_cas_reconciled_record_must_be_structural_and_payload_compatible(
    mutation: dict[str, object],
    expected_error: type[BaseException],
) -> None:
    reconciled = _record(state="COMPLETED")
    reconciled.update(mutation)
    repository = FakeIdempotencyRepository([_record(), reconciled])
    repository.transition_errors = [
        AwsError("ConditionalCheckFailedException")
    ]
    service, repository, _, _, _, _ = _service(
        repository=repository,
        discovery=FakeDiscovery(_discovery_result("ACTIVE_CONSISTENT")),
        clock_values=(_TRANSITION_TIME,),
        id_values=(),
    )

    with pytest.raises(expected_error):
        _resume(service)

    assert len(repository.transition_calls) == 1


def test_non_ambiguous_cas_error_propagates_without_reconciliation_get() -> None:
    repository = FakeIdempotencyRepository([_record()])
    repository.transition_errors = [AwsError("ValidationException")]
    service, repository, _, _, _, _ = _service(
        repository=repository,
        discovery=FakeDiscovery(_discovery_result("ACTIVE_CONSISTENT")),
        clock_values=(_TRANSITION_TIME,),
        id_values=(),
    )

    with pytest.raises(AwsError, match="ValidationException"):
        _resume(service)

    assert len(repository.transition_calls) == 1
    assert len(repository.get_calls) == 1


def test_transition_uses_resume_operation_and_never_writes_cognito_sub() -> None:
    repository = FakeIdempotencyRepository([_record()])
    service, repository, _, _, _, _ = _service(
        repository=repository,
        discovery=FakeDiscovery(_discovery_result("ACTIVE_CONSISTENT")),
        clock_values=(_TRANSITION_TIME,),
        id_values=(),
    )

    _resume(service)

    assert repository.transition_calls == [
        {
            "record_id": (
                "NONHTTP#dev#resume-first-admin-invitation#first-admin#"
                f"{_OPERATION_ID}"
            ),
            "operation": "resume-first-admin-invitation",
            "current_state": "STARTED",
            "next_state": "COMPLETED",
            "updated_at": "2026-08-20T13:46:00.123Z",
            "cognito_sub": None,
        }
    ]
