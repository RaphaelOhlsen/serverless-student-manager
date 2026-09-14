import json
from copy import deepcopy

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from users_api.errors import (
    AdminUserForbiddenError,
    AdminUserNotFoundError,
    IdempotencyKeyReusedError,
    LastActiveAdminConflictError,
    UserRoleChangeReconciliationError,
    UserVersionConflictError,
)
from users_api.services.invitation_saga import RoleChangeState, SagaClaim
from users_api.services.role_change_service import RoleChangeService

KEY = "11111111-1111-4111-8111-111111111111"
STARTED = "2026-09-14T14:00:00.000Z"


def profile(
    user_id: str,
    sub: str,
    *,
    role: str,
    status: str,
    version: int | None = 1,
    auth_version: int = 1,
) -> dict[str, object]:
    value: dict[str, object] = {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "userId": user_id,
        "cognitoSub": sub,
        "fullName": "Synthetic User",
        "email": "synthetic@example.test",
        "role": role,
        "status": status,
        "authVersion": auth_version,
        "createdAt": "2026-01-01T00:00:00.000Z",
        "updatedAt": "2026-01-01T00:00:00.000Z",
    }
    if version is not None:
        value["version"] = version
    return value


class FakeUsers:
    def __init__(
        self,
        *,
        actor_role: str = "ADMIN",
        actor_status: str = "ACTIVE",
        target_role: str = "OPERATOR",
        target_status: str = "INVITED",
        target_version: int | None = 1,
    ) -> None:
        self.actor = profile(
            "actor-1", "actor-sub", role=actor_role, status=actor_status, version=3
        )
        self.target = profile(
            "target-1",
            "target-sub",
            role=target_role,
            status=target_status,
            version=target_version,
            auth_version=4,
        )
        self.change_calls: list[dict[str, object]] = []
        self.noop_calls: list[dict[str, object]] = []
        self.transaction_error: ClientError | None = None
        self.active_admin_count: int | None = 2

    def get_authorization(self, cognito_sub: str) -> dict[str, object] | None:
        source = self.actor if cognito_sub == "actor-sub" else self.target
        if cognito_sub not in {"actor-sub", "target-sub"}:
            return None
        return {
            "userId": source["userId"],
            "role": source["role"],
            "status": source["status"],
            "authVersion": source["authVersion"],
        }

    def get_profile(self, user_id: str) -> dict[str, object] | None:
        if user_id == "actor-1":
            return deepcopy(self.actor)
        if user_id == "target-1":
            return deepcopy(self.target)
        return None

    def get_active_admin_count(self) -> int | None:
        return self.active_admin_count

    def change_role(self, **kwargs: object) -> None:
        self.change_calls.append(dict(kwargs))
        if self.transaction_error:
            raise self.transaction_error

    def complete_role_change_noop(self, **kwargs: object) -> None:
        self.noop_calls.append(dict(kwargs))
        if self.transaction_error:
            raise self.transaction_error


class FakeSaga:
    def __init__(self) -> None:
        self.record: dict[str, object] = {
            "id": "HTTP#dev#actor-1#change-user-role#key",
            "state": RoleChangeState.CLAIMED.value,
            "actorId": "actor-1",
            "target": "target-1",
            "eventId": "event-1",
            "correlationId": "correlation-1",
            "startedAt": STARTED,
            "idempotencyKey": KEY,
            "requestHash": "hash",
        }
        self.claim_calls: list[dict[str, object]] = []
        self.transition_responses: list[dict[str, object]] = []
        self.claim_error: Exception | None = None

    def claim_role_change(self, **kwargs: object) -> SagaClaim:
        self.claim_calls.append(dict(kwargs))
        if self.claim_error:
            raise self.claim_error
        return SagaClaim(deepcopy(self.record), created=True)

    def get(self, record_id: str) -> dict[str, object] | None:
        assert record_id == self.record["id"]
        return deepcopy(self.record)

    def build_role_change_completion_transition(
        self, *, record: dict[str, object], response: dict[str, object]
    ) -> dict[str, object]:
        del record
        self.transition_responses.append(deepcopy(response))
        return {"Update": {"TableName": "idempotency"}}


