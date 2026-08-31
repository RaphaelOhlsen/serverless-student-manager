from typing import NoReturn

import pytest

from tools.bootstrap_admin.cognito_repository import (
    CognitoIdentityValidationError,
    ReconciledCognitoIdentity,
)
from tools.verify_first_admin_email.discovery import (
    FirstAdminEmailTarget,
    VerifyFirstAdminEmailDiscovery,
    VerifyFirstAdminEmailDiscoveryConfig,
)

_USER_ID = "323e4567-e89b-42d3-a456-426614174002"
_BOOTSTRAP_OPERATION_ID = "223e4567-e89b-42d3-a456-426614174001"
_COGNITO_SUB = "cognito-sub-123"


class AwsError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeProvisioningReader:
    def __init__(self) -> None:
        self.marker: dict[str, object] | None = _marker()
        self.user: dict[str, object] | None = _user()
        self.projection: dict[str, object] | None = _projection()
        self.errors: dict[str, BaseException] = {}
        self.calls: list[tuple[str, object]] = []

    def get_bootstrap_marker(
        self,
        *,
        users_table_name: str,
    ) -> dict[str, object] | None:
        self.calls.append(("marker", users_table_name))
        if "marker" in self.errors:
            raise self.errors["marker"]
        return self.marker

    def get_user_profile(
        self,
        *,
        users_table_name: str,
        user_id: str,
    ) -> dict[str, object] | None:
        self.calls.append(("user", (users_table_name, user_id)))
        if "user" in self.errors:
            raise self.errors["user"]
        return self.user

    def get_cognito_projection(
        self,
        *,
        users_table_name: str,
        cognito_sub: str,
    ) -> dict[str, object] | None:
        self.calls.append(("projection", (users_table_name, cognito_sub)))
        if "projection" in self.errors:
            raise self.errors["projection"]
        return self.projection

    def put_item(self, **kwargs: object) -> NoReturn:
        raise AssertionError("discovery must not write DynamoDB")

    def transact_write_items(self, **kwargs: object) -> NoReturn:
        raise AssertionError("discovery must not write DynamoDB")


class FakeCognitoReader:
    def __init__(self, *, verified: bool = False) -> None:
        self.identity = ReconciledCognitoIdentity(
            cognito_sub=_COGNITO_SUB,
            verified=verified,
        )
        self.error: BaseException | None = None
        self.calls: list[dict[str, str]] = []

    def get_reconciled_user_identity(
        self,
        *,
        user_pool_id: str,
        user_id: str,
        expected_email: str,
        expected_sub: str,
    ) -> ReconciledCognitoIdentity:
        self.calls.append(
            {
                "user_pool_id": user_pool_id,
                "user_id": user_id,
                "expected_email": expected_email,
                "expected_sub": expected_sub,
            }
        )
        if self.error is not None:
            raise self.error
        return self.identity

    def admin_update_user_attributes(self, **kwargs: object) -> NoReturn:
        raise AssertionError("discovery must not update Cognito")

    def create_suppressed_user(self, **kwargs: object) -> NoReturn:
        raise AssertionError("discovery must not create Cognito users")

    def delete_user(self, **kwargs: object) -> NoReturn:
        raise AssertionError("discovery must not delete Cognito users")

    def disable_user(self, **kwargs: object) -> NoReturn:
        raise AssertionError("discovery must not disable Cognito users")

    def resend_invitation(self, **kwargs: object) -> NoReturn:
        raise AssertionError("discovery must not resend invitations")


def _marker() -> dict[str, object]:
    return {
        "PK": "CONTROL#FIRST_ADMIN_BOOTSTRAP",
        "SK": "CONTROL",
        "userId": _USER_ID,
        "operationId": _BOOTSTRAP_OPERATION_ID,
        "createdAt": "2026-08-20T13:45:12.347Z",
        "createdBy": "github:original",
    }


def _user(*, status: str = "INVITED") -> dict[str, object]:
    return {
        "PK": f"USER#{_USER_ID}",
        "SK": "PROFILE",
        "userId": _USER_ID,
        "cognitoSub": _COGNITO_SUB,
        "email": "admin@example.com",
        "role": "ADMIN",
        "status": status,
        "authVersion": 1,
    }


