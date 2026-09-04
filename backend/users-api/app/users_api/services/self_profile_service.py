from users_api.errors import SelfProfileForbiddenError
from users_api.services.user_state import (
    UserStateReconciliationError,
    UserStateRepositoryProtocol,
    reconcile_user_state,
)


class SelfProfileService:
    def __init__(self, users: UserStateRepositoryProtocol) -> None:
        self._users = users

    def get_current_user(self, *, cognito_sub: str) -> dict[str, object]:
        try:
            state = reconcile_user_state(
                self._users,
                cognito_sub,
                self._validate_authorization,
            )
        except UserStateReconciliationError:
            raise SelfProfileForbiddenError from None

        full_name = self._required_string(state.profile, "fullName")
        email = self._required_string(state.profile, "email")

        return {
            "userId": state.user_id,
            "fullName": full_name,
            "email": email,
            "role": state.role,
            "status": state.status,
            "authVersion": state.auth_version,
        }

    @staticmethod
    def _required_string(item: dict[str, object], name: str) -> str:
        value = item.get(name)
        if not isinstance(value, str) or not value:
            raise SelfProfileForbiddenError
        return value

    @staticmethod
    def _validate_authorization(role: str, status: str, auth_version: int) -> None:
        if role not in {"ADMIN", "OPERATOR"}:
            raise SelfProfileForbiddenError
        if status not in {"INVITED", "ACTIVE"}:
            raise SelfProfileForbiddenError
