import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid5

import pytest
from aws_lambda_powertools.shared.json_encoder import Encoder
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from users_api.errors import ActivationConflictError, ActivationForbiddenError
from users_api.repositories.dynamodb_values import normalize_dynamodb_value
from users_api.services.activation_service import ActivationService

SUB = "11111111-1111-1111-1111-111111111111"
USER_ID = "01JUSER0000000000000000000"
KEY = "22222222-2222-4222-8222-222222222222"
NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


def client_error(code: str, operation: str = "PutItem") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "safe test"}}, operation)


class FakeUsers:
    def __init__(self, *, role: str = "ADMIN", status: str = "INVITED") -> None:
        self.authorization: dict[str, object] | None = {
            "userId": USER_ID,
            "role": role,
            "status": status,
            "authVersion": 1,
        }
        self.profile: dict[str, object] | None = {
            "userId": USER_ID,
            "cognitoSub": SUB,
            "role": role,
            "status": status,
            "authVersion": 1,
        }
        self.activations: list[dict[str, object]] = []
        self.activation_error: ClientError | None = None

    def get_authorization(self, cognito_sub: str) -> dict[str, object] | None:
        assert cognito_sub == SUB
        return self.authorization

    def get_profile(self, user_id: str) -> dict[str, object] | None:
        assert user_id == USER_ID
        return self.profile

    def activate(self, **kwargs: object) -> None:
        self.activations.append(kwargs)
        if self.activation_error is not None:
            error = self.activation_error
            if self.authorization is not None:
                self.authorization["status"] = "ACTIVE"
            if self.profile is not None:
                self.profile["status"] = "ACTIVE"
            raise error
        if self.authorization is not None:
            self.authorization["status"] = "ACTIVE"
        if self.profile is not None:
            self.profile["status"] = "ACTIVE"


class FakeCognito:
    def __init__(self) -> None:
        self.user: dict[str, Any] = {
            "Username": USER_ID,
            "Enabled": True,
            "UserStatus": "CONFIRMED",
            "UserAttributes": [
                {"Name": "sub", "Value": SUB},
                {"Name": "email_verified", "Value": "true"},
            ],
            "UserMFASettingList": [],
        }
        self.factors: dict[str, Any] = {
            "Username": USER_ID,
            "ConfiguredUserAuthFactors": ["SOFTWARE_TOKEN"],
        }
        self.error: ClientError | None = None

    def get_user(self, user_id: str) -> dict[str, Any]:
        assert user_id == USER_ID
        if self.error is not None:
            raise self.error
        return self.user

    def get_user_auth_factors(self, user_id: str) -> dict[str, Any]:
        assert user_id == USER_ID
        return self.factors


class FakeIdempotency:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, object]] = {}
        self.complete_error: ClientError | None = None

    def start(self, record: dict[str, object]) -> None:
        record_id = str(record["id"])
        if record_id in self.records:
            raise client_error("ConditionalCheckFailedException")
        self.records[record_id] = dict(record)

    def get(self, record_id: str) -> dict[str, object] | None:
        return self.records.get(record_id)

    def complete(self, *, record_id: str, response: dict[str, object], updated_at: str) -> None:
        if self.complete_error is not None:
            raise self.complete_error
        record = self.records[record_id]
        if record["state"] != "STARTED":
            raise client_error("ConditionalCheckFailedException", "UpdateItem")
        record.update(state="COMPLETED", response=response, updatedAt=updated_at)


class ConcurrentCompletionIdempotency(FakeIdempotency):
    def complete(self, *, record_id: str, response: dict[str, object], updated_at: str) -> None:
        self.records[record_id].update(state="COMPLETED", response=response, updatedAt=updated_at)
        raise client_error("ConditionalCheckFailedException", "UpdateItem")


class DynamoCompletedIdempotency(FakeIdempotency):
    def get(self, record_id: str) -> dict[str, object] | None:
        normalized = normalize_dynamodb_value(super().get(record_id))
        return normalized if isinstance(normalized, dict) else None


