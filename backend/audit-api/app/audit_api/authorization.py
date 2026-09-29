from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, TypeGuard

from audit_api.errors import AuditForbiddenError


class UsersTableProtocol(Protocol):
    def get_item(self, **kwargs: object) -> dict[str, object]: ...


@dataclass(frozen=True)
class AuthorizedActor:
    user_id: str


class AdminAuthorizationService:
    def __init__(self, users_table: UsersTableProtocol) -> None:
        self._users_table = users_table

    def authorize(self, cognito_sub: str) -> AuthorizedActor:
        if not _required_string(cognito_sub):
            raise AuditForbiddenError

        authorization = self._consistent_get(
            {"PK": f"COGNITO#{cognito_sub}", "SK": "AUTHORIZATION"}
        )
        if authorization is None:
            raise AuditForbiddenError

        user_id = _item_string(authorization, "userId")
        role = _item_string(authorization, "role")
        status = _item_string(authorization, "status")
        auth_version = _item_positive_int(authorization, "authVersion")
        if (
            authorization.get("PK") != f"COGNITO#{cognito_sub}"
            or authorization.get("SK") != "AUTHORIZATION"
            or role != "ADMIN"
            or status != "ACTIVE"
        ):
            raise AuditForbiddenError

        profile = self._consistent_get({"PK": f"USER#{user_id}", "SK": "PROFILE"})
        if profile is None:
            raise AuditForbiddenError
        if (
            profile.get("PK") != f"USER#{user_id}"
            or profile.get("SK") != "PROFILE"
            or _item_string(profile, "userId") != user_id
            or _item_string(profile, "cognitoSub") != cognito_sub
            or _item_string(profile, "role") != role
            or _item_string(profile, "status") != status
            or _item_positive_int(profile, "authVersion") != auth_version
        ):
            raise AuditForbiddenError
        return AuthorizedActor(user_id=user_id)

    def _consistent_get(self, key: dict[str, str]) -> dict[str, object] | None:
        response = self._users_table.get_item(Key=key, ConsistentRead=True)
        item = response.get("Item")
        if item is None:
            return None
        if not isinstance(item, dict) or not all(isinstance(name, str) for name in item):
            raise AuditForbiddenError
        return item


def _required_string(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _item_string(item: dict[str, object], name: str) -> str:
    value = item.get(name)
    if not _required_string(value):
        raise AuditForbiddenError
    return value


def _item_positive_int(item: dict[str, object], name: str) -> int:
    value = item.get(name)
    if isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise AuditForbiddenError
        value = int(value)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise AuditForbiddenError
    return value
