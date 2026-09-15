import json
from copy import deepcopy

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from users_api.errors import (
    AdminUserForbiddenError,
    AdminUserNotFoundError,
    LastActiveAdminConflictError,
    UserDeactivationReconciliationError,
    UserStateConflictError,
    UserVersionConflictError,
)
from users_api.services.deactivation_service import DeactivationService
from users_api.services.invitation_saga import DeactivationState, SagaClaim

KEY = "11111111-1111-4111-8111-111111111111"
STARTED = "2026-09-14T14:00:00.000Z"


def profile(
    user_id: str, sub: str, role: str, status: str, version: int | None
) -> dict[str, object]:
    item: dict[str, object] = {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "userId": user_id,
        "cognitoSub": sub,
        "role": role,
        "status": status,
        "authVersion": 1,
        "fullName": "Synthetic User",
        "email": "synthetic@example.test",
        "createdAt": STARTED,
        "updatedAt": STARTED,
    }
    if version is not None:
        item["version"] = version
    return item


class FakeUsers:
    def __init__(
        self, *, role: str = "OPERATOR", status: str = "ACTIVE", version: int | None = 1
    ) -> None:
        self.actor = profile("actor-1", "actor-sub", "ADMIN", "ACTIVE", 1)
        self.target = profile("target-1", "target-sub", role, status, version)
        self.calls: list[dict[str, object]] = []
        self.count: int | None = 2
        self.error: ClientError | None = None

    def get_authorization(self, sub: str) -> dict[str, object] | None:
        source = self.actor if sub == "actor-sub" else self.target if sub == "target-sub" else None
        if source is None:
            return None
        return {
            "userId": source["userId"],
            "role": source["role"],
            "status": source["status"],
            "authVersion": source["authVersion"],
        }

    def get_profile(self, user_id: str) -> dict[str, object] | None:
        source = (
            self.actor if user_id == "actor-1" else self.target if user_id == "target-1" else None
        )
        return deepcopy(source)

    def get_active_admin_count(self) -> int | None:
        return self.count

    def deactivate_user(self, **kwargs: object) -> None:
        self.calls.append(deepcopy(kwargs))
        if self.error is not None:
            raise self.error


class FakeSaga:
    def __init__(self) -> None:
        self.record: dict[str, object] = {
            "id": "operation-1",
            "state": DeactivationState.CLAIMED.value,
            "target": "target-1",
            "actorId": "actor-1",
            "eventId": "event-1",
            "correlationId": "correlation-1",
            "startedAt": STARTED,
        }
        self.claim_calls: list[dict[str, object]] = []
        self.transition_calls: list[dict[str, object]] = []

    def claim_deactivation(self, **kwargs: object) -> SagaClaim:
        self.claim_calls.append(kwargs)
        return SagaClaim(deepcopy(self.record), created=True)

    def get(self, record_id: str) -> dict[str, object] | None:
        assert record_id == self.record["id"]
        return deepcopy(self.record)

    def build_deactivation_domain_transition(self, **kwargs: object) -> dict[str, object]:
        self.transition_calls.append(kwargs)
        return {"Update": {"TableName": "idempotency"}}


def run(
    users: FakeUsers, saga: FakeSaga, *, user_id: str = "target-1", version: int = 1
) -> DeactivationState:
    service = DeactivationService(users, saga, environment="dev", audit_retention_days=365)
    return service.commit_domain(
        cognito_sub="actor-sub",
        user_id=user_id,
        idempotency_key=KEY,
        request_id="request-1",
        body=json.dumps({"expectedVersion": version}),
    ).state


@pytest.mark.parametrize("role", ["OPERATOR", "ADMIN"])
def test_domain_commit_builds_one_atomic_transaction_and_private_audit(role: str) -> None:
    users, saga = FakeUsers(role=role), FakeSaga()
    assert run(users, saga) == DeactivationState.DOMAIN_COMMITTED
    assert len(users.calls) == 1
    call = users.calls[0]
    assert call["role"] == role and call["version"] == 1 and call["auth_version"] == 1
    assert call["idempotency_transition"] == {"Update": {"TableName": "idempotency"}}
    audit = call["audit"]
    assert isinstance(audit, dict)
    assert audit["eventType"] == "USER_DEACTIVATED"
    assert audit["changes"] == {
        "status": {"from": "ACTIVE", "to": "INACTIVE"},
        "version": {"from": 1, "to": 2},
    }
    assert audit["eventId"] == "event-1" and audit["result"] == "SUCCESS"
    assert "synthetic@example.test" not in repr(audit)
    assert "Synthetic User" not in repr(audit)
    assert saga.transition_calls[0]["resulting_version"] == 2


