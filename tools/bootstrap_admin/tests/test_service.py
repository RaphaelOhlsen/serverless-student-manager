from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from botocore.exceptions import ConnectionClosedError  # type: ignore[import-untyped]

from tools.bootstrap_admin.audit import build_user_created_audit_event
from tools.bootstrap_admin.cognito_repository import (
    CognitoCreateResultError,
    CognitoIdentityValidationError,
)
from tools.bootstrap_admin.context import InvalidBootstrapRecordError
from tools.bootstrap_admin.idempotency import (
    IdempotencyConflictError,
    build_started_record,
)
from tools.bootstrap_admin.models import (
    build_cognito_projection,
    build_first_admin_bootstrap_marker,
    build_unique_email,
    build_user_profile,
)
from tools.bootstrap_admin.service import FirstAdminBootstrapService
from tools.bootstrap_admin.service_models import BootstrapResult, FirstAdminBootstrapConfig

_OPERATION_ID = "123e4567-e89b-42d3-a456-426614174000"
_USER_ID = "223e4567-e89b-42d3-a456-426614174001"
_EVENT_ID = "323e4567-e89b-42d3-a456-426614174002"
_CORRELATION_ID = "423e4567-e89b-42d3-a456-426614174003"

ProvisioningItems = tuple[
    dict[str, object] | None,
    dict[str, object] | None,
    dict[str, object] | None,
    dict[str, object] | None,
    dict[str, object] | None,
]
ExpectedProvisioningItems = tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]


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
        get_outcomes: list[object] | None = None,
        transition_outcomes: list[object] | None = None,
    ) -> None:
        self._events = events
        self._existing = existing
        self._get_outcomes = get_outcomes or []
        self._transition_outcomes = transition_outcomes or []
        self.get_calls: list[str] = []
        self.started_records: list[dict[str, object]] = []
        self.transitions: list[dict[str, object]] = []

    def get(self, record_id: str) -> dict[str, object] | None:
        self._events.append("idempotency:get")
        self.get_calls.append(record_id)
        if self._get_outcomes:
            outcome = self._get_outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            if outcome is None or isinstance(outcome, dict):
                return outcome
            raise AssertionError("unsupported idempotency get outcome")
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
        if self._transition_outcomes:
            outcome = self._transition_outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            if outcome is not None:
                raise AssertionError("unsupported transition outcome")


class FakeCognitoRepository:
    def __init__(
        self,
        events: list[str],
        *,
        get_outcomes: list[object] | None = None,
        create_outcomes: list[object] | None = None,
        delete_outcomes: list[object] | None = None,
        disable_outcomes: list[object] | None = None,
        resend_outcomes: list[object] | None = None,
    ) -> None:
        self._events = events
        self._get_outcomes = get_outcomes or []
        self._create_outcomes = create_outcomes or ["cognito-sub-123"]
        self._delete_outcomes = delete_outcomes if delete_outcomes is not None else [None]
        self._disable_outcomes = disable_outcomes if disable_outcomes is not None else [None]
        self._resend_outcomes = resend_outcomes if resend_outcomes is not None else []
        self.get_calls: list[dict[str, str]] = []
        self.create_calls: list[dict[str, str]] = []
        self.delete_calls: list[dict[str, str]] = []
        self.disable_calls: list[dict[str, str]] = []
        self.resend_calls: list[dict[str, str]] = []

    def get_existing_user_sub(
        self,
        *,
        user_pool_id: str,
        user_id: str,
        expected_email: str,
    ) -> str:
        self._events.append("cognito:get_existing")
        self.get_calls.append(
            {
                "user_pool_id": user_pool_id,
                "user_id": user_id,
                "expected_email": expected_email,
            }
        )
        if not self._get_outcomes:
            raise AssertionError("unexpected get_existing_user_sub call")
        outcome = self._get_outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        assert isinstance(outcome, str)
        return outcome

    def delete_user(self, *, user_pool_id: str, user_id: str) -> None:
        self._events.append("cognito:delete")
        self.delete_calls.append(
            {
                "user_pool_id": user_pool_id,
                "user_id": user_id,
            }
        )
        if not self._delete_outcomes:
            raise AssertionError("unexpected delete_user call")
        outcome = self._delete_outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome

    def disable_user(self, *, user_pool_id: str, user_id: str) -> None:
        self._events.append("cognito:disable")
        self.disable_calls.append(
            {
                "user_pool_id": user_pool_id,
                "user_id": user_id,
            }
        )
        if not self._disable_outcomes:
            raise AssertionError("unexpected disable_user call")
        outcome = self._disable_outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome

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
        if not self._create_outcomes:
            raise AssertionError("unexpected create_suppressed_user call")
        outcome = self._create_outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        assert isinstance(outcome, str)
        return outcome

    def resend_invitation(self, *, user_pool_id: str, user_id: str) -> None:
        self._events.append("cognito:resend")
        self.resend_calls.append(
            {
                "user_pool_id": user_pool_id,
                "user_id": user_id,
            }
        )
        if self._resend_outcomes:
            outcome = self._resend_outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            if outcome is not None:
                raise AssertionError("unsupported resend outcome")


class FakeProvisioningRepository:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.calls: list[dict[str, Any]] = []
        self.read_calls: list[dict[str, object]] = []
        self.user_profile_result: dict[str, object] | None = None
        self.unique_email_result: dict[str, object] | None = None
        self.cognito_projection_result: dict[str, object] | None = None
        self.bootstrap_marker_result: dict[str, object] | None = None
        self.audit_event_result: dict[str, object] | None = None
        self.read_error_at: str | None = None
        self.read_error: Exception | None = None
        self.read_error_after_persist_at: str | None = None
        self.read_error_after_persist: Exception | None = None
        self.persist_error: BaseException | None = None
        self.results_after_persist_error: ProvisioningItems | None = None

    def persist_first_admin_with_audit(self, **kwargs: Any) -> None:
        self._events.append("provisioning:persist")
        self.calls.append(dict(kwargs))
        if self.persist_error is not None:
            self.read_error_at = self.read_error_after_persist_at
            self.read_error = self.read_error_after_persist
            if self.results_after_persist_error is not None:
                (
                    self.user_profile_result,
                    self.unique_email_result,
                    self.cognito_projection_result,
                    self.bootstrap_marker_result,
                    self.audit_event_result,
                ) = self.results_after_persist_error
            raise self.persist_error

    def get_user_profile(
        self,
        *,
        users_table_name: str,
        user_id: str,
    ) -> dict[str, object] | None:
        self._record_read(
            "user_profile",
            users_table_name=users_table_name,
            user_id=user_id,
        )
        return self.user_profile_result

    def get_unique_email(
        self,
        *,
        users_table_name: str,
        normalized_email: str,
    ) -> dict[str, object] | None:
        self._record_read(
            "unique_email",
            users_table_name=users_table_name,
            normalized_email=normalized_email,
        )
        return self.unique_email_result

    def get_cognito_projection(
        self,
        *,
        users_table_name: str,
        cognito_sub: str,
    ) -> dict[str, object] | None:
        self._record_read(
            "cognito_projection",
            users_table_name=users_table_name,
            cognito_sub=cognito_sub,
        )
        return self.cognito_projection_result

    def get_bootstrap_marker(
        self,
        *,
        users_table_name: str,
    ) -> dict[str, object] | None:
        self._record_read(
            "bootstrap_marker",
            users_table_name=users_table_name,
        )
        return self.bootstrap_marker_result

    def get_audit_event(
        self,
        *,
        audit_table_name: str,
        user_id: str,
        occurred_at: str,
        event_id: str,
    ) -> dict[str, object] | None:
        self._record_read(
            "audit_event",
            audit_table_name=audit_table_name,
            user_id=user_id,
            occurred_at=occurred_at,
            event_id=event_id,
        )
        return self.audit_event_result

    def _record_read(self, name: str, **kwargs: object) -> None:
        self._events.append(f"provisioning:get:{name}")
        self.read_calls.append({"name": name, **kwargs})
        if self.read_error_at == name and self.read_error is not None:
            raise self.read_error


