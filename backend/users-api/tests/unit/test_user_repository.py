from decimal import Decimal
from typing import Any

import pytest
from boto3.dynamodb.types import (  # type: ignore[import-untyped]
    TypeDeserializer,
    TypeSerializer,
)
from users_api.repositories.user_repository import UserRepository


class FakeClient:
    def __init__(self) -> None:
        self.responses: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, object]] = []
        self.transaction: dict[str, object] | None = None

    def get_item(self, **kwargs: object) -> dict[str, Any]:
        self.get_calls.append(kwargs)
        return self.responses.pop(0)

    def transact_write_items(self, **kwargs: object) -> dict[str, Any]:
        self.transaction = kwargs
        return {}


def serialized(item: dict[str, object]) -> dict[str, object]:
    serializer = TypeSerializer()
    return {key: serializer.serialize(value) for key, value in item.items()}


def activate(repository: UserRepository, client: FakeClient, role: str) -> dict[str, object]:
    repository.activate(
        user_id="user-1",
        cognito_sub="sub-1",
        role=role,
        auth_version=1,
        occurred_at="2026-09-02T12:00:00.000Z",
        event_id="event-1",
        correlation_id="request-1",
        expires_at=123456789,
        client_request_token="22222222-2222-4222-8222-222222222222",
    )
    assert client.transaction is not None
    return client.transaction


def test_reads_projection_and_profile_consistently() -> None:
    client = FakeClient()
    client.responses = [
        {"Item": serialized({"userId": "user-1", "status": "INVITED"})},
        {"Item": serialized({"userId": "user-1", "status": "INVITED"})},
    ]
    repository = UserRepository(client, "users", "audit")
    assert repository.get_authorization("sub-1") == {
        "userId": "user-1",
        "status": "INVITED",
    }
    assert repository.get_profile("user-1") is not None
    assert all(call["ConsistentRead"] is True for call in client.get_calls)


def test_normalizes_integral_dynamodb_auth_versions_for_both_user_items() -> None:
    client = FakeClient()
    client.responses = [
        {"Item": serialized({"authVersion": Decimal("1")})},
        {"Item": serialized({"authVersion": Decimal("1")})},
    ]
    repository = UserRepository(client, "users", "audit")

    authorization = repository.get_authorization("sub-1")
    profile = repository.get_profile("user-1")

    assert authorization == {"authVersion": 1}
    assert profile == {"authVersion": 1}
    assert type(authorization["authVersion"]) is int
    assert type(profile["authVersion"]) is int


@pytest.mark.parametrize(
    "invalid_value",
    [Decimal("1.5"), Decimal("NaN"), Decimal("Infinity"), "1", True],
)
def test_does_not_normalize_invalid_auth_version_types(invalid_value: object) -> None:
    client = FakeClient()
    attribute = (
        {"N": str(invalid_value)}
        if isinstance(invalid_value, Decimal) and not invalid_value.is_finite()
        else TypeSerializer().serialize(invalid_value)
    )
    client.responses = [{"Item": {"authVersion": attribute}}]

    item = UserRepository(client, "users", "audit").get_authorization("sub-1")

    assert item is not None
    value = item["authVersion"]
    if isinstance(invalid_value, Decimal) and invalid_value.is_nan():
        assert isinstance(value, Decimal) and value.is_nan()
    else:
        assert value == invalid_value


def test_missing_item_returns_none() -> None:
    client = FakeClient()
    client.responses = [{}]
    assert UserRepository(client, "users", "audit").get_profile("user-1") is None


def test_admin_transaction_has_counter_and_audit_once() -> None:
    client = FakeClient()
    transaction = activate(UserRepository(client, "users", "audit"), client, "ADMIN")
    items = transaction["TransactItems"]
    assert isinstance(items, list) and len(items) == 4
    assert sum("Update" in item for item in items) == 3
    assert sum("Put" in item for item in items) == 1
    assert transaction["ClientRequestToken"] == "22222222-2222-4222-8222-222222222222"

    counter = items[2]["Update"]
    assert counter["UpdateExpression"] == "ADD activeAdminCount :one"
    audit = TypeDeserializer().deserialize(items[3]["Put"]["Item"]["eventType"])
    assert audit == "USER_ACTIVATED"


def test_operator_transaction_has_no_admin_counter() -> None:
    client = FakeClient()
    transaction = activate(UserRepository(client, "users", "audit"), client, "OPERATOR")
    items = transaction["TransactItems"]
    assert isinstance(items, list) and len(items) == 3
    assert all(
        item.get("Update", {}).get("UpdateExpression") != "ADD activeAdminCount :one"
        for item in items
    )
