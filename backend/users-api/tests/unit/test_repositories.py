from typing import Any

from users_api.repositories.cognito_repository import CognitoRepository
from users_api.repositories.idempotency_repository import IdempotencyRepository


class FakeCognitoClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def admin_get_user(self, **kwargs: object) -> dict[str, Any]:
        self.calls.append(("user", kwargs))
        return {"Username": "user-1"}

    def admin_get_user_auth_factors(self, **kwargs: object) -> dict[str, Any]:
        self.calls.append(("factors", kwargs))
        return {"ConfiguredUserAuthFactors": ["SOFTWARE_TOKEN"]}


class FakeTable:
    def __init__(self) -> None:
        self.item: dict[str, object] | None = None
        self.calls: list[tuple[str, dict[str, object]]] = []

    def put_item(self, **kwargs: object) -> dict[str, Any]:
        self.calls.append(("put", kwargs))
        return {}

    def get_item(self, **kwargs: object) -> dict[str, Any]:
        self.calls.append(("get", kwargs))
        return {"Item": self.item} if self.item is not None else {}

    def update_item(self, **kwargs: object) -> dict[str, Any]:
        self.calls.append(("update", kwargs))
        return {}


def test_cognito_repository_uses_same_pool_and_username() -> None:
    client = FakeCognitoClient()
    repository = CognitoRepository(client, "pool-1")
    assert repository.get_user("user-1")["Username"] == "user-1"
    assert (
        "SOFTWARE_TOKEN" in repository.get_user_auth_factors("user-1")["ConfiguredUserAuthFactors"]
    )
    assert client.calls == [
        ("user", {"UserPoolId": "pool-1", "Username": "user-1"}),
        ("factors", {"UserPoolId": "pool-1", "Username": "user-1"}),
    ]


def test_idempotency_repository_uses_conditional_state_changes() -> None:
    table = FakeTable()
    repository = IdempotencyRepository(table)
    repository.start({"id": "record", "state": "STARTED"})
    assert repository.get("record") is None
    table.item = {"id": "record", "state": "STARTED"}
    assert repository.get("record") == table.item
    repository.complete(
        record_id="record",
        response={"status": "ACTIVE"},
        updated_at="2026-09-02T12:00:00.000Z",
    )
    assert table.calls[0][1]["ConditionExpression"] == "attribute_not_exists(id)"
    assert table.calls[-1][1]["ConditionExpression"] == "#state = :started"