def _config() -> FirstAdminBootstrapConfig:
    return FirstAdminBootstrapConfig(
        environment="dev",
        user_pool_id="pool-123",
        users_table_name="users-table",
        audit_table_name="audit-table",
        audit_retention_days=90,
    )


def _existing_record(state: str) -> dict[str, object]:
    record = build_started_record(
        environment="dev",
        operation_id=_OPERATION_ID,
        correlation_id=_CORRELATION_ID,
        user_id=_USER_ID,
        event_id=_EVENT_ID,
        full_name="Maria da Silva",
        normalized_email="admin@example.com",
        created_at="2026-08-20T13:45:12.347Z",
        occurred_at="2026-08-20T13:45:12.347Z",
        audit_expires_at=1_795_009_512,
        actor_id="github:original",
        expiration=1_787_319_912,
    )
    record["state"] = state
    if state in {
        "COGNITO_CREATED",
        "PERSISTENCE_COMPLETED",
        "INVITATION_SENT",
        "COMPLETED",
        "COMPENSATED",
    }:
        record["cognitoSub"] = "cognito-sub-123"
    return record


def _expected_replay_items() -> ExpectedProvisioningItems:
    return (
        build_user_profile(
            user_id=_USER_ID,
            cognito_sub="cognito-sub-123",
            full_name="Maria da Silva",
            email="admin@example.com",
            created_at="2026-08-20T13:45:12.347Z",
            created_by="github:original",
        ),
        build_unique_email(user_id=_USER_ID, email="admin@example.com"),
        build_cognito_projection(
            user_id=_USER_ID,
            cognito_sub="cognito-sub-123",
        ),
        build_first_admin_bootstrap_marker(
            user_id=_USER_ID,
            operation_id=_OPERATION_ID,
            created_at="2026-08-20T13:45:12.347Z",
            created_by="github:original",
        ),
        build_user_created_audit_event(
            user_id=_USER_ID,
            actor_id="github:original",
            event_id=_EVENT_ID,
            correlation_id=_CORRELATION_ID,
            occurred_at="2026-08-20T13:45:12.347Z",
            expires_at=1_795_009_512,
        ),
    )


def _foreign_marker(*, operation_id: str, user_id: str) -> dict[str, object]:
    return {
        "PK": "CONTROL#FIRST_ADMIN_BOOTSTRAP",
        "SK": "CONTROL",
        "userId": user_id,
        "operationId": operation_id,
        "createdAt": "2026-08-20T13:45:12.347Z",
        "createdBy": "github:winner",
    }


def _safe_foreign_marker() -> dict[str, object]:
    return _foreign_marker(
        operation_id=_CORRELATION_ID,
        user_id=_EVENT_ID,
    )


def _set_provisioning_results(
    provisioning: FakeProvisioningRepository,
    items: ProvisioningItems,
) -> None:
    (
        provisioning.user_profile_result,
        provisioning.unique_email_result,
        provisioning.cognito_projection_result,
        provisioning.bootstrap_marker_result,
        provisioning.audit_event_result,
    ) = items


def _mutable_replay_items() -> list[dict[str, object] | None]:
    return list(_expected_replay_items())


def _fixed_provisioning_items(
    items: list[dict[str, object] | None],
) -> ProvisioningItems:
    assert len(items) == 5
    return (items[0], items[1], items[2], items[3], items[4])


def _required_item(
    items: list[dict[str, object] | None],
    index: int,
) -> dict[str, object]:
    item = items[index]
    assert item is not None
    return item


def _build_service(
    *,
    existing: dict[str, object] | None = None,
    idempotency_get_outcomes: list[object] | None = None,
    transition_outcomes: list[object] | None = None,
    cognito_get_outcomes: list[object] | None = None,
    cognito_create_outcomes: list[object] | None = None,
    cognito_delete_outcomes: list[object] | None = None,
    cognito_disable_outcomes: list[object] | None = None,
    cognito_resend_outcomes: list[object] | None = None,
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
    idempotency = FakeIdempotencyRepository(
        events,
        existing=existing,
        get_outcomes=idempotency_get_outcomes,
        transition_outcomes=transition_outcomes,
    )
    cognito = FakeCognitoRepository(
        events,
        get_outcomes=cognito_get_outcomes,
        create_outcomes=cognito_create_outcomes,
        delete_outcomes=cognito_delete_outcomes,
        disable_outcomes=cognito_disable_outcomes,
        resend_outcomes=cognito_resend_outcomes,
    )
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


class AwsStyleError(Exception):
    def __init__(self, code: str, *, http_status: int | None = None) -> None:
        super().__init__(code)
        self.response: dict[str, object] = {"Error": {"Code": code}}
        if http_status is not None:
            self.response["ResponseMetadata"] = {"HTTPStatusCode": http_status}


def _assert_started_replay_has_no_downstream_effects(
    *,
    ids: FakeIdGenerator,
    cognito: FakeCognitoRepository,
    provisioning: FakeProvisioningRepository,
) -> None:
    assert ids.calls == 0
    assert cognito.resend_calls == []
    assert provisioning.calls == []


def _assert_started_replay_completed(
    *,
    result: BootstrapResult,
    clock: FakeClock,
    ids: FakeIdGenerator,
    idempotency: FakeIdempotencyRepository,
    cognito: FakeCognitoRepository,
    provisioning: FakeProvisioningRepository,
) -> None:
    assert result.state == "COMPLETED"
    assert result.replayed is True
    assert clock.calls == 4
    assert ids.calls == 0
    assert len(provisioning.calls) == 1
    assert len(cognito.resend_calls) == 1
    assert [transition["next_state"] for transition in idempotency.transitions] == [
        "COGNITO_CREATED",
        "PERSISTENCE_COMPLETED",
        "INVITATION_SENT",
        "COMPLETED",
    ]


def test_started_replay_adopts_existing_compatible_cognito_user() -> None:
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("STARTED"),
        cognito_get_outcomes=["reconciled-sub"],
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert cognito.get_calls == [
        {
            "user_pool_id": "pool-123",
            "user_id": _USER_ID,
            "expected_email": "admin@example.com",
        }
    ]
    assert cognito.create_calls == []
    assert idempotency.transitions[0]["next_state"] == "COGNITO_CREATED"
    assert idempotency.transitions[0]["cognito_sub"] == "reconciled-sub"
    _assert_started_replay_completed(
        result=result,
        clock=clock,
        ids=ids,
        idempotency=idempotency,
        cognito=cognito,
        provisioning=provisioning,
    )


def test_started_replay_creates_user_after_confirmed_absence() -> None:
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("STARTED"),
        cognito_get_outcomes=[AwsStyleError("UserNotFoundException")],
        cognito_create_outcomes=["created-sub"],
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email=" Admin@Example.COM ",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert len(cognito.create_calls) == 1
    assert cognito.create_calls[0]["email"] == "admin@example.com"
    assert idempotency.transitions[0]["cognito_sub"] == "created-sub"
    _assert_started_replay_completed(
        result=result,
        clock=clock,
        ids=ids,
        idempotency=idempotency,
        cognito=cognito,
        provisioning=provisioning,
    )


@pytest.mark.parametrize(
    "create_error_code",
    ["UsernameExistsException", "AliasExistsException", "InternalErrorException"],
)
def test_started_replay_reconciles_compatible_user_after_create_error(
    create_error_code: str,
) -> None:
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("STARTED"),
        cognito_get_outcomes=[
            AwsStyleError("UserNotFoundException"),
            "reconciled-sub",
        ],
        cognito_create_outcomes=[AwsStyleError(create_error_code)],
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert len(cognito.create_calls) == 1
    assert len(cognito.get_calls) == 2
    assert idempotency.transitions[0]["cognito_sub"] == "reconciled-sub"
    _assert_started_replay_completed(
        result=result,
        clock=clock,
        ids=ids,
        idempotency=idempotency,
        cognito=cognito,
        provisioning=provisioning,
    )


def test_started_replay_propagates_username_exists_when_user_remains_absent() -> None:
    original_error = AwsStyleError("UsernameExistsException")
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("STARTED"),
        cognito_get_outcomes=[
            AwsStyleError("UserNotFoundException"),
            AwsStyleError("UserNotFoundException"),
        ],
        cognito_create_outcomes=[original_error],
    )

    with pytest.raises(AwsStyleError) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert raised.value is original_error
    assert len(cognito.create_calls) == 1
    assert clock.calls == 0
    assert idempotency.transitions == []
    _assert_started_replay_has_no_downstream_effects(
        ids=ids, cognito=cognito, provisioning=provisioning
    )