def make_service(
    users: FakeUsers | None = None,
    cognito: FakeCognito | None = None,
    idempotency: FakeIdempotency | None = None,
) -> tuple[ActivationService, FakeUsers, FakeCognito, FakeIdempotency]:
    actual_users = users or FakeUsers()
    actual_cognito = cognito or FakeCognito()
    actual_idempotency = idempotency or FakeIdempotency()
    service = ActivationService(
        actual_users,
        actual_cognito,
        actual_idempotency,
        environment="dev",
        audit_retention_days=90,
        clock=lambda: NOW,
        identifier_factory=lambda: UUID("33333333-3333-4333-8333-333333333333"),
    )
    return service, actual_users, actual_cognito, actual_idempotency


def activate(service: ActivationService) -> dict[str, object]:
    return service.activate_current_user(
        cognito_sub=SUB,
        idempotency_key=KEY,
        request_id="request-123",
    )


def started_record(service: ActivationService) -> dict[str, object]:
    record_id = f"HTTP#dev#{USER_ID}#activate-current-user#{KEY}"
    return {
        "id": record_id,
        "environment": "dev",
        "actorId": USER_ID,
        "operation": "activate-current-user",
        "target": USER_ID,
        "idempotencyKey": KEY,
        "payloadHash": service._payload_hash(USER_ID),
        "state": "STARTED",
        "eventId": "44444444-4444-4444-8444-444444444444",
        "correlationId": "original-request",
        "occurredAt": "2026-09-01T10:30:00.000Z",
        "createdAt": "2026-09-01T10:30:00.000Z",
        "updatedAt": "2026-09-01T10:30:00.000Z",
        "expiration": 1798626600,
    }


@pytest.mark.parametrize("role", ["ADMIN", "OPERATOR"])
def test_invited_user_is_activated_for_allowed_roles(role: str) -> None:
    service, users, _, idempotency = make_service(FakeUsers(role=role))

    assert activate(service) == {
        "userId": USER_ID,
        "role": role,
        "status": "ACTIVE",
        "authVersion": 1,
    }
    assert len(users.activations) == 1
    assert users.activations[0]["role"] == role
    assert users.activations[0]["expires_at"] == 1796126400
    assert next(iter(idempotency.records.values()))["state"] == "COMPLETED"


def test_already_active_uses_no_activation_transaction() -> None:
    service, users, _, _ = make_service(FakeUsers(status="ACTIVE"))
    assert activate(service)["status"] == "ACTIVE"
    assert users.activations == []


def test_concurrent_idempotency_completion_returns_preserved_response() -> None:
    idempotency = ConcurrentCompletionIdempotency()
    service, users, _, _ = make_service(FakeUsers(status="ACTIVE"), idempotency=idempotency)
    assert activate(service)["status"] == "ACTIVE"
    assert users.activations == []


def test_completed_replay_returns_preserved_response() -> None:
    service, users, _, _ = make_service()
    first = activate(service)
    second = activate(service)
    assert second == first
    assert len(users.activations) == 1


def test_completed_replay_normalizes_persisted_response_without_changing_context() -> None:
    idempotency = DynamoCompletedIdempotency()
    service, users, _, _ = make_service(idempotency=idempotency)
    record = started_record(service)
    record.update(
        state="COMPLETED",
        response={
            "userId": USER_ID,
            "role": "ADMIN",
            "status": "ACTIVE",
            "authVersion": Decimal("1"),
        },
    )
    record_id = str(record["id"])
    idempotency.records[record_id] = record

    first_response = {
        "userId": USER_ID,
        "role": "ADMIN",
        "status": "ACTIVE",
        "authVersion": 1,
    }
    replay = activate(service)

    assert replay == first_response
    assert type(replay["authVersion"]) is int
    assert type(replay["authVersion"]) is type(first_response["authVersion"])
    serialized_replay = json.loads(json.dumps(replay, cls=Encoder))
    assert serialized_replay["authVersion"] == 1
    assert type(serialized_replay["authVersion"]) is int
    assert users.activations == []
    assert record["eventId"] == "44444444-4444-4444-8444-444444444444"
    assert record["correlationId"] == "original-request"
    assert record["occurredAt"] == "2026-09-01T10:30:00.000Z"


