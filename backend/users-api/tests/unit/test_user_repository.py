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
        self.query_responses: list[dict[str, Any]] = []
        self.query_calls: list[dict[str, object]] = []

    def get_item(self, **kwargs: object) -> dict[str, Any]:
        self.get_calls.append(kwargs)
        return self.responses.pop(0)

    def transact_write_items(self, **kwargs: object) -> dict[str, Any]:
        self.transaction = kwargs
        if self.transaction_error is not None:
            raise self.transaction_error
        return {}

    def query(self, **kwargs: object) -> dict[str, Any]:
        self.query_calls.append(kwargs)
        return self.query_responses.pop(0)


def serialized(item: dict[str, object]) -> dict[str, object]:
    serializer = TypeSerializer()
    return {key: serializer.serialize(value) for key, value in item.items()}


@pytest.mark.parametrize(("role", "expected_items"), [("OPERATOR", 4), ("ADMIN", 5)])
def test_deactivation_transaction_shape_and_conditions(role: str, expected_items: int) -> None:
    client = FakeClient()
    repository = UserRepository(client, "users", "audit")
    audit: dict[str, object] = {
        "PK": "RESOURCE#USER#user-1",
        "SK": "TS#now#EVENT#event-1",
    }
    saga: dict[str, object] = {"Update": {"TableName": "idempotency"}}
    repository.deactivate_user(
        user_id="user-1",
        cognito_sub="sub-1",
        role=role,
        version=1,
        auth_version=1,
        occurred_at="2026-09-14T14:00:00.000Z",
        actor_id="actor-1",
        audit=audit,
        idempotency_transition=saga,
        client_request_token="11111111-1111-4111-8111-111111111111",
    )
    assert client.transaction is not None
    items = client.transaction["TransactItems"]
    assert isinstance(items, list) and len(items) == expected_items
    profile = items[0]["Update"]
    authorization = items[1]["Update"]
    assert profile["TableName"] == authorization["TableName"] == "users"
    assert "#status = :inactive" in profile["UpdateExpression"]
    assert "#version = :next_version" in profile["UpdateExpression"]
    assert "deactivatedAt = :occurred_at" in profile["UpdateExpression"]
    for expression in (profile["ConditionExpression"], authorization["ConditionExpression"]):
        assert "userId = :user_id" in expression
        assert "#role = :role" in expression
        assert "#status = :active" in expression
        assert "authVersion = :auth_version" in expression
    assert "cognitoSub = :sub" in profile["ConditionExpression"]
    assert "attribute_not_exists(#version)" in profile["ConditionExpression"]
    if role == "ADMIN":
        counter = items[2]["Update"]
        assert counter["UpdateExpression"] == "ADD activeAdminCount :decrement"
        assert "activeAdminCount > :one" in counter["ConditionExpression"]
    assert items[-2]["Put"]["TableName"] == "audit"
    assert items[-1] == saga


def test_deactivation_version_condition_guards_legacy_and_versioned_profiles() -> None:
    client = FakeClient()
    repository = UserRepository(client, "users", "audit")
    repository.deactivate_user(
        user_id="user-1",
        cognito_sub="sub-1",
        role="OPERATOR",
        version=2,
        auth_version=1,
        occurred_at="2026-09-14T14:00:00.000Z",
        actor_id="actor-1",
        audit={"PK": "a", "SK": "b"},
        idempotency_transition={"Update": {}},
        client_request_token="11111111-1111-4111-8111-111111111111",
    )
    assert client.transaction is not None
    items = client.transaction["TransactItems"]
    assert isinstance(items, list)
    condition = items[0]["Update"]["ConditionExpression"]
    assert "attribute_not_exists(#version)" not in condition
    assert "#version = :version" in condition


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


def test_email_reservation_is_read_consistently() -> None:
    client = FakeClient()
    client.responses = [{"Item": serialized({"userId": "user-1"})}]

    assert UserRepository(client, "users", "audit").get_email_reservation("user@example.test") == {
        "userId": "user-1"
    }
    assert client.get_calls == [
        {
            "TableName": "users",
            "Key": serialized({"PK": "UNIQUE#EMAIL#user@example.test", "SK": "UNIQUE"}),
            "ConsistentRead": True,
        }
    ]