def test_started_replay_marks_reconciliation_when_alias_belongs_elsewhere() -> None:
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("STARTED"),
        cognito_get_outcomes=[
            AwsStyleError("UserNotFoundException"),
            AwsStyleError("UserNotFoundException"),
        ],
        cognito_create_outcomes=[AwsStyleError("AliasExistsException")],
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "RECONCILIATION_REQUIRED"
    assert result.replayed is True
    assert len(cognito.create_calls) == 1
    assert clock.calls == 1
    assert idempotency.transitions[0]["next_state"] == "RECONCILIATION_REQUIRED"
    _assert_started_replay_has_no_downstream_effects(
        ids=ids, cognito=cognito, provisioning=provisioning
    )


@pytest.mark.parametrize(
    "create_error_code",
    ["UsernameExistsException", "AliasExistsException"],
)
def test_started_replay_marks_reconciliation_for_incompatible_user_after_race(
    create_error_code: str,
) -> None:
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("STARTED"),
        cognito_get_outcomes=[
            AwsStyleError("UserNotFoundException"),
            CognitoIdentityValidationError("existing Cognito user is incompatible"),
        ],
        cognito_create_outcomes=[AwsStyleError(create_error_code)],
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "RECONCILIATION_REQUIRED"
    assert len(cognito.create_calls) == 1
    assert len(cognito.get_calls) == 2
    assert clock.calls == 1
    assert idempotency.transitions[0]["next_state"] == "RECONCILIATION_REQUIRED"
    _assert_started_replay_has_no_downstream_effects(
        ids=ids, cognito=cognito, provisioning=provisioning
    )


def test_started_replay_marks_reconciliation_for_incompatible_existing_user() -> None:
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("STARTED"),
        cognito_get_outcomes=[
            CognitoIdentityValidationError("existing Cognito user is incompatible")
        ],
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "RECONCILIATION_REQUIRED"
    assert cognito.create_calls == []
    assert clock.calls == 1
    assert idempotency.transitions[0]["next_state"] == "RECONCILIATION_REQUIRED"
    _assert_started_replay_has_no_downstream_effects(
        ids=ids, cognito=cognito, provisioning=provisioning
    )


def test_started_replay_propagates_inconclusive_initial_read() -> None:
    read_error = AwsStyleError("InternalErrorException")
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("STARTED"),
        cognito_get_outcomes=[read_error],
    )

    with pytest.raises(AwsStyleError) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert raised.value is read_error
    assert cognito.create_calls == []
    assert clock.calls == 0
    assert idempotency.transitions == []
    _assert_started_replay_has_no_downstream_effects(
        ids=ids, cognito=cognito, provisioning=provisioning
    )


def test_started_replay_propagates_unexpected_runtime_error_from_initial_read() -> None:
    read_error = RuntimeError("unexpected repository failure")
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("STARTED"),
        cognito_get_outcomes=[read_error],
    )

    with pytest.raises(RuntimeError) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert raised.value is read_error
    assert cognito.create_calls == []
    assert clock.calls == 0
    assert idempotency.transitions == []
    _assert_started_replay_has_no_downstream_effects(
        ids=ids, cognito=cognito, provisioning=provisioning
    )


@pytest.mark.parametrize(
    "create_error",
    [
        AwsStyleError("InternalErrorException"),
        ConnectionClosedError(endpoint_url="https://cognito.example"),
        CognitoCreateResultError("Cognito AdminCreateUser response is missing sub"),
    ],
)
def test_started_replay_reconciles_compatible_user_after_ambiguous_create(
    create_error: BaseException,
) -> None:
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("STARTED"),
        cognito_get_outcomes=[
            AwsStyleError("UserNotFoundException"),
            "reconciled-sub",
        ],
        cognito_create_outcomes=[create_error],
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert len(cognito.create_calls) == 1
    assert idempotency.transitions[0]["cognito_sub"] == "reconciled-sub"
    _assert_started_replay_completed(
        result=result,
        clock=clock,
        ids=ids,
        idempotency=idempotency,
        cognito=cognito,
        provisioning=provisioning,
    )


def test_started_replay_propagates_explicit_throttling_without_reconciliation() -> None:
    throttling_error = AwsStyleError("TooManyRequestsException")
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("STARTED"),
        cognito_get_outcomes=[AwsStyleError("UserNotFoundException")],
        cognito_create_outcomes=[throttling_error],
    )

    with pytest.raises(AwsStyleError) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert raised.value is throttling_error
    assert len(cognito.get_calls) == 1
    assert len(cognito.create_calls) == 1
    assert clock.calls == 0
    assert idempotency.transitions == []
    _assert_started_replay_has_no_downstream_effects(
        ids=ids, cognito=cognito, provisioning=provisioning
    )


@pytest.mark.parametrize(
    "create_error",
    [RuntimeError("unexpected repository failure"), ValueError("invalid value")],
)
def test_started_replay_propagates_unclassified_create_error_without_reconciliation(
    create_error: BaseException,
) -> None:
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("STARTED"),
        cognito_get_outcomes=[AwsStyleError("UserNotFoundException")],
        cognito_create_outcomes=[create_error],
    )

    with pytest.raises(type(create_error)) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert raised.value is create_error
    assert len(cognito.get_calls) == 1
    assert len(cognito.create_calls) == 1
    assert clock.calls == 0
    assert idempotency.transitions == []
    _assert_started_replay_has_no_downstream_effects(
        ids=ids, cognito=cognito, provisioning=provisioning
    )


def test_started_replay_propagates_ambiguous_create_when_user_remains_absent() -> None:
    original_error = AwsStyleError("InternalErrorException")
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("STARTED"),
        cognito_get_outcomes=[
            AwsStyleError("UserNotFoundException"),
            AwsStyleError("UserNotFoundException"),
        ],
        cognito_create_outcomes=[original_error],
    )

    with pytest.raises(AwsStyleError) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert raised.value is original_error
    assert len(cognito.create_calls) == 1
    assert clock.calls == 0
    assert idempotency.transitions == []
    _assert_started_replay_has_no_downstream_effects(
        ids=ids, cognito=cognito, provisioning=provisioning
    )