def test_response_lost_reconciles_started_record_without_duplicate_effects() -> None:
    idempotency = FakeIdempotency()
    service, users, _, _ = make_service(idempotency=idempotency)
    idempotency.complete_error = client_error("InternalServerError", "UpdateItem")
    with pytest.raises(ClientError):
        activate(service)
    assert len(users.activations) == 1

    idempotency.complete_error = None
    assert activate(service)["status"] == "ACTIVE"
    assert len(users.activations) == 1


def test_concurrent_transaction_loser_returns_active_without_second_effect() -> None:
    users = FakeUsers()
    users.activation_error = client_error("TransactionCanceledException", "TransactWriteItems")
    service, _, _, _ = make_service(users)
    assert activate(service)["status"] == "ACTIVE"
    assert len(users.activations) == 1


def test_started_invited_replay_resumes_with_preserved_context() -> None:
    service, users, _, idempotency = make_service()
    generated_ids: list[UUID] = []

    def generate_id() -> UUID:
        value = UUID("55555555-5555-4555-8555-555555555555")
        generated_ids.append(value)
        return value

    service._identifier_factory = generate_id
    record = started_record(service)
    record_id = str(record["id"])
    idempotency.records[record_id] = record

    assert activate(service)["status"] == "ACTIVE"

    assert len(idempotency.records) == 1
    assert generated_ids == []
    assert len(users.activations) == 1
    transaction = users.activations[0]
    assert transaction["event_id"] == record["eventId"]
    assert transaction["correlation_id"] == record["correlationId"]
    assert transaction["occurred_at"] == record["occurredAt"]
    assert transaction["expires_at"] == 1796034600
    assert transaction["client_request_token"] == str(uuid5(UUID(int=0), record_id))
    assert idempotency.records[record_id]["state"] == "COMPLETED"
    assert idempotency.records[record_id]["updatedAt"] == record["occurredAt"]


def test_started_active_replay_completes_without_duplicate_effects() -> None:
    service, users, _, idempotency = make_service(FakeUsers(status="ACTIVE"))
    record = started_record(service)
    idempotency.records[str(record["id"])] = record

    assert activate(service)["status"] == "ACTIVE"
    assert users.activations == []
    assert record["state"] == "COMPLETED"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("environment", "prod"),
        ("actorId", "other"),
        ("target", "other"),
        ("operation", "other"),
        ("idempotencyKey", "55555555-5555-4555-8555-555555555555"),
        ("payloadHash", "different"),
    ],
)
def test_started_replay_rejects_incompatible_context(field: str, value: object) -> None:
    service, users, _, idempotency = make_service()
    record = started_record(service)
    record[field] = value
    idempotency.records[str(record["id"])] = record

    with pytest.raises(ActivationConflictError):
        activate(service)
    assert users.activations == []


def test_started_replay_rejects_incoherent_application_state() -> None:
    users = FakeUsers()
    assert users.profile is not None
    users.profile["status"] = "ACTIVE"
    service, users, _, idempotency = make_service(users)
    record = started_record(service)
    idempotency.records[str(record["id"])] = record

    with pytest.raises(ActivationForbiddenError):
        activate(service)
    assert users.activations == []


def test_incompatible_idempotency_context_conflicts() -> None:
    service, _, _, idempotency = make_service(FakeUsers(status="ACTIVE"))
    record_id = f"HTTP#dev#{USER_ID}#activate-current-user#{KEY}"
    idempotency.records[record_id] = {
        "id": record_id,
        "operation": "another-operation",
        "payloadHash": "different",
        "state": "COMPLETED",
    }
    with pytest.raises(ActivationConflictError):
        activate(service)