def service(users: FakeUsers, saga: FakeSaga | None = None) -> RoleChangeService:
    return RoleChangeService(
        users,
        saga or FakeSaga(),
        environment="dev",
        audit_retention_days=365,
    )


def invoke(
    instance: RoleChangeService,
    *,
    role: str = "ADMIN",
    version: int = 1,
    user_id: str = "target-1",
) -> dict[str, object]:
    return instance.change_role(
        cognito_sub="actor-sub",
        user_id=user_id,
        idempotency_key=KEY,
        request_id="request-1",
        body=json.dumps({"expectedVersion": version, "role": role}),
    )


@pytest.mark.parametrize(
    ("status", "old_role", "new_role", "counter_expected"),
    [
        ("ACTIVE", "OPERATOR", "ADMIN", True),
        ("ACTIVE", "ADMIN", "OPERATOR", True),
        ("INVITED", "OPERATOR", "ADMIN", False),
        ("INVITED", "ADMIN", "OPERATOR", False),
        ("INACTIVE", "OPERATOR", "ADMIN", False),
        ("INACTIVE", "ADMIN", "OPERATOR", False),
    ],
)
def test_effective_role_change_builds_atomic_result_and_audit(
    status: str, old_role: str, new_role: str, counter_expected: bool
) -> None:
    users = FakeUsers(target_role=old_role, target_status=status)
    result = invoke(service(users), role=new_role)
    assert result == {
        "userId": "target-1",
        "fullName": "Synthetic User",
        "email": "synthetic@example.test",
        "role": new_role,
        "status": status,
        "version": 2,
        "createdAt": "2026-01-01T00:00:00.000Z",
        "updatedAt": STARTED,
    }
    assert len(users.change_calls) == 1 and not users.noop_calls
    call = users.change_calls[0]
    assert call["auth_version"] == 4
    assert call["version"] == 1
    assert call["status"] == status
    audit = call["audit"]
    assert isinstance(audit, dict)
    assert audit["eventType"] == "USER_ROLE_CHANGED"
    assert audit["changes"] == {
        "role": {"from": old_role, "to": new_role},
        "version": {"from": 1, "to": 2},
    }
    assert "email" not in repr(audit).lower()
    assert (status == "ACTIVE") is counter_expected


def test_legacy_version_one_materializes_version_two() -> None:
    users = FakeUsers(target_version=None)
    result = invoke(service(users), role="ADMIN", version=1)
    assert result["version"] == 2
    assert users.change_calls[0]["version"] == 1


def test_noop_completes_with_snapshot_check_and_no_domain_audit_or_counter() -> None:
    users = FakeUsers(target_role="ADMIN", target_status="ACTIVE")
    result = invoke(service(users), role="ADMIN")
    assert result["version"] == 1
    assert result["updatedAt"] == "2026-01-01T00:00:00.000Z"
    assert not users.change_calls
    assert len(users.noop_calls) == 1
    assert "audit" not in users.noop_calls[0]
    assert "active_admin_count" not in users.noop_calls[0]


@pytest.mark.parametrize(
    ("actor_role", "actor_status"),
    [("OPERATOR", "ACTIVE"), ("ADMIN", "INACTIVE")],
)
def test_only_active_admin_is_authorized(actor_role: str, actor_status: str) -> None:
    with pytest.raises(AdminUserForbiddenError):
        invoke(service(FakeUsers(actor_role=actor_role, actor_status=actor_status)))


def test_self_change_and_self_noop_are_forbidden_for_new_operation() -> None:
    users = FakeUsers()
    users.actor = profile("actor-1", "actor-sub", role="ADMIN", status="ACTIVE", version=3)
    users.target = users.actor
    with pytest.raises(AdminUserForbiddenError):
        invoke(service(users), role="ADMIN", version=3, user_id="actor-1")
    assert not users.change_calls and not users.noop_calls


def test_missing_target_and_version_conflict_have_no_transaction() -> None:
    users = FakeUsers()
    with pytest.raises(AdminUserNotFoundError):
        invoke(service(users), user_id="missing")
    with pytest.raises(UserVersionConflictError):
        invoke(service(users), version=2)
    assert not users.change_calls


