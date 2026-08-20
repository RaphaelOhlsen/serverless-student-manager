from dataclasses import dataclass
from typing import Literal, Protocol, cast

from tools.bootstrap_admin.aws_errors import get_aws_error_code
from tools.bootstrap_admin.cognito_repository import CognitoIdentityValidationError
from tools.bootstrap_admin.ids import validate_uuid4

FirstAdminStatus = Literal["INVITED", "ACTIVE"]
ResumeDiscoveryStatus = Literal[
    "INVITED_CONSISTENT",
    "ACTIVE_CONSISTENT",
    "RECONCILIATION_REQUIRED",
]

_FIRST_ADMIN_STATUSES = frozenset({"INVITED", "ACTIVE"})


class ProvisioningReader(Protocol):
    def get_bootstrap_marker(
        self,
        *,
        users_table_name: str,
    ) -> dict[str, object] | None: ...

    def get_user_profile(
        self,
        *,
        users_table_name: str,
        user_id: str,
    ) -> dict[str, object] | None: ...

    def get_cognito_projection(
        self,
        *,
        users_table_name: str,
        cognito_sub: str,
    ) -> dict[str, object] | None: ...


class CognitoReader(Protocol):
    def get_existing_user_sub(
        self,
        *,
        user_pool_id: str,
        user_id: str,
        expected_email: str,
    ) -> str: ...


@dataclass(frozen=True)
class ResumeInvitationDiscoveryConfig:
    users_table_name: str
    user_pool_id: str

    def __post_init__(self) -> None:
        if self.users_table_name == "":
            raise ValueError("users_table_name must be a non-empty string")
        if self.user_pool_id == "":
            raise ValueError("user_pool_id must be a non-empty string")


@dataclass(frozen=True)
class FirstAdminInvitationTarget:
    user_id: str
    email: str
    cognito_sub: str
    status: FirstAdminStatus


@dataclass(frozen=True)
class ResumeDiscoveryResult:
    status: ResumeDiscoveryStatus
    target: FirstAdminInvitationTarget | None

    def __post_init__(self) -> None:
        is_consistent = self.status in {
            "INVITED_CONSISTENT",
            "ACTIVE_CONSISTENT",
        }
        if is_consistent and self.target is None:
            raise ValueError("consistent discovery requires a target")
        if self.status == "RECONCILIATION_REQUIRED" and self.target is not None:
            raise ValueError("reconciliation discovery must not include a target")


class ResumeInvitationOperationIdConflictError(ValueError):
    pass


class ResumeInvitationDiscovery:
    def __init__(
        self,
        *,
        config: ResumeInvitationDiscoveryConfig,
        provisioning_reader: ProvisioningReader,
        cognito_reader: CognitoReader,
    ) -> None:
        self._config = config
        self._provisioning_reader = provisioning_reader
        self._cognito_reader = cognito_reader

    def discover(self, *, resume_operation_id: str) -> ResumeDiscoveryResult:
        validate_uuid4(resume_operation_id)

        marker = self._provisioning_reader.get_bootstrap_marker(
            users_table_name=self._config.users_table_name,
        )
        marker_identity = _parse_marker(marker)
        if marker_identity is None:
            return _reconciliation_required()

        user_id, bootstrap_operation_id = marker_identity
        if resume_operation_id == bootstrap_operation_id:
            raise ResumeInvitationOperationIdConflictError(
                "resume operationId must differ from bootstrap operationId"
            )

        user_profile = self._provisioning_reader.get_user_profile(
            users_table_name=self._config.users_table_name,
            user_id=user_id,
        )
        user_identity = _parse_user_profile(user_profile, expected_user_id=user_id)
        if user_identity is None:
            return _reconciliation_required()

        email, cognito_sub, status, auth_version = user_identity
        cognito_projection = self._provisioning_reader.get_cognito_projection(
            users_table_name=self._config.users_table_name,
            cognito_sub=cognito_sub,
        )
        if not _is_valid_cognito_projection(
            cognito_projection,
            expected_user_id=user_id,
            expected_cognito_sub=cognito_sub,
            expected_status=status,
            expected_auth_version=auth_version,
        ):
            return _reconciliation_required()

        try:
            existing_sub = self._cognito_reader.get_existing_user_sub(
                user_pool_id=self._config.user_pool_id,
                user_id=user_id,
                expected_email=email,
            )
        except CognitoIdentityValidationError:
            return _reconciliation_required()
        except Exception as error:
            if get_aws_error_code(error) == "UserNotFoundException":
                return _reconciliation_required()
            raise

        if existing_sub != cognito_sub:
            return _reconciliation_required()

        target = FirstAdminInvitationTarget(
            user_id=user_id,
            email=email,
            cognito_sub=cognito_sub,
            status=status,
        )
        discovery_status: ResumeDiscoveryStatus = (
            "ACTIVE_CONSISTENT" if status == "ACTIVE" else "INVITED_CONSISTENT"
        )
        return ResumeDiscoveryResult(status=discovery_status, target=target)