def test_started_replay_propagates_inconclusive_reconciliation_read() -> None:
    read_error = TimeoutError("AdminGetUser timed out")
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("STARTED"),
        cognito_get_outcomes=[
            AwsStyleError("UserNotFoundException"),
            read_error,
        ],
        cognito_create_outcomes=[ConnectionClosedError(endpoint_url="https://cognito.example")],
    )

    with pytest.raises(TimeoutError) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert raised.value is read_error
    assert len(cognito.create_calls) == 1
    assert clock.calls == 0
    assert idempotency.transitions == []
    _assert_started_replay_has_no_downstream_effects(
        ids=ids, cognito=cognito, provisioning=provisioning
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


@pytest.mark.parametrize(
    "state",
    ["COMPLETED", "COMPENSATED", "RECONCILIATION_REQUIRED"],
)
def test_terminal_state_replay_returns_without_effects(state: str) -> None:
    service, events, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record(state)
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.operation_id == _OPERATION_ID
    assert result.user_id == _USER_ID
    assert result.state == state
    assert result.replayed is True
    assert events == ["idempotency:get"]
    assert clock.calls == 0
    assert ids.calls == 0
    assert idempotency.started_records == []
    assert idempotency.transitions == []
    assert cognito.create_calls == []
    assert cognito.resend_calls == []
    assert provisioning.calls == []


def test_invitation_sent_replay_only_completes_operation() -> None:
    service, events, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("INVITATION_SENT")
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    record_id = f"NONHTTP#dev#bootstrap-admin#first-admin#{_OPERATION_ID}"
    assert result.state == "COMPLETED"
    assert result.replayed is True
    assert clock.calls == 1
    assert ids.calls == 0
    assert idempotency.transitions == [
        {
            "record_id": record_id,
            "operation": "bootstrap-admin",
            "current_state": "INVITATION_SENT",
            "next_state": "COMPLETED",
            "updated_at": "2026-08-20T13:45:12.347Z",
        }
    ]
    assert cognito.create_calls == []
    assert cognito.resend_calls == []
    assert provisioning.calls == []
    assert events == [
        "idempotency:get",
        "clock:1",
        "idempotency:transition:COMPLETED",
    ]


def test_persistence_completed_replay_resends_and_completes_operation() -> None:
    service, events, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("PERSISTENCE_COMPLETED")
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    record_id = f"NONHTTP#dev#bootstrap-admin#first-admin#{_OPERATION_ID}"
    assert result.state == "COMPLETED"
    assert result.replayed is True
    assert clock.calls == 2
    assert ids.calls == 0
    assert cognito.create_calls == []
    assert cognito.resend_calls == [{"user_pool_id": "pool-123", "user_id": _USER_ID}]
    assert provisioning.calls == []
    assert idempotency.transitions == [
        {
            "record_id": record_id,
            "operation": "bootstrap-admin",
            "current_state": "PERSISTENCE_COMPLETED",
            "next_state": "INVITATION_SENT",
            "updated_at": "2026-08-20T13:45:12.347Z",
        },
        {
            "record_id": record_id,
            "operation": "bootstrap-admin",
            "current_state": "INVITATION_SENT",
            "next_state": "COMPLETED",
            "updated_at": "2026-08-20T13:46:12.347Z",
        },
    ]
    assert events == [
        "idempotency:get",
        "cognito:resend",
        "clock:1",
        "idempotency:transition:INVITATION_SENT",
        "clock:2",
        "idempotency:transition:COMPLETED",
    ]


def test_cognito_created_replay_persists_when_all_five_items_are_absent() -> None:
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    expected_items = _expected_replay_items()
    assert result.state == "COMPLETED"
    assert result.replayed is True
    assert ids.calls == 0
    assert clock.calls == 3
    assert cognito.get_calls == [
        {
            "user_pool_id": "pool-123",
            "user_id": _USER_ID,
            "expected_email": "admin@example.com",
        }
    ]
    assert cognito.create_calls == []
    assert cognito.resend_calls == [{"user_pool_id": "pool-123", "user_id": _USER_ID}]
    assert provisioning.read_calls == [
        {"name": "user_profile", "users_table_name": "users-table", "user_id": _USER_ID},
        {
            "name": "unique_email",
            "users_table_name": "users-table",
            "normalized_email": "admin@example.com",
        },
        {
            "name": "cognito_projection",
            "users_table_name": "users-table",
            "cognito_sub": "cognito-sub-123",
        },
        {"name": "bootstrap_marker", "users_table_name": "users-table"},
        {
            "name": "audit_event",
            "audit_table_name": "audit-table",
            "user_id": _USER_ID,
            "occurred_at": "2026-08-20T13:45:12.347Z",
            "event_id": _EVENT_ID,
        },
    ]
    assert provisioning.calls == [
        {
            "users_table_name": "users-table",
            "audit_table_name": "audit-table",
            "user_profile": expected_items[0],
            "unique_email": expected_items[1],
            "cognito_projection": expected_items[2],
            "bootstrap_marker": expected_items[3],
            "audit_event": expected_items[4],
            "client_request_token": _OPERATION_ID,
        }
    ]
    assert expected_items[0]["createdBy"] == "github:original"
    assert expected_items[0]["updatedBy"] == "github:original"
    assert expected_items[3] == {
        "PK": "CONTROL#FIRST_ADMIN_BOOTSTRAP",
        "SK": "CONTROL",
        "userId": _USER_ID,
        "operationId": _OPERATION_ID,
        "createdAt": "2026-08-20T13:45:12.347Z",
        "createdBy": "github:original",
    }
    assert expected_items[4]["eventId"] == _EVENT_ID
    assert expected_items[4]["correlationId"] == _CORRELATION_ID
    assert expected_items[4]["occurredAt"] == "2026-08-20T13:45:12.347Z"
    assert expected_items[4]["expiresAt"] == 1_795_009_512
    assert expected_items[4]["actorId"] == "github:original"
    assert [transition["next_state"] for transition in idempotency.transitions] == [
        "PERSISTENCE_COMPLETED",
        "INVITATION_SENT",
        "COMPLETED",
    ]


def test_cognito_created_replay_accepts_five_exact_items_without_transaction() -> None:
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
    )
    _set_provisioning_results(provisioning, _expected_replay_items())

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "COMPLETED"
    assert result.replayed is True
    assert ids.calls == 0
    assert clock.calls == 3
    assert provisioning.calls == []
    assert cognito.resend_calls == [{"user_pool_id": "pool-123", "user_id": _USER_ID}]
    assert [transition["next_state"] for transition in idempotency.transitions] == [
        "PERSISTENCE_COMPLETED",
        "INVITATION_SENT",
        "COMPLETED",
    ]


