from typing import NoReturn

import pytest

from tools.bootstrap_admin.cognito_repository import CognitoIdentityValidationError
from tools.bootstrap_admin.resume_discovery import (
    FirstAdminInvitationTarget,
    ResumeDiscoveryResult,
    ResumeInvitationDiscovery,
    ResumeInvitationDiscoveryConfig,
    ResumeInvitationOperationIdConflictError,
)

_RESUME_OPERATION_ID = "123e4567-e89b-42d3-a456-426614174000"
_BOOTSTRAP_OPERATION_ID = "223e4567-e89b-42d3-a456-426614174001"
_USER_ID = "323e4567-e89b-42d3-a456-426614174002"
_COGNITO_SUB = "cognito-sub-123"


class AwsError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeProvisioningReader:
    def __init__(
        self,
        *,
        marker: dict[str, object] | None = None,
        user_profile: dict[str, object] | None = None,
        cognito_projection: dict[str, object] | None = None,
    ) -> None:
        self.marker: dict[str, object] | None = _marker() if marker is None else marker
        self.user_profile: dict[str, object] | None = (
            _user_profile() if user_profile is None else user_profile
        )
        self.cognito_projection: dict[str, object] | None = (
            _cognito_projection() if cognito_projection is None else cognito_projection
        )
        self.marker_error: BaseException | None = None
        self.user_error: BaseException | None = None
        self.projection_error: BaseException | None = None
        self.calls: list[tuple[str, object]] = []
        self.forbidden_calls: list[str] = []

    def get_bootstrap_marker(
        self,
        *,
        users_table_name: str,
    ) -> dict[str, object] | None:
        self.calls.append(("marker", users_table_name))
        if self.marker_error is not None:
            raise self.marker_error
        return self.marker

    def get_user_profile(
        self,
        *,
        users_table_name: str,
        user_id: str,
    ) -> dict[str, object] | None:
        self.calls.append(("user", (users_table_name, user_id)))
        if self.user_error is not None:
            raise self.user_error
        return self.user_profile

    def get_cognito_projection(
        self,
        *,
        users_table_name: str,
        cognito_sub: str,
    ) -> dict[str, object] | None:
        self.calls.append(("projection", (users_table_name, cognito_sub)))
        if self.projection_error is not None:
            raise self.projection_error
        return self.cognito_projection

    def get_unique_email(self, **kwargs: object) -> NoReturn:
        self.forbidden_calls.append("get_unique_email")
        raise AssertionError("get_unique_email must not be called")

    def get_audit_event(self, **kwargs: object) -> NoReturn:
        self.forbidden_calls.append("get_audit_event")
        raise AssertionError("get_audit_event must not be called")

    def persist_first_admin_with_audit(self, **kwargs: object) -> NoReturn:
        self.forbidden_calls.append("persist_first_admin_with_audit")
        raise AssertionError("persist_first_admin_with_audit must not be called")


class FakeCognitoReader:
    def __init__(self, result: str = _COGNITO_SUB) -> None:
        self.result = result
        self.error: BaseException | None = None
        self.calls: list[dict[str, str]] = []
        self.forbidden_calls: list[str] = []

    def get_existing_user_sub(
        self,
        *,
        user_pool_id: str,
        user_id: str,
        expected_email: str,
    ) -> str:
        self.calls.append(
            {
                "user_pool_id": user_pool_id,
                "user_id": user_id,
                "expected_email": expected_email,
            }
        )
        if self.error is not None:
            raise self.error
        return self.result

    def resend_invitation(self, **kwargs: object) -> NoReturn:
        self.forbidden_calls.append("resend_invitation")
        raise AssertionError("resend_invitation must not be called")

    def create_suppressed_user(self, **kwargs: object) -> NoReturn:
        self.forbidden_calls.append("create_suppressed_user")
        raise AssertionError("create_suppressed_user must not be called")

    def delete_user(self, **kwargs: object) -> NoReturn:
        self.forbidden_calls.append("delete_user")
        raise AssertionError("delete_user must not be called")

    def disable_user(self, **kwargs: object) -> NoReturn:
        self.forbidden_calls.append("disable_user")
        raise AssertionError("disable_user must not be called")


def _marker() -> dict[str, object]:
    return {
        "PK": "CONTROL#FIRST_ADMIN_BOOTSTRAP",
        "SK": "CONTROL",
        "userId": _USER_ID,
        "operationId": _BOOTSTRAP_OPERATION_ID,
        "createdAt": "2026-08-20T13:45:12.347Z",
        "createdBy": "github:original",
    }