def _parse_marker(
    marker: dict[str, object] | None,
) -> tuple[str, str] | None:
    if marker is None:
        return None
    if marker.get("PK") != "CONTROL#FIRST_ADMIN_BOOTSTRAP":
        return None
    if marker.get("SK") != "CONTROL":
        return None

    user_id = _nonempty_string(marker.get("userId"))
    operation_id = _nonempty_string(marker.get("operationId"))
    created_at = _nonempty_string(marker.get("createdAt"))
    created_by = _nonempty_string(marker.get("createdBy"))
    if None in (user_id, operation_id, created_at, created_by):
        return None

    assert user_id is not None
    assert operation_id is not None
    try:
        validate_uuid4(user_id)
        validate_uuid4(operation_id)
    except ValueError:
        return None
    return user_id, operation_id


def _parse_user_profile(
    user_profile: dict[str, object] | None,
    *,
    expected_user_id: str,
) -> tuple[str, str, FirstAdminStatus, int] | None:
    if user_profile is None:
        return None
    if user_profile.get("PK") != f"USER#{expected_user_id}":
        return None
    if user_profile.get("SK") != "PROFILE":
        return None

    persisted_user_id = user_profile.get("userId")
    if persisted_user_id is not None and persisted_user_id != expected_user_id:
        return None
    if user_profile.get("role") != "ADMIN":
        return None

    status_value = user_profile.get("status")
    if not isinstance(status_value, str) or status_value not in _FIRST_ADMIN_STATUSES:
        return None
    email = _nonempty_string(user_profile.get("email"))
    cognito_sub = _nonempty_string(user_profile.get("cognitoSub"))
    auth_version = user_profile.get("authVersion")
    if email is None or cognito_sub is None or type(auth_version) is not int:
        return None

    return (
        email,
        cognito_sub,
        cast(FirstAdminStatus, status_value),
        auth_version,
    )


def _is_valid_cognito_projection(
    projection: dict[str, object] | None,
    *,
    expected_user_id: str,
    expected_cognito_sub: str,
    expected_status: FirstAdminStatus,
    expected_auth_version: int,
) -> bool:
    if projection is None:
        return False
    if projection.get("PK") != f"COGNITO#{expected_cognito_sub}":
        return False
    if projection.get("SK") != "AUTHORIZATION":
        return False
    if projection.get("userId") != expected_user_id:
        return False
    if projection.get("role") != "ADMIN":
        return False
    if projection.get("status") != expected_status:
        return False

    auth_version = projection.get("authVersion")
    return type(auth_version) is int and auth_version == expected_auth_version


def _nonempty_string(value: object) -> str | None:
    if not isinstance(value, str) or value == "":
        return None
    return value


def _reconciliation_required() -> ResumeDiscoveryResult:
    return ResumeDiscoveryResult(
        status="RECONCILIATION_REQUIRED",
        target=None,
    )
