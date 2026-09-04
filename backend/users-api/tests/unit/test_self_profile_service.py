from typing import Any

import pytest
from users_api.errors import SelfProfileForbiddenError
from users_api.services.self_profile_service import SelfProfileService

SUB = "sub-1"
USER_ID = "user-1"


class FakeUsers:
    def __init__(self, *, role: str = "ADMIN", status: str = "INVITED") -> None:
        self.authorization: dict[str, object] | None = {
            "userId": USER_ID,
            "role": role,
            "status": status,
            "authVersion": 1,
        }
        self.profile: dict[str, object] | None = {
            "userId": USER_ID,
            "cognitoSub": SUB,
            "fullName": "User One",
            "email": "user@example.test",
            "role": role,
            "status": status,
            "authVersion": 1,
        }

    def get_authorization(self, cognito_sub: str) -> dict[str, object] | None:
        assert cognito_sub == SUB
        return self.authorization

    def get_profile(self, user_id: str) -> dict[str, object] | None:
        assert user_id == USER_ID
        return self.profile


@pytest.mark.parametrize("status", ["INVITED", "ACTIVE"])
def test_returns_exact_public_contract_for_allowed_status(status: str) -> None:
    result = SelfProfileService(FakeUsers(status=status)).get_current_user(cognito_sub=SUB)

    assert result == {
        "userId": USER_ID,
        "fullName": "User One",
        "email": "user@example.test",
        "role": "ADMIN",
        "status": status,
        "authVersion": 1,
    }
    assert type(result["authVersion"]) is int


@pytest.mark.parametrize(
    ("role", "status"),
    [("VIEWER", "ACTIVE"), ("ADMIN", "INACTIVE")],
)
def test_forbids_disallowed_role_or_status(role: str, status: str) -> None:
    with pytest.raises(SelfProfileForbiddenError):
        SelfProfileService(FakeUsers(role=role, status=status)).get_current_user(cognito_sub=SUB)


@pytest.mark.parametrize("missing", ["authorization", "profile"])
def test_forbids_missing_application_identity(missing: str) -> None:
    users = FakeUsers()
    setattr(users, missing, None)

    with pytest.raises(SelfProfileForbiddenError):
        SelfProfileService(users).get_current_user(cognito_sub=SUB)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("userId", "other-user"),
        ("cognitoSub", "other-sub"),
        ("role", "OPERATOR"),
        ("status", "ACTIVE"),
        ("authVersion", 2),
    ],
)
def test_forbids_inconsistent_profile(field: str, value: Any) -> None:
    users = FakeUsers()
    assert users.profile is not None
    users.profile[field] = value

    with pytest.raises(SelfProfileForbiddenError):
        SelfProfileService(users).get_current_user(cognito_sub=SUB)


@pytest.mark.parametrize(
    ("field", "value"),
    [("fullName", ""), ("fullName", None), ("email", ""), ("email", None)],
)
def test_forbids_invalid_public_profile_fields(field: str, value: object) -> None:
    users = FakeUsers()
    assert users.profile is not None
    users.profile[field] = value

    with pytest.raises(SelfProfileForbiddenError):
        SelfProfileService(users).get_current_user(cognito_sub=SUB)