@pytest.mark.parametrize(
    "scenario",
    [
        "only-user",
        "audit-absent",
        "marker-incompatible",
        "user-incompatible",
        "audit-incompatible",
        "absent-and-incompatible",
    ],
)
def test_cognito_created_replay_marks_partial_or_incompatible_items_for_reconciliation(
    scenario: str,
) -> None:
    expected = _mutable_replay_items()
    if scenario == "only-user":
        actual: list[dict[str, object] | None] = [expected[0], None, None, None, None]
    else:
        actual = list(expected)
        if scenario == "audit-absent":
            actual[4] = None
        elif scenario == "marker-incompatible":
            actual[3] = {
                **_required_item(expected, 3),
                "operationId": _CORRELATION_ID,
            }
        elif scenario == "user-incompatible":
            actual[0] = {**_required_item(expected, 0), "status": "ACTIVE"}
        elif scenario == "audit-incompatible":
            actual[4] = {**_required_item(expected, 4), "result": "FAILURE"}
        else:
            actual[0] = None
            actual[3] = {
                **_required_item(expected, 3),
                "createdBy": "github:other",
            }

    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
    )
    _set_provisioning_results(provisioning, _fixed_provisioning_items(actual))

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "RECONCILIATION_REQUIRED"
    assert result.replayed is True
    assert ids.calls == 0
    assert clock.calls == 1
    assert provisioning.calls == []
    assert cognito.create_calls == []
    assert cognito.resend_calls == []
    assert [transition["next_state"] for transition in idempotency.transitions] == [
        "RECONCILIATION_REQUIRED"
    ]


@pytest.mark.parametrize(
    "cognito_outcome",
    [
        "different-sub",
        CognitoIdentityValidationError("identity is incompatible"),
    ],
)
def test_cognito_created_replay_marks_cognito_inconsistency_before_dynamo(
    cognito_outcome: object,
) -> None:
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=[cognito_outcome],
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "RECONCILIATION_REQUIRED"
    assert ids.calls == 0
    assert clock.calls == 1
    assert provisioning.read_calls == []
    assert provisioning.calls == []
    assert cognito.create_calls == []
    assert cognito.resend_calls == []
    assert idempotency.transitions[0]["current_state"] == "COGNITO_CREATED"
    assert idempotency.transitions[0]["next_state"] == "RECONCILIATION_REQUIRED"


def test_cognito_created_replay_propagates_inconclusive_cognito_read() -> None:
    read_error = AwsStyleError("InternalErrorException")
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=[read_error],
    )

    with pytest.raises(AwsStyleError) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert raised.value is read_error
    assert ids.calls == 0
    assert clock.calls == 0
    assert provisioning.read_calls == []
    assert provisioning.calls == []
    assert idempotency.transitions == []
    assert cognito.create_calls == []
    assert cognito.resend_calls == []


def test_cognito_created_replay_propagates_dynamo_read_failure_without_effects() -> None:
    read_error = RuntimeError("consistent read failed")
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
    )
    provisioning.read_error_at = "cognito_projection"
    provisioning.read_error = read_error

    with pytest.raises(RuntimeError) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert raised.value is read_error
    assert ids.calls == 0
    assert clock.calls == 0
    assert len(provisioning.read_calls) == 3
    assert provisioning.calls == []
    assert idempotency.transitions == []
    assert cognito.resend_calls == []


def test_cognito_created_replay_propagates_transaction_failure_without_advancing() -> None:
    transaction_error = RuntimeError("transaction failed")
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
    )
    provisioning.persist_error = transaction_error

    with pytest.raises(RuntimeError) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert raised.value is transaction_error
    assert ids.calls == 0
    assert clock.calls == 0
    assert len(provisioning.read_calls) == 5
    assert len(provisioning.calls) == 1
    assert idempotency.transitions == []
    assert cognito.resend_calls == []


@pytest.mark.parametrize(
    "transaction_error",
    [
        AwsStyleError("InternalServerError"),
        AwsStyleError("UnknownServiceError", http_status=503),
        ConnectionClosedError(endpoint_url="https://dynamodb.example"),
    ],
)
def test_cognito_created_reconciles_materialized_items_after_ambiguous_transaction(
    transaction_error: BaseException,
) -> None:
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
    )
    provisioning.persist_error = transaction_error
    provisioning.results_after_persist_error = _expected_replay_items()

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "COMPLETED"
    assert result.replayed is True
    assert len(provisioning.calls) == 1
    assert len(provisioning.read_calls) == 10
    assert clock.calls == 3
    assert ids.calls == 0
    assert len(cognito.resend_calls) == 1
    assert [transition["next_state"] for transition in idempotency.transitions] == [
        "PERSISTENCE_COMPLETED",
        "INVITATION_SENT",
        "COMPLETED",
    ]


def test_cognito_created_propagates_original_ambiguous_error_when_items_absent() -> None:
    transaction_error = AwsStyleError("InternalServerError")
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
    )
    provisioning.persist_error = transaction_error

    with pytest.raises(AwsStyleError) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert raised.value is transaction_error
    assert len(provisioning.calls) == 1
    assert len(provisioning.read_calls) == 10
    assert clock.calls == 0
    assert ids.calls == 0
    assert idempotency.transitions == []
    assert cognito.resend_calls == []


@pytest.mark.parametrize("scenario", ["partial", "incompatible"])
def test_cognito_created_marks_reconciliation_after_ambiguous_transaction_state(
    scenario: str,
) -> None:
    expected = _mutable_replay_items()
    if scenario == "partial":
        expected[4] = None
    else:
        expected[3] = {
            **_required_item(expected, 3),
            "operationId": _CORRELATION_ID,
        }
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
    )
    provisioning.persist_error = AwsStyleError("InternalServerError")
    provisioning.results_after_persist_error = _fixed_provisioning_items(expected)

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "RECONCILIATION_REQUIRED"
    assert len(provisioning.calls) == 1
    assert len(provisioning.read_calls) == 10
    assert clock.calls == 1
    assert ids.calls == 0
    assert cognito.resend_calls == []
    assert idempotency.transitions[0]["next_state"] == "RECONCILIATION_REQUIRED"


def test_cognito_created_propagates_post_error_read_failure() -> None:
    post_error_read = RuntimeError("post-error read failed")
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
    )
    provisioning.persist_error = AwsStyleError("InternalServerError")
    provisioning.read_error_after_persist_at = "user_profile"
    provisioning.read_error_after_persist = post_error_read

    with pytest.raises(RuntimeError) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert raised.value is post_error_read
    assert len(provisioning.calls) == 1
    assert len(provisioning.read_calls) == 6
    assert clock.calls == 0
    assert ids.calls == 0
    assert idempotency.transitions == []
    assert cognito.resend_calls == []


@pytest.mark.parametrize(
    "error_code",
    [
        "TransactionConflictException",
        "TooManyRequestsException",
        "ThrottlingException",
        "ProvisionedThroughputExceededException",
        "ValidationException",
    ],
)
def test_cognito_created_propagates_non_ambiguous_transaction_without_extra_reads(
    error_code: str,
) -> None:
    transaction_error = AwsStyleError(error_code)
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
    )
    provisioning.persist_error = transaction_error

    with pytest.raises(AwsStyleError) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert raised.value is transaction_error
    assert len(provisioning.calls) == 1
    assert len(provisioning.read_calls) == 5
    assert clock.calls == 0
    assert ids.calls == 0
    assert idempotency.transitions == []
    assert cognito.resend_calls == []


@pytest.mark.parametrize(
    ("marker_operation_id", "marker_user_id", "expected_state", "delete_count"),
    [
        (_OPERATION_ID, _CORRELATION_ID, "RECONCILIATION_REQUIRED", 0),
        (_CORRELATION_ID, _USER_ID, "RECONCILIATION_REQUIRED", 0),
        (_CORRELATION_ID, _EVENT_ID, "COMPENSATED", 1),
    ],
)
def test_transaction_canceled_detects_structurally_valid_foreign_marker(
    marker_operation_id: str,
    marker_user_id: str,
    expected_state: str,
    delete_count: int,
) -> None:
    expected = _mutable_replay_items()
    expected[3] = _foreign_marker(
        operation_id=marker_operation_id,
        user_id=marker_user_id,
    )
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
    )
    provisioning.persist_error = AwsStyleError("TransactionCanceledException")
    provisioning.results_after_persist_error = _fixed_provisioning_items(expected)

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == expected_state
    assert result.replayed is True
    assert len(provisioning.calls) == 1
    assert len(provisioning.read_calls) == 10
    assert clock.calls == 1
    assert ids.calls == 0
    assert cognito.create_calls == []
    assert len(cognito.delete_calls) == delete_count
    assert cognito.disable_calls == []
    assert cognito.resend_calls == []
    assert idempotency.transitions[0]["next_state"] == expected_state


