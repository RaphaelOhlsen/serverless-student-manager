from typing import Protocol

from users_api.cursor import (
    UserCursorPosition,
    decode_cursor,
    encode_cursor,
    normalize_email,
    normalize_name,
)
from users_api.errors import (
    AdminUserDataInvariantError,
    AdminUserForbiddenError,
    AdminUserNotFoundError,
    InvalidAdminUserListRequestError,
)
from users_api.repositories.dynamodb_values import normalize_dynamodb_value
from users_api.repositories.user_repository import UserPage
from users_api.services.user_state import UserStateReconciliationError, reconcile_user_state


class AdminUserRepositoryProtocol(Protocol):
    def get_authorization(self, cognito_sub: str) -> dict[str, object] | None: ...

    def get_profile(self, user_id: str) -> dict[str, object] | None: ...

    def get_email_reservation(self, normalized_email: str) -> dict[str, object] | None: ...

    def list_profiles(
        self,
        *,
        name_prefix: str | None,
        limit: int,
        position: UserCursorPosition | None,
    ) -> UserPage: ...


class AdminUserService:
    def __init__(self, users: AdminUserRepositoryProtocol) -> None:
        self._users = users

    def get_user(self, *, cognito_sub: str, user_id: str) -> dict[str, object]:
        self._authorize_admin(cognito_sub)
        profile = self._users.get_profile(user_id)
        if profile is None:
            raise AdminUserNotFoundError
        return self._public_user(profile, expected_user_id=user_id)

    def list_users(
        self,
        *,
        cognito_sub: str,
        limit: int,
        role: str,
        status: str,
        name_prefix: str | None,
        email: str | None,
        cursor: str | None,
    ) -> dict[str, object]:
        self._authorize_admin(cognito_sub)
        if not 1 <= limit <= 100:
            raise InvalidAdminUserListRequestError
        if role not in {"ADMIN", "OPERATOR", "ALL"}:
            raise InvalidAdminUserListRequestError
        if status not in {"INVITED", "ACTIVE", "INACTIVE", "ALL"}:
            raise InvalidAdminUserListRequestError
        if name_prefix is not None and email is not None:
            raise InvalidAdminUserListRequestError

        normalized_prefix = self._normalize_prefix(name_prefix)
        normalized_email = normalize_email(email) if email is not None else None
        if normalized_email is not None:
            if cursor is not None:
                raise InvalidAdminUserListRequestError
            email_items = self._find_by_email(normalized_email, role=role, status=status)
            return {"items": email_items, "nextCursor": None}

        position = (
            decode_cursor(
                cursor,
                role=role,
                status=status,
                name_prefix=normalized_prefix,
            )
            if cursor is not None
            else None
        )
        items: list[dict[str, object]] = []
        while len(items) < limit:
            page = self._users.list_profiles(
                name_prefix=normalized_prefix,
                limit=limit - len(items),
                position=position,
            )
            for profile in page.items:
                public = self._public_user(profile)
                if self._matches(public, role=role, status=status):
                    items.append(public)
            if page.next_position is None:
                position = None
                break
            if page.next_position == position:
                raise AdminUserDataInvariantError
            position = page.next_position

        next_cursor = (
            encode_cursor(
                role=role,
                status=status,
                name_prefix=normalized_prefix,
                position=position,
            )
            if position is not None
            else None
        )
        return {"items": items, "nextCursor": next_cursor}

    def _authorize_admin(self, cognito_sub: str) -> None:
        try:
            reconcile_user_state(self._users, cognito_sub, self._validate_admin)
        except UserStateReconciliationError:
            raise AdminUserForbiddenError from None

    @staticmethod
    def _validate_admin(role: str, status: str, auth_version: int) -> None:
        del auth_version
        if role != "ADMIN" or status != "ACTIVE":
            raise AdminUserForbiddenError

    @staticmethod
    def _normalize_prefix(value: str | None) -> str | None:
        if value is None:
            return None
        if not 1 <= len(value) <= 150:
            raise InvalidAdminUserListRequestError
        normalized = normalize_name(value)
        if not normalized:
            raise InvalidAdminUserListRequestError
        return normalized

    def _find_by_email(
        self, normalized_email: str, *, role: str, status: str
    ) -> list[dict[str, object]]:
        reservation = self._users.get_email_reservation(normalized_email)
        if reservation is None:
            return []
        user_id = reservation.get("userId")
        if (
            reservation.get("PK") != f"UNIQUE#EMAIL#{normalized_email}"
            or reservation.get("SK") != "UNIQUE"
            or not isinstance(user_id, str)
            or not user_id
        ):
            raise AdminUserDataInvariantError
        profile = self._users.get_profile(user_id)
        if profile is None:
            raise AdminUserDataInvariantError
        public = self._public_user(profile, expected_user_id=user_id)
        if public["email"] != normalized_email:
            raise AdminUserDataInvariantError
        return [public] if self._matches(public, role=role, status=status) else []

    @staticmethod
    def _matches(user: dict[str, object], *, role: str, status: str) -> bool:
        return (role == "ALL" or user["role"] == role) and (
            status == "ALL" or user["status"] == status
        )

    @staticmethod
    def _public_user(
        profile: dict[str, object], *, expected_user_id: str | None = None
    ) -> dict[str, object]:
        user_id = AdminUserService._required_string(profile, "userId")
        if (
            expected_user_id is not None
            and user_id != expected_user_id
            or profile.get("PK") != f"USER#{user_id}"
            or profile.get("SK") != "PROFILE"
        ):
            raise AdminUserDataInvariantError
        role = AdminUserService._required_string(profile, "role")
        status = AdminUserService._required_string(profile, "status")
        if role not in {"ADMIN", "OPERATOR"} or status not in {
            "INVITED",
            "ACTIVE",
            "INACTIVE",
        }:
            raise AdminUserDataInvariantError
        stored_version = normalize_dynamodb_value(profile.get("version", 1))
        if type(stored_version) is not int or stored_version < 1:
            raise AdminUserDataInvariantError
        return {
            "userId": user_id,
            "fullName": AdminUserService._required_string(profile, "fullName"),
            "email": AdminUserService._required_string(profile, "email"),
            "role": role,
            "status": status,
            "version": stored_version,
            "createdAt": AdminUserService._required_string(profile, "createdAt"),
            "updatedAt": AdminUserService._required_string(profile, "updatedAt"),
        }

    @staticmethod
    def _required_string(profile: dict[str, object], name: str) -> str:
        value = profile.get(name)
        if not isinstance(value, str) or not value:
            raise AdminUserDataInvariantError
        return value
