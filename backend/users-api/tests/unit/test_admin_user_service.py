from decimal import Decimal
from typing import Any, cast

import pytest
from users_api.cursor import UserCursorPosition
from users_api.errors import (
    AdminUserDataInvariantError,
    AdminUserForbiddenError,
    AdminUserNotFoundError,
    InvalidAdminUserListRequestError,
)
from users_api.repositories.user_repository import UserPage
from users_api.services.admin_user_service import AdminUserService

ACTOR_SUB = "admin-sub"
ACTOR_ID = "admin-actor"


def profile(
    user_id: str,
    *,
    role: str = "OPERATOR",
    status: str = "ACTIVE",
    version: object = 2,
    name: str = "User One",
    email: str = "user@example.test",
) -> dict[str, object]:
    value: dict[str, object] = {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "userId": user_id,
        "cognitoSub": f"sub-{user_id}",
        "fullName": name,
        "normalizedName": name.casefold(),
        "email": email,
        "role": role,
        "status": status,
        "authVersion": 1,
        "createdAt": "2026-09-01T10:00:00.000Z",
        "updatedAt": "2026-09-02T10:00:00.000Z",
        "internal": "must-not-leak",
    }
    if version is not ...:
        value["version"] = version
    return value


class FakeRepository:
    def __init__(self, *, actor_role: str = "ADMIN", actor_status: str = "ACTIVE") -> None:
        self.actor_authorization: dict[str, object] = {
            "userId": ACTOR_ID,
            "role": actor_role,
            "status": actor_status,
            "authVersion": 1,
        }
        self.profiles: dict[str, dict[str, object]] = {
            ACTOR_ID: {
                **profile(ACTOR_ID, role=actor_role, status=actor_status),
                "cognitoSub": ACTOR_SUB,
            }
        }
        self.pages: list[UserPage] = []
        self.list_calls: list[dict[str, object]] = []
        self.reservations: dict[str, dict[str, object]] = {}

    def get_authorization(self, cognito_sub: str) -> dict[str, object] | None:
        return self.actor_authorization if cognito_sub == ACTOR_SUB else None

    def get_profile(self, user_id: str) -> dict[str, object] | None:
        return self.profiles.get(user_id)

    def get_email_reservation(self, normalized_email: str) -> dict[str, object] | None:
        return self.reservations.get(normalized_email)

    def list_profiles(self, **kwargs: Any) -> UserPage:
        self.list_calls.append(kwargs)
        return self.pages.pop(0)


def test_get_returns_exact_public_allowlist_and_integral_version() -> None:
    repository = FakeRepository()
    repository.profiles["target"] = profile("target", version=Decimal("3"))

    result = AdminUserService(repository).get_user(cognito_sub=ACTOR_SUB, user_id="target")

    assert result == {
        "userId": "target",
        "fullName": "User One",
        "email": "user@example.test",
        "role": "OPERATOR",
        "status": "ACTIVE",
        "version": 3,
        "createdAt": "2026-09-01T10:00:00.000Z",
        "updatedAt": "2026-09-02T10:00:00.000Z",
    }
    assert type(result["version"]) is int
    internal_fields = {"PK", "SK", "cognitoSub", "authVersion", "normalizedName", "internal"}
    assert not internal_fields & result.keys()


def test_get_uses_logical_version_one_when_stored_version_is_absent() -> None:
    repository = FakeRepository()
    repository.profiles["legacy"] = profile("legacy", version=...)

    result = AdminUserService(repository).get_user(cognito_sub=ACTOR_SUB, user_id="legacy")

    assert result["version"] == 1


@pytest.mark.parametrize("invalid", [0, -1, True, "1", Decimal("1.5")])
def test_get_rejects_invalid_persisted_version(invalid: object) -> None:
    repository = FakeRepository()
    repository.profiles["target"] = profile("target", version=invalid)

    with pytest.raises(AdminUserDataInvariantError):
        AdminUserService(repository).get_user(cognito_sub=ACTOR_SUB, user_id="target")


def test_get_missing_user_is_not_found() -> None:
    with pytest.raises(AdminUserNotFoundError):
        AdminUserService(FakeRepository()).get_user(cognito_sub=ACTOR_SUB, user_id="missing")


@pytest.mark.parametrize(
    ("role", "status"),
    [("OPERATOR", "ACTIVE"), ("ADMIN", "INACTIVE")],
)
def test_get_and_list_require_active_admin(role: str, status: str) -> None:
    repository = FakeRepository(actor_role=role, actor_status=status)
    service = AdminUserService(repository)

    with pytest.raises(AdminUserForbiddenError):
        service.get_user(cognito_sub=ACTOR_SUB, user_id="target")
    with pytest.raises(AdminUserForbiddenError):
        service.list_users(
            cognito_sub=ACTOR_SUB,
            limit=20,
            role="ALL",
            status="ALL",
            name_prefix=None,
            email=None,
            cursor=None,
        )