def test_provisioning_transaction_has_exactly_five_atomic_operations() -> None:
    client = FakeClient()
    repository = UserRepository(client, "users", "audit")
    saga: dict[str, object] = {
        "Update": {
            "TableName": "idempotency",
            "Key": serialized({"id": "operation"}),
            "UpdateExpression": "SET #state = :next",
        }
    }
    repository.provision_invited_user(
        profile={"PK": "USER#user-1", "SK": "PROFILE"},
        unique_email={"PK": "UNIQUE#EMAIL#admin@example.test", "SK": "UNIQUE"},
        authorization={"PK": "COGNITO#sub-1", "SK": "AUTHORIZATION"},
        audit={"PK": "RESOURCE#USER#user-1", "SK": "TS#time#EVENT#event-1"},
        saga_transition=saga,
        client_request_token="44444444-4444-4444-8444-444444444444",
    )

    assert client.transaction is not None
    items = client.transaction["TransactItems"]
    assert isinstance(items, list) and len(items) == 5
    assert [item["Put"]["TableName"] for item in items[:4]] == [
        "users",
        "users",
        "users",
        "audit",
    ]
    assert items[4] == saga
    assert all(
        item["Put"]["ConditionExpression"]
        == "attribute_not_exists(PK) AND attribute_not_exists(SK)"
        for item in items[:4]
    )
    assert client.transaction["ClientRequestToken"] == ("44444444-4444-4444-8444-444444444444")
    assert "CONTROL#ACTIVE_ADMIN_COUNT" not in repr(client.transaction)


def test_resend_completion_atomically_writes_audit_and_saga_only() -> None:
    client = FakeClient()
    repository = UserRepository(client, "users", "audit")
    saga: dict[str, object] = {
        "Update": {
            "TableName": "idempotency",
            "Key": serialized({"id": "resend-operation"}),
            "UpdateExpression": "SET #state = :completed",
        }
    }

    repository.complete_invitation_resend(
        audit={"PK": "RESOURCE#USER#user-1", "SK": "TS#time#EVENT#event-1"},
        saga_transition=saga,
        client_request_token="44444444-4444-4444-8444-444444444444",
    )

    assert client.transaction is not None
    items = client.transaction["TransactItems"]
    assert isinstance(items, list) and len(items) == 2
    assert items[0]["Put"]["TableName"] == "audit"
    assert items[0]["Put"]["ConditionExpression"] == (
        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
    )
    assert items[1] == saga
    assert client.transaction["ClientRequestToken"] == ("44444444-4444-4444-8444-444444444444")
    assert "CONTROL#ACTIVE_ADMIN_COUNT" not in repr(client.transaction)


def test_lists_profiles_through_name_index_with_opaque_position() -> None:
    client = FakeClient()
    last_key: dict[str, object] = {
        "PK": "USER#user-2",
        "SK": "PROFILE",
        "GSI1PK": "USERS",
        "GSI1SK": "NAME#ana#USER#user-2",
    }
    client.query_responses = [
        {
            "Items": [serialized({"PK": "USER#user-1", "SK": "PROFILE"})],
            "LastEvaluatedKey": serialized(last_key),
        }
    ]

    page = UserRepository(client, "users", "audit").list_profiles(
        name_prefix="ana", limit=20, position=None
    )

    assert page.items == [{"PK": "USER#user-1", "SK": "PROFILE"}]
    assert page.next_position is not None
    assert page.next_position.user_id == "user-2"
    assert page.next_position.normalized_name == "ana"
    query = client.query_calls[0]
    assert query["IndexName"] == "gsi-all-users-name"
    assert query["Limit"] == 20
    assert query["KeyConditionExpression"] == ("#gsi_pk = :users AND begins_with(#gsi_sk, :prefix)")
    assert query["ExpressionAttributeNames"] == {
        "#gsi_pk": "GSI1PK",
        "#gsi_sk": "GSI1SK",
    }
    expression_values = query["ExpressionAttributeValues"]
    assert isinstance(expression_values, dict)
    assert set(expression_values) == {":users", ":prefix"}
    assert "FilterExpression" not in query


def test_list_without_name_prefix_omits_unused_sort_key_alias() -> None:
    client = FakeClient()
    client.query_responses = [{"Items": []}]

    UserRepository(client, "users", "audit").list_profiles(
        name_prefix=None, limit=20, position=None
    )

    query = client.query_calls[0]
    assert query["KeyConditionExpression"] == "#gsi_pk = :users"
    assert query["ExpressionAttributeNames"] == {"#gsi_pk": "GSI1PK"}
    expression_values = query["ExpressionAttributeValues"]
    assert isinstance(expression_values, dict)
    assert set(expression_values) == {":users"}


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


