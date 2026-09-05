from typing import Any, Protocol

from students_api.errors import ForbiddenError


class UsersTable(Protocol):
    def get_item(
        self,
        *,
        Key: dict[str, str],
        ConsistentRead: bool,
    ) -> dict[str, Any]: ...


class AuthorizationService:
    def __init__(self, users_table: UsersTable) -> None:
        self._users_table = users_table

    def authorize_list_students(self, cognito_sub: str | None) -> None:
        if not cognito_sub:
            raise ForbiddenError

        response = self._users_table.get_item(
            Key={"PK": f"COGNITO#{cognito_sub}", "SK": "AUTHORIZATION"},
            ConsistentRead=True,
        )
        authorization = response.get("Item")

        if not isinstance(authorization, dict):
            raise ForbiddenError
        if authorization.get("status") != "ACTIVE":
            raise ForbiddenError
        if authorization.get("role") not in {"ADMIN", "OPERATOR"}:
            raise ForbiddenError

    def authorize_create_student(self, cognito_sub: str | None) -> str:
        if not cognito_sub:
            raise ForbiddenError

        response = self._users_table.get_item(
            Key={"PK": f"COGNITO#{cognito_sub}", "SK": "AUTHORIZATION"},
            ConsistentRead=True,
        )
        authorization = response.get("Item")

        if not isinstance(authorization, dict):
            raise ForbiddenError
        if authorization.get("PK") != f"COGNITO#{cognito_sub}":
            raise ForbiddenError
        if authorization.get("SK") != "AUTHORIZATION":
            raise ForbiddenError
        if authorization.get("status") != "ACTIVE":
            raise ForbiddenError
        if authorization.get("role") not in {"ADMIN", "OPERATOR"}:
            raise ForbiddenError
        auth_version = authorization.get("authVersion")
        if not isinstance(auth_version, int) or isinstance(auth_version, bool) or auth_version < 1:
            raise ForbiddenError
        user_id = authorization.get("userId")
        if not isinstance(user_id, str) or not user_id:
            raise ForbiddenError
        return user_id