def _projection(*, status: str = "INVITED") -> dict[str, object]:
    return {
        "PK": f"COGNITO#{_COGNITO_SUB}",
        "SK": "AUTHORIZATION",
        "userId": _USER_ID,
        "role": "ADMIN",
        "status": status,
        "authVersion": 1,
    }


def _discovery(
    provisioning: FakeProvisioningReader | None = None,
    cognito: FakeCognitoReader | None = None,
) -> tuple[
    VerifyFirstAdminEmailDiscovery,
    FakeProvisioningReader,
    FakeCognitoReader,
]:
    provisioning = provisioning or FakeProvisioningReader()
    cognito = cognito or FakeCognitoReader()
    return (
        VerifyFirstAdminEmailDiscovery(
            config=VerifyFirstAdminEmailDiscoveryConfig(
                users_table_name="users-table",
                user_pool_id="pool-123",
            ),
            provisioning_reader=provisioning,
            cognito_reader=cognito,
        ),
        provisioning,
        cognito,
    )


@pytest.mark.parametrize(
    ("verified", "expected_status"),
    [(False, "NEEDS_VERIFICATION"), (True, "ALREADY_VERIFIED")],
)
def test_reconciled_identity_returns_exact_contract_status(
    verified: bool,
    expected_status: str,
) -> None:
    discovery, provisioning, cognito = _discovery(cognito=FakeCognitoReader(verified=verified))

    result = discovery.discover()

    assert result.status == expected_status
    assert result.target == FirstAdminEmailTarget(
        user_id=_USER_ID,
        email="admin@example.com",
        cognito_sub=_COGNITO_SUB,
    )
    assert result.authoritative_user_id == _USER_ID
    assert [call[0] for call in provisioning.calls] == [
        "marker",
        "user",
        "projection",
    ]
    assert cognito.calls == [
        {
            "user_pool_id": "pool-123",
            "user_id": _USER_ID,
            "expected_email": "admin@example.com",
            "expected_sub": _COGNITO_SUB,
        }
    ]


@pytest.mark.parametrize("status", ["INVITED", "ACTIVE"])
def test_compatible_user_statuses_are_reconciled(status: str) -> None:
    provisioning = FakeProvisioningReader()
    provisioning.user = _user(status=status)
    provisioning.projection = _projection(status=status)
    discovery, _, _ = _discovery(provisioning)

    assert discovery.discover().status == "NEEDS_VERIFICATION"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("PK", "CONTROL#WRONG"),
        ("SK", "WRONG"),
        ("userId", None),
        ("userId", "invalid"),
        ("operationId", None),
        ("operationId", "invalid"),
        ("createdAt", ""),
        ("createdBy", 1),
    ],
)
def test_incompatible_marker_stops_discovery(
    field: str,
    value: object,
) -> None:
    provisioning = FakeProvisioningReader()
    assert provisioning.marker is not None
    provisioning.marker[field] = value
    discovery, provisioning, cognito = _discovery(provisioning)

    result = discovery.discover()

    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.target is None
    assert result.authoritative_user_id is None
    assert [call[0] for call in provisioning.calls] == ["marker"]
    assert cognito.calls == []


def test_missing_marker_requires_reconciliation() -> None:
    provisioning = FakeProvisioningReader()
    provisioning.marker = None
    discovery, provisioning, cognito = _discovery(provisioning)

    result = discovery.discover()

    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.target is None
    assert result.authoritative_user_id is None
    assert [call[0] for call in provisioning.calls] == ["marker"]
    assert cognito.calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("PK", "USER#wrong"),
        ("SK", "WRONG"),
        ("userId", "other-user"),
        ("role", "OPERATOR"),
        ("status", "INACTIVE"),
        ("email", ""),
        ("cognitoSub", None),
        ("authVersion", None),
        ("authVersion", False),
        ("authVersion", "1"),
    ],
)
def test_incompatible_user_stops_before_projection_and_cognito(
    field: str,
    value: object,
) -> None:
    provisioning = FakeProvisioningReader()
    assert provisioning.user is not None
    provisioning.user[field] = value
    discovery, provisioning, cognito = _discovery(provisioning)

    result = discovery.discover()

    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.target is None
    assert result.authoritative_user_id is None
    assert [call[0] for call in provisioning.calls] == ["marker", "user"]
    assert cognito.calls == []


