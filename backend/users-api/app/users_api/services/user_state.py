from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


class UserStateRepositoryProtocol(Protocol):
    def get_authorization(self, cognito_sub: str) -> dict[str, object] | None: ...

    def get_profile(self, user_id: str) -> dict[str, object] | None: ...


class UserStateReconciliationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReconciledUserState:
    user_id: str
    cognito_sub: str
    role: str
    status: str
    auth_version: int
    profile: dict[str, object]


def reconcile_user_state(
    users: UserStateRepositoryProtocol,
    cognito_sub: str,
    authorization_validator: Callable[[str, str, int], None] | None = None,
) -> ReconciledUserState:
    authorization = users.get_authorization(cognito_sub)
    if authorization is None:
        raise UserStateReconciliationError

    user_id = _required_string(authorization, "userId")
    role = _required_string(authorization, "role")
    status = _required_string(authorization, "status")
    auth_version = _required_int(authorization, "authVersion")

    profile = users.get_profile(user_id)
    if profile is None:
        raise UserStateReconciliationError

    if authorization_validator is not None:
        authorization_validator(role, status, auth_version)

    if (
        _required_string(profile, "userId") != user_id
        or _required_string(profile, "cognitoSub") != cognito_sub
        or _required_string(profile, "role") != role
        or _required_string(profile, "status") != status
        or _required_int(profile, "authVersion") != auth_version
    ):
        raise UserStateReconciliationError

    return ReconciledUserState(
        user_id=user_id,
        cognito_sub=cognito_sub,
        role=role,
        status=status,
        auth_version=auth_version,
        profile=profile,
    )


def _required_string(item: dict[str, object], name: str) -> str:
    value = item.get(name)
    if not isinstance(value, str) or not value:
        raise UserStateReconciliationError
    return value


def _required_int(item: dict[str, object], name: str) -> int:
    value = item.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise UserStateReconciliationError
    return value