def role_change(
    repository: UserRepository,
    client: FakeClient,
    *,
    old_role: str,
    new_role: str,
    status: str,
    version: int = 1,
) -> list[dict[str, object]]:
    repository.change_role(
        user_id="user-1",
        cognito_sub="sub-1",
        old_role=old_role,
        new_role=new_role,
        status=status,
        version=version,
        auth_version=3,
        updated_at="2026-09-14T14:00:00.000Z",
        actor_id="actor-1",
        audit={"PK": "RESOURCE#USER#user-1", "SK": "TS#time#EVENT#event-1"},
        idempotency_transition={"Update": {"TableName": "idempotency"}},
        client_request_token="55555555-5555-4555-8555-555555555555",
    )
    assert client.transaction is not None
    items = client.transaction["TransactItems"]
    assert isinstance(items, list)
    return items


@pytest.mark.parametrize("status", ["INVITED", "INACTIVE"])
def test_role_change_transaction_without_counter_has_four_items(status: str) -> None:
    client = FakeClient()
    items = role_change(
        UserRepository(client, "users", "audit"),
        client,
        old_role="OPERATOR",
        new_role="ADMIN",
        status=status,
    )
    assert len(items) == 4
    assert [next(iter(item)) for item in items] == ["Update", "Update", "Put", "Update"]
    assert "CONTROL#ACTIVE_ADMIN_COUNT" not in repr(items)

    profile = items[0]["Update"]
    auth = items[1]["Update"]
    assert isinstance(profile, dict) and isinstance(auth, dict)
    assert "authVersion = :next_auth_version" in profile["UpdateExpression"]
    assert "#version = :next_version" in profile["UpdateExpression"]
    assert "#role = :new_role" in auth["UpdateExpression"]
    assert "#status = :status" in profile["ConditionExpression"]
    assert "authVersion = :auth_version" in auth["ConditionExpression"]


@pytest.mark.parametrize(
    ("old_role", "new_role", "delta", "condition"),
    [
        ("OPERATOR", "ADMIN", 1, "activeAdminCount >= :one"),
        ("ADMIN", "OPERATOR", -1, "activeAdminCount > :one"),
    ],
)
def test_active_role_change_updates_counter_atomically(
    old_role: str, new_role: str, delta: int, condition: str
) -> None:
    client = FakeClient()
    items = role_change(
        UserRepository(client, "users", "audit"),
        client,
        old_role=old_role,
        new_role=new_role,
        status="ACTIVE",
    )
    assert len(items) == 5
    counter = items[2]["Update"]
    assert isinstance(counter, dict)
    assert counter["UpdateExpression"] == "ADD activeAdminCount :delta"
    assert condition in counter["ConditionExpression"]
    assert TypeDeserializer().deserialize(counter["ExpressionAttributeValues"][":delta"]) == delta
    audit = items[3]["Put"]
    assert isinstance(audit, dict) and audit["TableName"] == "audit"
    assert items[4] == {"Update": {"TableName": "idempotency"}}


def test_role_change_supports_legacy_version_one_but_not_other_stale_versions() -> None:
    client = FakeClient()
    first = role_change(
        UserRepository(client, "users", "audit"),
        client,
        old_role="OPERATOR",
        new_role="ADMIN",
        status="INVITED",
        version=1,
    )
    first_profile = first[0]["Update"]
    assert isinstance(first_profile, dict)
    assert (
        "attribute_not_exists(#version) OR #version = :version"
        in first_profile["ConditionExpression"]
    )

    second = role_change(
        UserRepository(client, "users", "audit"),
        client,
        old_role="ADMIN",
        new_role="OPERATOR",
        status="INACTIVE",
        version=2,
    )
    second_profile = second[0]["Update"]
    assert isinstance(second_profile, dict)
    condition = second_profile["ConditionExpression"]
    assert "attribute_not_exists(#version)" not in condition
    assert condition.endswith("#version = :version")


def test_role_change_noop_is_condition_check_plus_completion_only() -> None:
    client = FakeClient()
    transition: dict[str, object] = {"Update": {"TableName": "idempotency"}}
    UserRepository(client, "users", "audit").complete_role_change_noop(
        user_id="user-1",
        cognito_sub="sub-1",
        role="ADMIN",
        status="ACTIVE",
        version=1,
        auth_version=4,
        idempotency_transition=transition,
        client_request_token="55555555-5555-4555-8555-555555555555",
    )
    assert client.transaction is not None
    items = client.transaction["TransactItems"]
    assert isinstance(items, list) and len(items) == 2
    assert "ConditionCheck" in items[0]
    assert items[1] == transition
    rendered = repr(items)
    assert "USER_ROLE_CHANGED" not in rendered
    assert "CONTROL#ACTIVE_ADMIN_COUNT" not in rendered
    assert "UpdateExpression" not in repr(items[0])