def test_missing_user_requires_reconciliation() -> None:
    provisioning = FakeProvisioningReader()
    provisioning.user = None
    discovery, provisioning, cognito = _discovery(provisioning)

    result = discovery.discover()

    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.target is None
    assert result.authoritative_user_id is None
    assert [call[0] for call in provisioning.calls] == ["marker", "user"]
    assert cognito.calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("PK", "COGNITO#wrong"),
        ("SK", "WRONG"),
        ("userId", "other-user"),
        ("role", "OPERATOR"),
        ("status", "ACTIVE"),
        ("authVersion", None),
        ("authVersion", False),
        ("authVersion", "1"),
        ("authVersion", 2),
    ],
)
def test_incompatible_projection_stops_before_cognito(
    field: str,
    value: object,
) -> None:
    provisioning = FakeProvisioningReader()
    assert provisioning.projection is not None
    provisioning.projection[field] = value
    discovery, provisioning, cognito = _discovery(provisioning)

    result = discovery.discover()

    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.target is None
    assert result.authoritative_user_id == _USER_ID
    assert [call[0] for call in provisioning.calls] == [
        "marker",
        "user",
        "projection",
    ]
    assert cognito.calls == []


def test_missing_projection_requires_reconciliation() -> None:
    provisioning = FakeProvisioningReader()
    provisioning.projection = None
    discovery, _, cognito = _discovery(provisioning)

    result = discovery.discover()

    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.target is None
    assert result.authoritative_user_id == _USER_ID
    assert cognito.calls == []


@pytest.mark.parametrize(
    "error",
    [
        CognitoIdentityValidationError("incompatible identity"),
        AwsError("UserNotFoundException"),
    ],
)
def test_confirmed_cognito_inconsistency_requires_reconciliation(
    error: BaseException,
) -> None:
    cognito = FakeCognitoReader()
    cognito.error = error
    discovery, _, _ = _discovery(cognito=cognito)

    result = discovery.discover()

    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.target is None
    assert result.authoritative_user_id == _USER_ID


def test_defensive_sub_check_requires_reconciliation() -> None:
    cognito = FakeCognitoReader()
    cognito.identity = ReconciledCognitoIdentity(
        cognito_sub="different-sub",
        verified=False,
    )
    discovery, _, _ = _discovery(cognito=cognito)

    result = discovery.discover()

    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.target is None
    assert result.authoritative_user_id == _USER_ID


@pytest.mark.parametrize(
    "reason",
    [
        "username does not match",
        "sub does not match",
        "email does not match",
        "email_verified value is incompatible",
    ],
)
def test_late_cognito_incompatibility_exposes_only_authoritative_user_id(
    reason: str,
) -> None:
    cognito = FakeCognitoReader()
    cognito.error = CognitoIdentityValidationError(reason)
    discovery, _, _ = _discovery(cognito=cognito)

    result = discovery.discover()

    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.target is None
    assert result.authoritative_user_id == _USER_ID
    assert not hasattr(result, "email")
    assert not hasattr(result, "cognito_sub")


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("timeout"),
        AwsError("InternalErrorException"),
        AwsError("TooManyRequestsException"),
        AwsError("AccessDeniedException"),
        RuntimeError("unclassified"),
    ],
)
def test_inconclusive_cognito_error_is_propagated(error: BaseException) -> None:
    cognito = FakeCognitoReader()
    cognito.error = error
    discovery, _, _ = _discovery(cognito=cognito)

    with pytest.raises(type(error), match=str(error)):
        discovery.discover()


@pytest.mark.parametrize("stage", ["marker", "user", "projection"])
def test_dynamodb_read_error_is_propagated_and_stops_later_reads(
    stage: str,
) -> None:
    provisioning = FakeProvisioningReader()
    provisioning.errors[stage] = RuntimeError(f"{stage} read failed")
    discovery, provisioning, cognito = _discovery(provisioning)

    with pytest.raises(RuntimeError, match=f"{stage} read failed"):
        discovery.discover()

    expected = {
        "marker": ["marker"],
        "user": ["marker", "user"],
        "projection": ["marker", "user", "projection"],
    }
    assert [call[0] for call in provisioning.calls] == expected[stage]
    assert cognito.calls == []


def test_discovery_is_strictly_read_only() -> None:
    discovery, provisioning, cognito = _discovery()

    assert discovery.discover().status == "NEEDS_VERIFICATION"
    assert [call[0] for call in provisioning.calls] == [
        "marker",
        "user",
        "projection",
    ]
    assert len(cognito.calls) == 1