def test_filtered_pagination_continues_across_empty_intermediate_pages() -> None:
    repository = FakeRepository()
    first = UserCursorPosition("u1", "alpha")
    second = UserCursorPosition("u2", "beta")
    repository.pages = [
        UserPage([profile("u1", role="OPERATOR")], first),
        UserPage([profile("u2", role="OPERATOR")], second),
        UserPage([profile("u3", role="ADMIN"), profile("u4", role="ADMIN")], None),
    ]

    result = AdminUserService(repository).list_users(
        cognito_sub=ACTOR_SUB,
        limit=2,
        role="ADMIN",
        status="ACTIVE",
        name_prefix=None,
        email=None,
        cursor=None,
    )

    items = cast(list[dict[str, object]], result["items"])
    assert [item["userId"] for item in items] == ["u3", "u4"]
    assert result["nextCursor"] is None
    assert len(repository.list_calls) == 3
    assert repository.list_calls[1]["position"] == first
    assert repository.list_calls[2]["position"] == second


def test_list_returns_cursor_for_really_consumed_position_and_normalizes_prefix() -> None:
    repository = FakeRepository()
    position = UserCursorPosition("u1", "ána silva")
    repository.pages = [UserPage([profile("u1", name="Ána Silva")], position)]

    result = AdminUserService(repository).list_users(
        cognito_sub=ACTOR_SUB,
        limit=1,
        role="ALL",
        status="ALL",
        name_prefix="  ÁNA  Silva ",
        email=None,
        cursor=None,
    )

    items = cast(list[dict[str, object]], result["items"])
    assert [item["userId"] for item in items] == ["u1"]
    assert isinstance(result["nextCursor"], str)
    assert repository.list_calls[0]["name_prefix"] == "ána silva"


def test_exact_email_search_uses_reservation_and_applies_filters() -> None:
    repository = FakeRepository()
    repository.reservations["target@example.test"] = {
        "PK": "UNIQUE#EMAIL#target@example.test",
        "SK": "UNIQUE",
        "userId": "target",
    }
    repository.profiles["target"] = profile(
        "target", role="ADMIN", status="INVITED", email="target@example.test"
    )
    service = AdminUserService(repository)

    found = service.list_users(
        cognito_sub=ACTOR_SUB,
        limit=20,
        role="ADMIN",
        status="INVITED",
        name_prefix=None,
        email=" TARGET@EXAMPLE.TEST ",
        cursor=None,
    )
    filtered = service.list_users(
        cognito_sub=ACTOR_SUB,
        limit=20,
        role="OPERATOR",
        status="ALL",
        name_prefix=None,
        email="target@example.test",
        cursor=None,
    )

    items = cast(list[dict[str, object]], found["items"])
    assert [item["userId"] for item in items] == ["target"]
    assert filtered == {"items": [], "nextCursor": None}


def test_email_not_found_is_an_empty_result() -> None:
    result = AdminUserService(FakeRepository()).list_users(
        cognito_sub=ACTOR_SUB,
        limit=20,
        role="ALL",
        status="ALL",
        name_prefix=None,
        email="missing@example.test",
        cursor=None,
    )
    assert result == {"items": [], "nextCursor": None}


def test_orphan_email_reservation_is_a_technical_invariant() -> None:
    repository = FakeRepository()
    repository.reservations["orphan@example.test"] = {
        "PK": "UNIQUE#EMAIL#orphan@example.test",
        "SK": "UNIQUE",
        "userId": "missing",
    }

    with pytest.raises(AdminUserDataInvariantError):
        AdminUserService(repository).list_users(
            cognito_sub=ACTOR_SUB,
            limit=20,
            role="ALL",
            status="ALL",
            name_prefix=None,
            email="orphan@example.test",
            cursor=None,
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 0},
        {"limit": 101},
        {"role": "admin"},
        {"status": "DISABLED"},
        {"name_prefix": "", "email": "a@example.test"},
        {"email": "a@example.test", "cursor": "invalid"},
    ],
)
def test_list_rejects_invalid_parameters(kwargs: dict[str, object]) -> None:
    parameters: dict[str, object] = {
        "cognito_sub": ACTOR_SUB,
        "limit": 20,
        "role": "ALL",
        "status": "ALL",
        "name_prefix": None,
        "email": None,
        "cursor": None,
    }
    parameters.update(kwargs)
    with pytest.raises(InvalidAdminUserListRequestError):
        AdminUserService(FakeRepository()).list_users(**parameters)  # type: ignore[arg-type]
