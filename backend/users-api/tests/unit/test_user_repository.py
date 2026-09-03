from decimal import Decimal
from typing import Any

import pytest
from boto3.dynamodb.types import (  # type: ignore[import-untyped]
    TypeDeserializer,
    TypeSerializer,
)
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from users_api.repositories import user_repository
from users_api.repositories.user_repository import UserRepository


class FakeClient:
    def __init__(self) -> None:
        self.responses: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, object]] = []
        self.transaction: dict[str, object] | None = None
        self.transaction_error: ClientError | None = None

    def get_item(self, **kwargs: object) -> dict[str, Any]:
        self.get_calls.append(kwargs)
        return self.responses.pop(0)

    def transact_write_items(self, **kwargs: object) -> dict[str, Any]:
        self.transaction = kwargs
        if self.transaction_error is not None:
            raise self.transaction_error
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


def test_transaction_error_logging_is_structured_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()
    client.transaction_error = ClientError(
        {
            "Error": {
                "Code": "ValidationException",
                "Message": (
                    "contains USER#secret, ExpressionAttributeValues, sub-1, "
                    "admin@example.test, token-secret and 22222222-2222-4222-8222-222222222222"
                ),
            },
            "ResponseMetadata": {"RequestId": "aws-request-1"},
            "CancellationReasons": [
                {"Code": "None", "Message": "private"},
                {"Code": "ValidationError", "Item": {"PK": {"S": "private"}}},
            ],
        },
        "TransactWriteItems",
    )
    logged: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        user_repository.logger,
        "error",
        lambda message, *, extra: logged.append((message, extra)),
    )

    with pytest.raises(ClientError):
        activate(UserRepository(client, "users", "audit"), client, "ADMIN")

    assert logged == [
        (
            "Activation transaction failed",
            {
                "stage": "activation_transaction",
                "exceptionClass": "ClientError",
                "operation": "TransactWriteItems",
                "awsErrorCode": "ValidationException",
                "awsRequestId": "aws-request-1",
                "correlationId": "request-1",
                "cancellationReasonCodes": [
                    {"index": 0, "code": "None"},
                    {"index": 1, "code": "ValidationError"},
                ],
            },
        )
    ]
    rendered = repr(logged)
    assert "USER#secret" not in rendered
    assert "ExpressionAttributeValues" not in rendered
    assert "private" not in rendered
    assert "sub-1" not in rendered
    assert "admin@example.test" not in rendered
    assert "token-secret" not in rendered
    assert "22222222-2222-4222-8222-222222222222" not in rendered