@pytest.mark.parametrize(
    ("target", "field", "value", "error_type"),
    [
        ("authorization", "status", "INACTIVE", ActivationConflictError),
        ("authorization", "role", "VIEWER", ActivationForbiddenError),
        ("authorization", "authVersion", 2, ActivationForbiddenError),
        ("authorization", "authVersion", True, ActivationForbiddenError),
        ("authorization", "authVersion", "1", ActivationForbiddenError),
        ("authorization", "authVersion", 1.5, ActivationForbiddenError),
        ("profile", "userId", "other", ActivationForbiddenError),
        ("profile", "cognitoSub", "other", ActivationForbiddenError),
        ("profile", "role", "OPERATOR", ActivationForbiddenError),
        ("profile", "authVersion", 2, ActivationForbiddenError),
    ],
)
def test_application_state_is_strictly_reconciled(
    target: str, field: str, value: object, error_type: type[Exception]
) -> None:
    users = FakeUsers()
    item = users.authorization if target == "authorization" else users.profile
    assert item is not None
    item[field] = value
    service, _, _, idempotency = make_service(users)
    with pytest.raises(error_type):
        activate(service)
    assert idempotency.records == {}


@pytest.mark.parametrize("missing", ["authorization", "profile"])
def test_missing_application_identity_is_forbidden(missing: str) -> None:
    users = FakeUsers()
    setattr(users, missing, None)
    service, _, _, _ = make_service(users)
    with pytest.raises(ActivationForbiddenError):
        activate(service)


@pytest.mark.parametrize(
    ("field", "value"),
    [("Enabled", False), ("UserStatus", "FORCE_CHANGE_PASSWORD")],
)
def test_cognito_account_must_be_ready(field: str, value: object) -> None:
    cognito = FakeCognito()
    cognito.user[field] = value
    service, _, _, idempotency = make_service(cognito=cognito)
    with pytest.raises(ActivationConflictError):
        activate(service)
    assert idempotency.records == {}


def test_email_must_be_verified() -> None:
    cognito = FakeCognito()
    cognito.user["UserAttributes"][1]["Value"] = "false"
    service, _, _, _ = make_service(cognito=cognito)
    with pytest.raises(ActivationConflictError):
        activate(service)


def test_software_token_is_required_but_mfa_setting_list_is_not() -> None:
    cognito = FakeCognito()
    cognito.user.pop("UserMFASettingList")
    service, _, _, _ = make_service(cognito=cognito)
    assert activate(service)["status"] == "ACTIVE"

    cognito = FakeCognito()
    cognito.factors["ConfiguredUserAuthFactors"] = []
    service, _, _, _ = make_service(cognito=cognito)
    with pytest.raises(ActivationConflictError):
        activate(service)


@pytest.mark.parametrize("source", ["user", "factors", "sub"])
def test_cognito_identity_mismatch_is_forbidden(source: str) -> None:
    cognito = FakeCognito()
    if source == "user":
        cognito.user["Username"] = "other"
    elif source == "factors":
        cognito.factors["Username"] = "other"
    else:
        cognito.user["UserAttributes"][0]["Value"] = "other"
    service, _, _, _ = make_service(cognito=cognito)
    with pytest.raises(ActivationForbiddenError):
        activate(service)


def test_missing_cognito_user_is_forbidden() -> None:
    cognito = FakeCognito()
    cognito.error = client_error("UserNotFoundException", "AdminGetUser")
    service, _, _, _ = make_service(cognito=cognito)
    with pytest.raises(ActivationForbiddenError):
        activate(service)


def test_unexpected_cognito_error_is_not_exposed_as_domain_conflict() -> None:
    cognito = FakeCognito()
    cognito.error = client_error("InternalErrorException", "AdminGetUser")
    service, _, _, _ = make_service(cognito=cognito)
    with pytest.raises(ClientError):
        activate(service)