def test_completed_replay_precedes_target_state_validation_and_has_no_mutation() -> None:
    users = FakeUsers(target_role="OPERATOR", target_status="INACTIVE", target_version=9)
    saga = FakeSaga()
    saga.record.update(
        state="COMPLETED",
        httpStatus=200,
        responseUserId="target-1",
        responseRole="ADMIN",
        responseStatus="INVITED",
        responseVersion=2,
        responseCreatedAt="2026-01-01T00:00:00.000Z",
        responseUpdatedAt=STARTED,
    )
    result = invoke(service(users, saga), role="ADMIN", version=1)
    assert result["role"] == "ADMIN"
    assert result["status"] == "INVITED"
    assert result["version"] == 2
    assert not users.change_calls and not users.noop_calls


def transaction_cancelled() -> ClientError:
    return ClientError(
        {"Error": {"Code": "TransactionCanceledException", "Message": "sanitized"}},
        "TransactWriteItems",
    )


def test_last_active_admin_cancellation_is_classified_without_partial_repair() -> None:
    users = FakeUsers(target_role="ADMIN", target_status="ACTIVE")
    users.active_admin_count = 1
    users.transaction_error = transaction_cancelled()
    with pytest.raises(LastActiveAdminConflictError):
        invoke(service(users), role="OPERATOR")
    assert len(users.change_calls) == 1 and not users.noop_calls


def test_concurrent_version_change_is_classified_as_version_conflict() -> None:
    users = FakeUsers()

    def fail_and_advance(**kwargs: object) -> None:
        users.change_calls.append(dict(kwargs))
        users.target["version"] = 2
        raise transaction_cancelled()

    users.change_role = fail_and_advance  # type: ignore[method-assign]
    with pytest.raises(UserVersionConflictError):
        invoke(service(users), role="ADMIN")


def test_concurrent_status_or_projection_change_fails_closed() -> None:
    users = FakeUsers(target_status="INVITED")

    def fail_and_activate(**kwargs: object) -> None:
        users.change_calls.append(dict(kwargs))
        users.target["status"] = "ACTIVE"
        raise transaction_cancelled()

    users.change_role = fail_and_activate  # type: ignore[method-assign]
    with pytest.raises(UserRoleChangeReconciliationError):
        invoke(service(users), role="ADMIN")


def test_concurrent_change_prevents_noop_completion() -> None:
    users = FakeUsers(target_role="ADMIN", target_status="INVITED")

    def fail_and_advance(**kwargs: object) -> None:
        users.noop_calls.append(dict(kwargs))
        users.target["version"] = 2
        raise transaction_cancelled()

    users.complete_role_change_noop = fail_and_advance  # type: ignore[method-assign]
    with pytest.raises(UserVersionConflictError):
        invoke(service(users), role="ADMIN")
    assert not users.change_calls and len(users.noop_calls) == 1


def test_same_operation_completed_concurrently_replays_without_second_write() -> None:
    users = FakeUsers()
    saga = FakeSaga()

    def fail_and_complete(**kwargs: object) -> None:
        users.change_calls.append(dict(kwargs))
        saga.record.update(
            state="COMPLETED",
            httpStatus=200,
            responseUserId="target-1",
            responseRole="ADMIN",
            responseStatus="INVITED",
            responseVersion=2,
            responseCreatedAt="2026-01-01T00:00:00.000Z",
            responseUpdatedAt=STARTED,
        )
        raise transaction_cancelled()

    users.change_role = fail_and_complete  # type: ignore[method-assign]
    assert invoke(service(users, saga), role="ADMIN")["version"] == 2
    assert len(users.change_calls) == 1


def test_idempotency_mismatch_is_propagated_before_target_read() -> None:
    users = FakeUsers()
    saga = FakeSaga()
    saga.claim_error = IdempotencyKeyReusedError()
    with pytest.raises(IdempotencyKeyReusedError):
        invoke(service(users, saga), role="ADMIN")
    assert not users.change_calls and not users.noop_calls