def _user_profile(*, status: str = "INVITED") -> dict[str, object]:
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


def _cognito_projection(*, status: str = "INVITED") -> dict[str, object]:
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
) -> tuple[ResumeInvitationDiscovery, FakeProvisioningReader, FakeCognitoReader]:
    provisioning = provisioning or FakeProvisioningReader()
    cognito = cognito or FakeCognitoReader()
    discovery = ResumeInvitationDiscovery(
        config=ResumeInvitationDiscoveryConfig(
            users_table_name="users-table",
            user_pool_id="pool-123",
        ),
        provisioning_reader=provisioning,
        cognito_reader=cognito,
    )
    return discovery, provisioning, cognito


def _discover(discovery: ResumeInvitationDiscovery) -> ResumeDiscoveryResult:
    return discovery.discover(resume_operation_id=_RESUME_OPERATION_ID)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("PK", "CONTROL#WRONG"),
        ("SK", "WRONG"),
        ("userId", None),
        ("userId", "invalid-uuid"),
        ("operationId", None),
        ("operationId", "invalid-uuid"),
        ("createdAt", ""),
        ("createdBy", 123),
    ],
)
def test_invalid_marker_returns_reconciliation_and_stops_reads(
    field: str,
    value: object,
) -> None:
    marker = _marker()
    marker[field] = value
    discovery, provisioning, cognito = _discovery(FakeProvisioningReader(marker=marker))

    result = _discover(discovery)

    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.target is None
    assert provisioning.calls == [("marker", "users-table")]
    assert cognito.calls == []


def test_missing_marker_returns_reconciliation_and_stops_reads() -> None:
    provisioning = FakeProvisioningReader()
    provisioning.marker = None
    discovery, provisioning, cognito = _discovery(provisioning)

    result = _discover(discovery)

    assert result.status == "RECONCILIATION_REQUIRED"
    assert provisioning.calls == [("marker", "users-table")]
    assert cognito.calls == []


def test_equal_resume_and_bootstrap_operation_ids_raise_before_user_read() -> None:
    marker = _marker()
    marker["operationId"] = _RESUME_OPERATION_ID
    discovery, provisioning, cognito = _discovery(FakeProvisioningReader(marker=marker))

    with pytest.raises(ResumeInvitationOperationIdConflictError):
        _discover(discovery)

    assert provisioning.calls == [("marker", "users-table")]
    assert cognito.calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("PK", "USER#wrong"),
        ("SK", "WRONG"),
        ("userId", "423e4567-e89b-42d3-a456-426614174003"),
        ("role", "OPERATOR"),
        ("status", "INACTIVE"),
        ("email", ""),
        ("cognitoSub", None),
        ("authVersion", None),
        ("authVersion", False),
        ("authVersion", "1"),
    ],
)
def test_invalid_user_returns_reconciliation_before_projection_or_cognito(
    field: str,
    value: object,
) -> None:
    user = _user_profile()
    user[field] = value
    discovery, provisioning, cognito = _discovery(FakeProvisioningReader(user_profile=user))

    result = _discover(discovery)

    assert result.status == "RECONCILIATION_REQUIRED"
    assert [call[0] for call in provisioning.calls] == ["marker", "user"]
    assert cognito.calls == []


def test_user_without_user_id_attribute_is_accepted() -> None:
    user = _user_profile()
    del user["userId"]
    discovery, provisioning, cognito = _discovery(FakeProvisioningReader(user_profile=user))

    result = _discover(discovery)

    assert result.status == "INVITED_CONSISTENT"
    assert [call[0] for call in provisioning.calls] == [
        "marker",
        "user",
        "projection",
    ]
    assert len(cognito.calls) == 1


def test_missing_user_returns_reconciliation_before_projection_or_cognito() -> None:
    provisioning = FakeProvisioningReader()
    provisioning.user_profile = None
    discovery, provisioning, cognito = _discovery(provisioning)

    result = _discover(discovery)

    assert result.status == "RECONCILIATION_REQUIRED"
    assert [call[0] for call in provisioning.calls] == ["marker", "user"]
    assert cognito.calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("PK", "COGNITO#wrong"),
        ("SK", "WRONG"),
        ("userId", "423e4567-e89b-42d3-a456-426614174003"),
        ("role", "OPERATOR"),
        ("status", "ACTIVE"),
        ("authVersion", None),
        ("authVersion", False),
        ("authVersion", "1"),
        ("authVersion", 2),
    ],
)
def test_invalid_projection_returns_reconciliation_before_cognito(
    field: str,
    value: object,
) -> None:
    projection = _cognito_projection()
    projection[field] = value
    discovery, provisioning, cognito = _discovery(
        FakeProvisioningReader(cognito_projection=projection)
    )

    result = _discover(discovery)

    assert result.status == "RECONCILIATION_REQUIRED"
    assert [call[0] for call in provisioning.calls] == [
        "marker",
        "user",
        "projection",
    ]
    assert cognito.calls == []