def test_transaction_canceled_does_not_trust_malformed_foreign_marker() -> None:
    expected = _mutable_replay_items()
    expected[3] = {
        "PK": "WRONG",
        "SK": "CONTROL",
        "userId": _CORRELATION_ID,
        "operationId": _CORRELATION_ID,
        "createdAt": "2026-08-20T13:45:12.347Z",
        "createdBy": "github:winner",
    }
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
    )
    provisioning.persist_error = AwsStyleError("TransactionCanceledException")
    provisioning.results_after_persist_error = _fixed_provisioning_items(expected)

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "RECONCILIATION_REQUIRED"
    assert len(provisioning.calls) == 1
    assert clock.calls == 1
    assert ids.calls == 0
    assert cognito.resend_calls == []


def test_transaction_canceled_accepts_our_complete_persistence() -> None:
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
    )
    provisioning.persist_error = AwsStyleError("TransactionCanceledException")
    provisioning.results_after_persist_error = _expected_replay_items()

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "COMPLETED"
    assert len(provisioning.calls) == 1
    assert len(provisioning.read_calls) == 10
    assert clock.calls == 3
    assert ids.calls == 0
    assert len(cognito.resend_calls) == 1


def test_transaction_canceled_propagates_original_error_when_all_items_absent() -> None:
    transaction_error = AwsStyleError("TransactionCanceledException")
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
    )
    provisioning.persist_error = transaction_error

    with pytest.raises(AwsStyleError) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert raised.value is transaction_error
    assert len(provisioning.calls) == 1
    assert len(provisioning.read_calls) == 10
    assert clock.calls == 0
    assert ids.calls == 0
    assert idempotency.transitions == []
    assert cognito.resend_calls == []


@pytest.mark.parametrize("scenario", ["own-marker-audit-absent", "marker-absent-user-present"])
def test_transaction_canceled_marks_partial_state_for_reconciliation(
    scenario: str,
) -> None:
    expected = _mutable_replay_items()
    if scenario == "own-marker-audit-absent":
        expected[4] = None
    else:
        expected = [expected[0], None, None, None, None]
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
    )
    provisioning.persist_error = AwsStyleError("TransactionCanceledException")
    provisioning.results_after_persist_error = _fixed_provisioning_items(expected)

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "RECONCILIATION_REQUIRED"
    assert len(provisioning.calls) == 1
    assert clock.calls == 1
    assert ids.calls == 0
    assert cognito.resend_calls == []


@pytest.mark.parametrize(
    "write_error",
    [
        AwsStyleError("InternalServerError"),
        ConnectionClosedError(endpoint_url="https://dynamodb.example"),
    ],
)
def test_ambiguous_write_detects_foreign_marker(
    write_error: BaseException,
) -> None:
    expected = _mutable_replay_items()
    expected[3] = _foreign_marker(
        operation_id=_CORRELATION_ID,
        user_id=_EVENT_ID,
    )
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
    )
    provisioning.persist_error = write_error
    provisioning.results_after_persist_error = _fixed_provisioning_items(expected)

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "COMPENSATED"
    assert len(provisioning.calls) == 1
    assert clock.calls == 1
    assert ids.calls == 0
    assert cognito.delete_calls == [{"user_pool_id": "pool-123", "user_id": _USER_ID}]
    assert cognito.disable_calls == []
    assert cognito.resend_calls == []


def test_normal_read_detects_foreign_marker_without_transaction() -> None:
    expected = _mutable_replay_items()
    expected[3] = _foreign_marker(
        operation_id=_CORRELATION_ID,
        user_id=_EVENT_ID,
    )
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
    )
    _set_provisioning_results(provisioning, _fixed_provisioning_items(expected))

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "COMPENSATED"
    assert provisioning.calls == []
    assert clock.calls == 1
    assert ids.calls == 0
    assert cognito.delete_calls == [{"user_pool_id": "pool-123", "user_id": _USER_ID}]
    assert cognito.delete_calls[0]["user_id"] != _EVENT_ID
    assert cognito.disable_calls == []
    assert cognito.resend_calls == []


def test_normal_read_treats_own_marker_with_incompatible_item_as_reconciliation() -> None:
    expected = _mutable_replay_items()
    expected[0] = {**_required_item(expected, 0), "status": "ACTIVE"}
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
    )
    _set_provisioning_results(provisioning, _fixed_provisioning_items(expected))

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "RECONCILIATION_REQUIRED"
    assert provisioning.calls == []
    assert clock.calls == 1
    assert ids.calls == 0
    assert cognito.resend_calls == []


def test_foreign_marker_delete_user_not_found_is_compensated() -> None:
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
        cognito_delete_outcomes=[AwsStyleError("UserNotFoundException")],
    )
    _set_provisioning_results(
        provisioning,
        (None, None, None, _safe_foreign_marker(), None),
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "COMPENSATED"
    assert len(cognito.delete_calls) == 1
    assert cognito.disable_calls == []
    assert clock.calls == 1
    assert ids.calls == 0
    assert idempotency.transitions[0]["next_state"] == "COMPENSATED"


@pytest.mark.parametrize(
    ("disable_outcome", "expected_state"),
    [
        (None, "RECONCILIATION_REQUIRED"),
        (AwsStyleError("UserNotFoundException"), "COMPENSATED"),
        (AwsStyleError("InternalErrorException"), "RECONCILIATION_REQUIRED"),
    ],
)
def test_foreign_marker_delete_failure_uses_disable_fallback(
    disable_outcome: object,
    expected_state: str,
) -> None:
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=["cognito-sub-123"],
        cognito_delete_outcomes=[AwsStyleError("InternalErrorException")],
        cognito_disable_outcomes=[disable_outcome],
    )
    _set_provisioning_results(
        provisioning,
        (None, None, None, _safe_foreign_marker(), None),
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == expected_state
    assert cognito.delete_calls == [{"user_pool_id": "pool-123", "user_id": _USER_ID}]
    assert cognito.disable_calls == [{"user_pool_id": "pool-123", "user_id": _USER_ID}]
    assert clock.calls == 1
    assert ids.calls == 0
    assert cognito.resend_calls == []
    assert idempotency.transitions[0]["next_state"] == expected_state


def test_missing_cognito_with_safe_foreign_marker_recovers_compensated_state() -> None:
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=[AwsStyleError("UserNotFoundException")],
    )
    _set_provisioning_results(
        provisioning,
        (None, None, None, _safe_foreign_marker(), None),
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "COMPENSATED"
    assert result.replayed is True
    assert cognito.delete_calls == []
    assert cognito.disable_calls == []
    assert provisioning.calls == []
    assert clock.calls == 1
    assert ids.calls == 0
    assert idempotency.transitions[0]["next_state"] == "COMPENSATED"


@pytest.mark.parametrize(
    "actual_items",
    [
        (
            None,
            None,
            None,
            _foreign_marker(operation_id=_CORRELATION_ID, user_id=_USER_ID),
            None,
        ),
        _expected_replay_items(),
        (
            None,
            None,
            None,
            {
                "PK": "WRONG",
                "SK": "CONTROL",
                "userId": _EVENT_ID,
                "operationId": _CORRELATION_ID,
                "createdAt": "2026-08-20T13:45:12.347Z",
                "createdBy": "github:winner",
            },
            None,
        ),
    ],
)
def test_missing_cognito_without_safe_foreign_marker_requires_reconciliation(
    actual_items: tuple[
        dict[str, object] | None,
        dict[str, object] | None,
        dict[str, object] | None,
        dict[str, object] | None,
        dict[str, object] | None,
    ],
) -> None:
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COGNITO_CREATED"),
        cognito_get_outcomes=[AwsStyleError("UserNotFoundException")],
    )
    _set_provisioning_results(provisioning, actual_items)

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "RECONCILIATION_REQUIRED"
    assert cognito.delete_calls == []
    assert cognito.disable_calls == []
    assert provisioning.calls == []
    assert clock.calls == 1
    assert ids.calls == 0


