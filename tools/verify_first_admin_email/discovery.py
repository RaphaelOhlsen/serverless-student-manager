from dataclasses import dataclass
from typing import Literal, Protocol, cast

from tools.bootstrap_admin.aws_errors import get_aws_error_code
from tools.bootstrap_admin.cognito_repository import (
    CognitoIdentityValidationError,
    ReconciledCognitoIdentity,
)
from tools.bootstrap_admin.ids import validate_uuid4

VerifyFirstAdminEmailDiscoveryStatus = Literal[
    "NEEDS_VERIFICATION",
    "ALREADY_VERIFIED",
    "RECONCILIATION_REQUIRED",
]
FirstAdminStatus = Literal["INVITED", "ACTIVE"]

_COMPATIBLE_STATUSES = frozenset({"INVITED", "ACTIVE"})


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
    def get_reconciled_user_identity(
        self,
        *,
        user_pool_id: str,
        user_id: str,
        expected_email: str,
        expected_sub: str,
    ) -> ReconciledCognitoIdentity: ...


@dataclass(frozen=True)
class VerifyFirstAdminEmailDiscoveryConfig:
    users_table_name: str
    user_pool_id: str

    def __post_init__(self) -> None:
        if self.users_table_name == "":
            raise ValueError("users_table_name must be a non-empty string")
        if self.user_pool_id == "":
            raise ValueError("user_pool_id must be a non-empty string")


@dataclass(frozen=True)
class FirstAdminEmailTarget:
    user_id: str
    email: str
    cognito_sub: str


@dataclass(frozen=True)
class VerifyFirstAdminEmailDiscoveryResult:
    status: VerifyFirstAdminEmailDiscoveryStatus
    target: FirstAdminEmailTarget | None
    authoritative_user_id: str | None

    def __post_init__(self) -> None:
        if self.status == "RECONCILIATION_REQUIRED":
            if self.target is not None:
                raise ValueError("reconciliation discovery must not include a target")
        elif self.target is None:
            raise ValueError("consistent discovery requires a target")
        elif self.authoritative_user_id != self.target.user_id:
            raise ValueError("consistent discovery requires the authoritative target user_id")

        if self.authoritative_user_id is not None:
            validate_uuid4(self.authoritative_user_id)


class VerifyFirstAdminEmailDiscovery:
    def __init__(
        self,
        *,
        config: VerifyFirstAdminEmailDiscoveryConfig,
        provisioning_reader: ProvisioningReader,
        cognito_reader: CognitoReader,
    ) -> None:
        self._config = config
        self._provisioning_reader = provisioning_reader
        self._cognito_reader = cognito_reader

    def discover(self) -> VerifyFirstAdminEmailDiscoveryResult:
        marker = self._provisioning_reader.get_bootstrap_marker(
            users_table_name=self._config.users_table_name,
        )
        user_id = _parse_marker(marker)
        if user_id is None:
            return _reconciliation_required()

        user_profile = self._provisioning_reader.get_user_profile(
            users_table_name=self._config.users_table_name,
            user_id=user_id,
        )
        user_identity = _parse_user_profile(
            user_profile,
            expected_user_id=user_id,
        )
        if user_identity is None:
            return _reconciliation_required()

        email, cognito_sub, status, auth_version = user_identity
        projection = self._provisioning_reader.get_cognito_projection(
            users_table_name=self._config.users_table_name,
            cognito_sub=cognito_sub,
        )
        if not _is_valid_projection(
            projection,
            expected_user_id=user_id,
            expected_cognito_sub=cognito_sub,
            expected_status=status,
            expected_auth_version=auth_version,
        ):
            return _reconciliation_required(authoritative_user_id=user_id)

        try:
            identity = self._cognito_reader.get_reconciled_user_identity(
                user_pool_id=self._config.user_pool_id,
                user_id=user_id,
                expected_email=email,
                expected_sub=cognito_sub,
            )
        except CognitoIdentityValidationError:
            return _reconciliation_required(authoritative_user_id=user_id)
        except Exception as error:
            if get_aws_error_code(error) == "UserNotFoundException":
                return _reconciliation_required(authoritative_user_id=user_id)
            raise

        if identity.cognito_sub != cognito_sub:
            return _reconciliation_required(authoritative_user_id=user_id)

        target = FirstAdminEmailTarget(
            user_id=user_id,
            email=email,
            cognito_sub=cognito_sub,
        )
        status_result: VerifyFirstAdminEmailDiscoveryStatus = (
            "ALREADY_VERIFIED" if identity.verified else "NEEDS_VERIFICATION"
        )
        return VerifyFirstAdminEmailDiscoveryResult(
            status=status_result,
            target=target,
            authoritative_user_id=user_id,
        )


def _parse_marker(marker: dict[str, object] | None) -> str | None:
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
    return user_id


def _parse_user_profile(
    profile: dict[str, object] | None,
    *,
    expected_user_id: str,
) -> tuple[str, str, FirstAdminStatus, int] | None:
    if profile is None:
        return None
    if profile.get("PK") != f"USER#{expected_user_id}":
        return None
    if profile.get("SK") != "PROFILE":
        return None
    if profile.get("userId") not in {None, expected_user_id}:
        return None
    if profile.get("role") != "ADMIN":
        return None

    status = profile.get("status")
    email = _nonempty_string(profile.get("email"))
    cognito_sub = _nonempty_string(profile.get("cognitoSub"))
    auth_version = profile.get("authVersion")
    if not isinstance(status, str) or status not in _COMPATIBLE_STATUSES:
        return None
    if email is None or cognito_sub is None or type(auth_version) is not int:
        return None

    return email, cognito_sub, cast(FirstAdminStatus, status), auth_version


def _is_valid_projection(
    projection: dict[str, object] | None,
    *,
    expected_user_id: str,
    expected_cognito_sub: str,
    expected_status: FirstAdminStatus,
    expected_auth_version: int,
) -> bool:
    if projection is None:
        return False
    return (
        projection.get("PK") == f"COGNITO#{expected_cognito_sub}"
        and projection.get("SK") == "AUTHORIZATION"
        and projection.get("userId") == expected_user_id
        and projection.get("role") == "ADMIN"
        and projection.get("status") == expected_status
        and type(projection.get("authVersion")) is int
        and projection.get("authVersion") == expected_auth_version
    )


def _nonempty_string(value: object) -> str | None:
    return value if isinstance(value, str) and value != "" else None


def _reconciliation_required(
    *,
    authoritative_user_id: str | None = None,
) -> VerifyFirstAdminEmailDiscoveryResult:
    return VerifyFirstAdminEmailDiscoveryResult(
        status="RECONCILIATION_REQUIRED",
        target=None,
        authoritative_user_id=authoritative_user_id,
    )