def test_missing_projection_returns_reconciliation_before_cognito() -> None:
    provisioning = FakeProvisioningReader()
    provisioning.cognito_projection = None
    discovery, provisioning, cognito = _discovery(provisioning)

    result = _discover(discovery)

    assert result.status == "RECONCILIATION_REQUIRED"
    assert [call[0] for call in provisioning.calls] == [
        "marker",
        "user",
        "projection",
    ]
    assert cognito.calls == []


@pytest.mark.parametrize(
    "error",
    [
        AwsError("UserNotFoundException"),
        CognitoIdentityValidationError("incompatible identity"),
    ],
)
def test_confirmed_cognito_inconsistency_returns_reconciliation(
    error: BaseException,
) -> None:
    cognito = FakeCognitoReader()
    cognito.error = error
    discovery, provisioning, cognito = _discovery(cognito=cognito)

    result = _discover(discovery)

    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.target is None
    assert [call[0] for call in provisioning.calls] == [
        "marker",
        "user",
        "projection",
    ]
    assert len(cognito.calls) == 1


def test_different_cognito_sub_returns_reconciliation() -> None:
    discovery, _, cognito = _discovery(cognito=FakeCognitoReader(result="different-sub"))

    result = _discover(discovery)

    assert result.status == "RECONCILIATION_REQUIRED"
    assert len(cognito.calls) == 1


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("timeout"),
        AwsError("InternalErrorException"),
        AwsError("TooManyRequestsException"),
        AwsError("AccessDeniedException"),
    ],
)
def test_inconclusive_cognito_error_is_propagated(error: BaseException) -> None:
    cognito = FakeCognitoReader()
    cognito.error = error
    discovery, _, cognito = _discovery(cognito=cognito)

    with pytest.raises(type(error), match=str(error)):
        _discover(discovery)

    assert len(cognito.calls) == 1


@pytest.mark.parametrize("stage", ["marker", "user", "projection"])
def test_dynamodb_read_error_is_propagated_and_stops_later_reads(stage: str) -> None:
    provisioning = FakeProvisioningReader()
    error = RuntimeError(f"{stage} read failed")
    setattr(provisioning, f"{stage}_error", error)
    discovery, provisioning, cognito = _discovery(provisioning)

    with pytest.raises(RuntimeError, match=f"{stage} read failed"):
        _discover(discovery)

    expected_order = {
        "marker": ["marker"],
        "user": ["marker", "user"],
        "projection": ["marker", "user", "projection"],
    }
    assert [call[0] for call in provisioning.calls] == expected_order[stage]
    assert cognito.calls == []


@pytest.mark.parametrize(
    ("status", "expected_discovery_status"),
    [
        ("INVITED", "INVITED_CONSISTENT"),
        ("ACTIVE", "ACTIVE_CONSISTENT"),
    ],
)
def test_consistent_first_admin_is_classified_with_authoritative_target(
    status: str,
    expected_discovery_status: str,
) -> None:
    provisioning = FakeProvisioningReader(
        user_profile=_user_profile(status=status),
        cognito_projection=_cognito_projection(status=status),
    )
    discovery, provisioning, cognito = _discovery(provisioning)

    result = _discover(discovery)

    assert result.status == expected_discovery_status
    assert result.target == FirstAdminInvitationTarget(
        user_id=_USER_ID,
        email="admin@example.com",
        cognito_sub=_COGNITO_SUB,
        status=status,  # type: ignore[arg-type]
    )
    assert provisioning.calls == [
        ("marker", "users-table"),
        ("user", ("users-table", _USER_ID)),
        ("projection", ("users-table", _COGNITO_SUB)),
    ]
    assert cognito.calls == [
        {
            "user_pool_id": "pool-123",
            "user_id": _USER_ID,
            "expected_email": "admin@example.com",
        }
    ]


def test_discovery_has_no_writes_or_unrequired_reads() -> None:
    discovery, provisioning, cognito = _discovery()

    result = _discover(discovery)

    assert result.status == "INVITED_CONSISTENT"
    assert provisioning.forbidden_calls == []
    assert cognito.forbidden_calls == []