def test_compensated_replay_has_no_compensation_effects() -> None:
    service, _, clock, ids, _, cognito, provisioning = _build_service(
        existing=_existing_record("COMPENSATED"),
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "COMPENSATED"
    assert result.replayed is True
    assert cognito.delete_calls == []
    assert cognito.disable_calls == []
    assert provisioning.calls == []
    assert clock.calls == 0
    assert ids.calls == 0


def test_replay_payload_mismatch_fails_before_any_effect() -> None:
    service, events, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("COMPLETED")
    )

    with pytest.raises(IdempotencyConflictError, match="incompatible payload"):
        service.bootstrap_first_admin(
            full_name="Different Name",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert events == ["idempotency:get"]
    assert clock.calls == 0
    assert ids.calls == 0
    assert idempotency.transitions == []
    assert cognito.create_calls == []
    assert cognito.resend_calls == []
    assert provisioning.calls == []


def test_structurally_invalid_replay_record_fails_before_any_effect() -> None:
    existing = _existing_record("COMPLETED")
    existing["id"] = "incompatible-record-id"
    service, events, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=existing
    )

    with pytest.raises(InvalidBootstrapRecordError, match="id"):
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert events == ["idempotency:get"]
    assert clock.calls == 0
    assert ids.calls == 0
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


@pytest.mark.parametrize(
    "transition_error",
    [
        AwsStyleError("InternalServerError"),
        ConnectionClosedError(endpoint_url="https://dynamodb.example"),
        AwsStyleError("ConditionalCheckFailedException"),
    ],
)
def test_completed_cas_error_accepts_consistently_confirmed_next_state(
    transition_error: BaseException,
) -> None:
    completed = _existing_record("COMPLETED")
    completed["updatedAt"] = "2026-08-20T14:55:00.000Z"
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        idempotency_get_outcomes=[_existing_record("INVITATION_SENT"), completed],
        transition_outcomes=[transition_error],
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "COMPLETED"
    assert result.replayed is True
    assert len(idempotency.transitions) == 1
    assert len(idempotency.get_calls) == 2
    assert clock.calls == 1
    assert ids.calls == 0
    assert cognito.create_calls == []
    assert cognito.resend_calls == []
    assert provisioning.calls == []


@pytest.mark.parametrize(
    ("reconciled_state", "post_error_record"),
    [
        ("INVITATION_SENT", _existing_record("INVITATION_SENT")),
        ("PERSISTENCE_COMPLETED", _existing_record("PERSISTENCE_COMPLETED")),
        ("missing", None),
    ],
)
def test_completed_cas_error_propagates_when_next_state_is_not_confirmed(
    reconciled_state: str,
    post_error_record: dict[str, object] | None,
) -> None:
    transition_error = AwsStyleError("InternalServerError")
    service, _, _, _, idempotency, cognito, _ = _build_service(
        idempotency_get_outcomes=[
            _existing_record("INVITATION_SENT"),
            post_error_record,
        ],
        transition_outcomes=[transition_error],
    )

    with pytest.raises(AwsStyleError) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert raised.value is transition_error
    assert reconciled_state in {"INVITATION_SENT", "PERSISTENCE_COMPLETED", "missing"}
    assert len(idempotency.transitions) == 1
    assert cognito.resend_calls == []


def test_cas_reconciliation_propagates_read_error() -> None:
    transition_error = AwsStyleError("InternalServerError")
    read_error = AwsStyleError("InternalServerError")
    service, _, _, _, idempotency, _, _ = _build_service(
        idempotency_get_outcomes=[_existing_record("INVITATION_SENT"), read_error],
        transition_outcomes=[transition_error],
    )

    with pytest.raises(AwsStyleError) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert raised.value is read_error
    assert len(idempotency.transitions) == 1


def test_cas_reconciliation_rejects_structurally_invalid_record() -> None:
    transition_error = AwsStyleError("InternalServerError")
    invalid_record = _existing_record("COMPLETED")
    invalid_record["operationId"] = "invalid"
    service, _, _, _, idempotency, _, _ = _build_service(
        idempotency_get_outcomes=[_existing_record("INVITATION_SENT"), invalid_record],
        transition_outcomes=[transition_error],
    )

    with pytest.raises(InvalidBootstrapRecordError):
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert len(idempotency.transitions) == 1


def test_non_ambiguous_cas_error_propagates_without_reconciliation_read() -> None:
    transition_error = AwsStyleError("ValidationException")
    service, _, _, _, idempotency, _, _ = _build_service(
        existing=_existing_record("INVITATION_SENT"),
        transition_outcomes=[transition_error],
    )

    with pytest.raises(AwsStyleError) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert raised.value is transition_error
    assert len(idempotency.get_calls) == 1
    assert len(idempotency.transitions) == 1


@pytest.mark.parametrize(
    ("transition_error", "persisted_sub", "succeeds"),
    [
        (AwsStyleError("InternalServerError"), "cognito-sub-123", True),
        (
            AwsStyleError("ConditionalCheckFailedException"),
            "cognito-sub-123",
            True,
        ),
        (AwsStyleError("InternalServerError"), "different-sub", False),
        (
            AwsStyleError("ConditionalCheckFailedException"),
            "different-sub",
            False,
        ),
    ],
)
def test_cognito_created_cas_reconciliation_requires_matching_sub(
    transition_error: BaseException,
    persisted_sub: str,
    succeeds: bool,
) -> None:
    reconciled = _existing_record("COGNITO_CREATED")
    reconciled["cognitoSub"] = persisted_sub
    reconciled["updatedAt"] = "2026-08-20T14:55:00.000Z"
    service, _, _, ids, idempotency, cognito, provisioning = _build_service(
        idempotency_get_outcomes=[_existing_record("STARTED"), reconciled],
        transition_outcomes=[transition_error],
        cognito_get_outcomes=["cognito-sub-123"],
    )
    _set_provisioning_results(provisioning, _expected_replay_items())

    if succeeds:
        result = service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )
        assert result.state == "COMPLETED"
    else:
        with pytest.raises(type(transition_error)) as raised:
            service.bootstrap_first_admin(
                full_name="Maria da Silva",
                email="admin@example.com",
                operation_id=_OPERATION_ID,
                actor_id="github:other-executor",
            )
        assert raised.value is transition_error
        assert provisioning.read_calls == []
        assert cognito.resend_calls == []

    assert len(idempotency.transitions) == (4 if succeeds else 1)
    assert idempotency.transitions[0]["next_state"] == "COGNITO_CREATED"
    assert ids.calls == 0