def test_legacy_version_materializes_version_two() -> None:
    users, saga = FakeUsers(version=None), FakeSaga()
    assert run(users, saga) == DeactivationState.DOMAIN_COMMITTED
    assert users.calls[0]["version"] == 1
    assert saga.transition_calls[0]["resulting_version"] == 2


@pytest.mark.parametrize("status", ["INVITED", "INACTIVE"])
def test_new_key_rejects_non_active_target(status: str) -> None:
    users, saga = FakeUsers(status=status), FakeSaga()
    with pytest.raises(UserStateConflictError):
        run(users, saga)
    assert users.calls == []


def test_missing_target_and_stale_version_are_classified() -> None:
    users, saga = FakeUsers(), FakeSaga()
    with pytest.raises(AdminUserNotFoundError):
        run(users, saga, user_id="missing")
    with pytest.raises(UserVersionConflictError):
        run(users, saga, version=2)
    assert users.calls == []


def test_self_and_non_admin_are_forbidden_before_claim() -> None:
    users, saga = FakeUsers(), FakeSaga()
    with pytest.raises(AdminUserForbiddenError):
        run(users, saga, user_id="actor-1")
    assert saga.claim_calls == []
    users.actor["role"] = "OPERATOR"
    with pytest.raises(AdminUserForbiddenError):
        run(users, saga)
    assert saga.claim_calls == []


def test_domain_committed_resume_does_not_repeat_domain_transaction() -> None:
    users, saga = FakeUsers(status="INACTIVE", version=2), FakeSaga()
    saga.record["state"] = DeactivationState.DOMAIN_COMMITTED.value
    assert run(users, saga) == DeactivationState.DOMAIN_COMMITTED
    assert users.calls == []


def test_transaction_cancellation_classifies_last_admin_and_fail_closed() -> None:
    users, saga = FakeUsers(role="ADMIN"), FakeSaga()
    users.error = ClientError(
        {"Error": {"Code": "TransactionCanceledException", "Message": "private"}},
        "TransactWriteItems",
    )
    users.count = 1
    with pytest.raises(LastActiveAdminConflictError):
        run(users, saga)
    users.count = None
    with pytest.raises(UserDeactivationReconciliationError):
        run(users, saga)


def test_cancellation_readback_recognizes_domain_commit_without_repeat() -> None:
    users, saga = FakeUsers(), FakeSaga()
    users.error = ClientError(
        {"Error": {"Code": "TransactionCanceledException"}}, "TransactWriteItems"
    )
    original = users.deactivate_user

    def raced(**kwargs: object) -> None:
        saga.record["state"] = DeactivationState.DOMAIN_COMMITTED.value
        original(**kwargs)

    users.deactivate_user = raced  # type: ignore[method-assign]
    assert run(users, saga) == DeactivationState.DOMAIN_COMMITTED


@pytest.mark.parametrize(
    ("changed_field", "new_value", "expected_error"),
    [
        ("version", 2, UserVersionConflictError),
        ("status", "INACTIVE", UserStateConflictError),
        ("role", "ADMIN", UserDeactivationReconciliationError),
    ],
)
def test_cancellation_readback_rejects_concurrent_target_change(
    changed_field: str, new_value: object, expected_error: type[Exception]
) -> None:
    users, saga = FakeUsers(), FakeSaga()
    users.error = ClientError(
        {"Error": {"Code": "TransactionCanceledException", "Message": "private"}},
        "TransactWriteItems",
    )
    original = users.deactivate_user

    def raced(**kwargs: object) -> None:
        users.target[changed_field] = new_value
        original(**kwargs)

    users.deactivate_user = raced  # type: ignore[method-assign]
    with pytest.raises(expected_error) as failure:
        run(users, saga)
    assert "private" not in str(failure.value)


def test_cancellation_readback_fails_closed_on_projection_inconsistency() -> None:
    users, saga = FakeUsers(), FakeSaga()
    users.error = ClientError(
        {"Error": {"Code": "TransactionCanceledException", "Message": "private"}},
        "TransactWriteItems",
    )
    original = users.deactivate_user

    def raced(**kwargs: object) -> None:
        users.target["authVersion"] = 2
        original(**kwargs)

    users.deactivate_user = raced  # type: ignore[method-assign]
    with pytest.raises(UserDeactivationReconciliationError):
        run(users, saga)
