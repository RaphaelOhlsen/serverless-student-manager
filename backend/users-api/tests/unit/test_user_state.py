from typing import Any

import pytest
from users_api.services.user_state import (
    UserStateReconciliationError,
    reconcile_user_state,
)

SUB = "sub-1"
USER_ID = "user-1"


class FakeUsers:
    def __init__(self) -> None:
        self.authorization: dict[str, object] | None = {
            "userId": USER_ID,
            "role": "ADMIN",
            "status": "INVITED",
            "authVersion": 1,
        }
        self.profile: dict[str, object] | None = {
            "userId": USER_ID,
            "cognitoSub": SUB,
            "role": "ADMIN",
            "status": "INVITED",
            "authVersion": 1,
            "fullName": "User One",
            "email": "user@example.test",
        }
        self.calls: list[tuple[str, str]] = []

    def get_authorization(self, cognito_sub: str) -> dict[str, object] | None:
        self.calls.append(("authorization", cognito_sub))
        return self.authorization

    def get_profile(self, user_id: str) -> dict[str, object] | None:
        self.calls.append(("profile", user_id))
        return self.profile


def test_reconciles_authorization_and_profile_in_order() -> None:
    users = FakeUsers()

    state = reconcile_user_state(users, SUB)

    assert state.user_id == USER_ID
    assert state.cognito_sub == SUB
    assert state.role == "ADMIN"
    assert state.status == "INVITED"
    assert state.auth_version == 1
    assert state.profile is users.profile
    assert users.calls == [("authorization", SUB), ("profile", USER_ID)]


@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("profile", "userId", "other-user"),
        ("profile", "cognitoSub", "other-sub"),
        ("profile", "role", "OPERATOR"),
        ("profile", "status", "ACTIVE"),
        ("profile", "authVersion", 2),
        ("authorization", "userId", "other-user"),
    ],
)
def test_rejects_structural_divergence(target: str, field: str, value: Any) -> None:
    users = FakeUsers()
    item = users.authorization if target == "authorization" else users.profile
    assert item is not None
    item[field] = value

    with pytest.raises(UserStateReconciliationError):
        reconcile_user_state(users, SUB)


@pytest.mark.parametrize("missing", ["authorization", "profile"])
def test_rejects_missing_items(missing: str) -> None:
    users = FakeUsers()
    setattr(users, missing, None)

    with pytest.raises(UserStateReconciliationError):
        reconcile_user_state(users, SUB)