@pytest.mark.parametrize(
    ("target_state", "cognito_get_outcomes", "provisioning_items"),
    [
        ("COMPENSATED", ["cognito-sub-123"], (None, None, None, _safe_foreign_marker(), None)),
        (
            "RECONCILIATION_REQUIRED",
            [AwsStyleError("UserNotFoundException")],
            (None, None, None, None, None),
        ),
    ],
)
def test_terminal_cas_error_accepts_confirmed_terminal_state(
    target_state: str,
    cognito_get_outcomes: list[object],
    provisioning_items: tuple[
        dict[str, object] | None,
        dict[str, object] | None,
        dict[str, object] | None,
        dict[str, object] | None,
        dict[str, object] | None,
    ],
) -> None:
    transition_error = AwsStyleError("InternalServerError")
    reconciled = _existing_record(target_state)
    service, _, _, ids, idempotency, _, provisioning = _build_service(
        idempotency_get_outcomes=[_existing_record("COGNITO_CREATED"), reconciled],
        transition_outcomes=[transition_error],
        cognito_get_outcomes=cognito_get_outcomes,
    )
    _set_provisioning_results(provisioning, provisioning_items)

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == target_state
    assert result.replayed is True
    assert len(idempotency.transitions) == 1
    assert ids.calls == 0


@pytest.mark.parametrize(
    "resend_error",
    [
        AwsStyleError("CodeDeliveryFailureException"),
        AwsStyleError("TooManyRequestsException"),
        AwsStyleError("InternalErrorException"),
        ConnectionClosedError(endpoint_url="https://cognito.example"),
    ],
)
def test_persistence_completed_replay_propagates_resend_error_without_effects(
    resend_error: BaseException,
) -> None:
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("PERSISTENCE_COMPLETED"),
        cognito_resend_outcomes=[resend_error],
    )

    with pytest.raises(type(resend_error)) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert raised.value is resend_error
    assert len(cognito.resend_calls) == 1
    assert cognito.delete_calls == []
    assert cognito.disable_calls == []
    assert idempotency.transitions == []
    assert provisioning.calls == []
    assert clock.calls == 0
    assert ids.calls == 0


def test_persistence_completed_replay_marks_missing_cognito_for_reconciliation() -> None:
    service, _, clock, ids, idempotency, cognito, provisioning = _build_service(
        existing=_existing_record("PERSISTENCE_COMPLETED"),
        cognito_resend_outcomes=[AwsStyleError("UserNotFoundException")],
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "RECONCILIATION_REQUIRED"
    assert result.replayed is True
    assert len(cognito.resend_calls) == 1
    assert cognito.delete_calls == []
    assert cognito.disable_calls == []
    assert provisioning.calls == []
    assert clock.calls == 1
    assert ids.calls == 0
    assert [call["next_state"] for call in idempotency.transitions] == ["RECONCILIATION_REQUIRED"]


def test_resend_user_not_found_accepts_reconciled_terminal_cas() -> None:
    transition_error = AwsStyleError("InternalServerError")
    service, _, clock, _, idempotency, cognito, _ = _build_service(
        idempotency_get_outcomes=[
            _existing_record("PERSISTENCE_COMPLETED"),
            _existing_record("RECONCILIATION_REQUIRED"),
        ],
        transition_outcomes=[transition_error],
        cognito_resend_outcomes=[AwsStyleError("UserNotFoundException")],
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "RECONCILIATION_REQUIRED"
    assert result.replayed is True
    assert len(cognito.resend_calls) == 1
    assert len(idempotency.transitions) == 1
    assert len(idempotency.get_calls) == 2
    assert clock.calls == 1


def test_resend_success_accepts_reconciled_invitation_sent_cas() -> None:
    transition_error = AwsStyleError("InternalServerError")
    service, _, clock, _, idempotency, cognito, _ = _build_service(
        idempotency_get_outcomes=[
            _existing_record("PERSISTENCE_COMPLETED"),
            _existing_record("INVITATION_SENT"),
        ],
        transition_outcomes=[transition_error],
    )

    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:other-executor",
    )

    assert result.state == "COMPLETED"
    assert len(cognito.resend_calls) == 1
    assert [call["next_state"] for call in idempotency.transitions] == [
        "INVITATION_SENT",
        "COMPLETED",
    ]
    assert clock.calls == 2


def test_resend_success_propagates_unconfirmed_invitation_sent_cas() -> None:
    transition_error = AwsStyleError("InternalServerError")
    service, _, clock, _, idempotency, cognito, _ = _build_service(
        idempotency_get_outcomes=[
            _existing_record("PERSISTENCE_COMPLETED"),
            _existing_record("PERSISTENCE_COMPLETED"),
        ],
        transition_outcomes=[transition_error],
    )

    with pytest.raises(AwsStyleError) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:other-executor",
        )

    assert raised.value is transition_error
    assert len(cognito.resend_calls) == 1
    assert len(idempotency.transitions) == 1
    assert clock.calls == 1


def test_separate_replays_may_resend_after_prior_failure() -> None:
    first_error = AwsStyleError("CodeDeliveryFailureException")
    service, _, clock, ids, idempotency, cognito, _ = _build_service(
        existing=_existing_record("PERSISTENCE_COMPLETED"),
        cognito_resend_outcomes=[first_error, None],
    )

    with pytest.raises(AwsStyleError) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:first-executor",
        )
    result = service.bootstrap_first_admin(
        full_name="Maria da Silva",
        email="admin@example.com",
        operation_id=_OPERATION_ID,
        actor_id="github:second-executor",
    )

    assert raised.value is first_error
    assert result.state == "COMPLETED"
    assert result.replayed is True
    assert len(cognito.resend_calls) == 2
    assert len(idempotency.transitions) == 2
    assert clock.calls == 2
    assert ids.calls == 0


def test_happy_path_resend_user_not_found_returns_non_replayed_reconciliation() -> None:
    service, _, clock, _, idempotency, cognito, provisioning = _build_service(
        cognito_resend_outcomes=[AwsStyleError("UserNotFoundException")],
    )

    result = service.bootstrap_first_admin(
        full_name="  Maria   da Silva  ",
        email=" ADMIN@Example.COM ",
        operation_id=_OPERATION_ID,
        actor_id="github:raphael",
    )

    assert result.state == "RECONCILIATION_REQUIRED"
    assert result.replayed is False
    assert len(provisioning.calls) == 1
    assert len(cognito.resend_calls) == 1
    assert cognito.delete_calls == []
    assert cognito.disable_calls == []
    assert [call["next_state"] for call in idempotency.transitions] == [
        "COGNITO_CREATED",
        "PERSISTENCE_COMPLETED",
        "RECONCILIATION_REQUIRED",
    ]
    assert clock.calls == 4


def test_happy_path_propagates_resend_error_without_rollback() -> None:
    resend_error = AwsStyleError("CodeDeliveryFailureException")
    service, _, clock, _, idempotency, cognito, provisioning = _build_service(
        cognito_resend_outcomes=[resend_error],
    )

    with pytest.raises(AwsStyleError) as raised:
        service.bootstrap_first_admin(
            full_name="Maria da Silva",
            email="admin@example.com",
            operation_id=_OPERATION_ID,
            actor_id="github:raphael",
        )

    assert raised.value is resend_error
    assert len(provisioning.calls) == 1
    assert len(cognito.resend_calls) == 1
    assert cognito.delete_calls == []
    assert cognito.disable_calls == []
    assert [call["next_state"] for call in idempotency.transitions] == [
        "COGNITO_CREATED",
        "PERSISTENCE_COMPLETED",
    ]
    assert clock.calls == 3
