from decimal import Decimal
from typing import Any

import pytest
from students_api.authorization import AuthorizationService
from students_api.errors import ForbiddenError
from students_api.repositories.dynamodb_values import normalize_dynamodb_value


class FakeUsersTable:
    def __init__(self, item: dict[str, Any] | None) -> None:
        self.item = item
        self.call: dict[str, Any] | None = None

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        self.call = kwargs
        return {"Item": self.item} if self.item is not None else {}


@pytest.mark.parametrize("role", ["ADMIN", "OPERATOR"])
def test_active_allowed_roles_are_authorized(role: str) -> None:
    table = FakeUsersTable({"status": "ACTIVE", "role": role})

    AuthorizationService(table).authorize_list_students("subject-123")

    assert table.call == {
        "Key": {"PK": "COGNITO#subject-123", "SK": "AUTHORIZATION"},
        "ConsistentRead": True,
    }


@pytest.mark.parametrize(
    "subject,item",
    [
        (None, None),
        ("subject-123", None),
        ("subject-123", {"status": "INACTIVE", "role": "ADMIN"}),
        ("subject-123", {"status": "ACTIVE", "role": "VIEWER"}),
    ],
)
def test_missing_or_disallowed_authorization_is_forbidden(
    subject: str | None, item: dict[str, Any] | None
) -> None:
    with pytest.raises(ForbiddenError):
        AuthorizationService(FakeUsersTable(item)).authorize_list_students(subject)


@pytest.mark.parametrize("role", ["ADMIN", "OPERATOR"])
@pytest.mark.parametrize("auth_version", [1, Decimal("1"), Decimal("2")])
def test_active_allowed_roles_can_create_student(role: str, auth_version: object) -> None:
    table = FakeUsersTable(
        {
            "PK": "COGNITO#subject-123",
            "SK": "AUTHORIZATION",
            "userId": "user-1",
            "status": "ACTIVE",
            "role": role,
            "authVersion": auth_version,
        }
    )

    actor_id = AuthorizationService(table).authorize_create_student("subject-123")

    assert actor_id == "user-1"
    assert table.call == {
        "Key": {"PK": "COGNITO#subject-123", "SK": "AUTHORIZATION"},
        "ConsistentRead": True,
    }


@pytest.mark.parametrize("role", ["ADMIN", "OPERATOR"])
def test_active_allowed_roles_can_update_student(role: str) -> None:
    table = FakeUsersTable(
        {
            "PK": "COGNITO#subject-123",
            "SK": "AUTHORIZATION",
            "userId": "user-1",
            "status": "ACTIVE",
            "role": role,
            "authVersion": 1,
        }
    )

    assert AuthorizationService(table).authorize_update_student("subject-123") == "user-1"


def test_other_role_cannot_update_student() -> None:
    table = FakeUsersTable(
        {
            "PK": "COGNITO#subject-123",
            "SK": "AUTHORIZATION",
            "userId": "user-1",
            "status": "ACTIVE",
            "role": "VIEWER",
            "authVersion": 1,
        }
    )

    with pytest.raises(ForbiddenError):
        AuthorizationService(table).authorize_update_student("subject-123")


def test_active_admin_can_manage_student_lifecycle() -> None:
    table = FakeUsersTable(
        {
            "PK": "COGNITO#subject-123",
            "SK": "AUTHORIZATION",
            "userId": "user-1",
            "status": "ACTIVE",
            "role": "ADMIN",
            "authVersion": 1,
        }
    )

    assert AuthorizationService(table).authorize_student_lifecycle("subject-123") == "user-1"


@pytest.mark.parametrize(
    ("role", "status"),
    [("OPERATOR", "ACTIVE"), ("VIEWER", "ACTIVE"), ("ADMIN", "INACTIVE")],
)
def test_non_admin_or_inactive_user_cannot_manage_student_lifecycle(role: str, status: str) -> None:
    table = FakeUsersTable(
        {
            "PK": "COGNITO#subject-123",
            "SK": "AUTHORIZATION",
            "userId": "user-1",
            "status": status,
            "role": role,
            "authVersion": 1,
        }
    )

    with pytest.raises(ForbiddenError):
        AuthorizationService(table).authorize_student_lifecycle("subject-123")


def test_integral_dynamodb_number_preserves_integer_value() -> None:
    normalized = normalize_dynamodb_value(Decimal("2"))

    assert type(normalized) is int
    assert normalized == 2


@pytest.mark.parametrize(
    "auth_version",
    [
        Decimal("1.5"),
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        Decimal("0"),
        Decimal("-1"),
        0,
        -1,
        "1",
        True,
        False,
        None,
        1.0,
        [],
        {},
    ],
)
def test_create_student_rejects_invalid_auth_version(auth_version: object) -> None:
    item = {
        "PK": "COGNITO#subject-123",
        "SK": "AUTHORIZATION",
        "userId": "user-1",
        "status": "ACTIVE",
        "role": "ADMIN",
        "authVersion": auth_version,
    }
    if auth_version is None:
        del item["authVersion"]

    with pytest.raises(ForbiddenError):
        AuthorizationService(FakeUsersTable(item)).authorize_create_student("subject-123")


@pytest.mark.parametrize(
    "subject,item",
    [
        (None, None),
        ("subject-123", None),
        (
            "subject-123",
            {
                "PK": "COGNITO#subject-123",
                "SK": "AUTHORIZATION",
                "userId": "user-1",
                "status": "INVITED",
                "role": "ADMIN",
                "authVersion": 1,
            },
        ),
        (
            "subject-123",
            {
                "PK": "COGNITO#subject-123",
                "SK": "AUTHORIZATION",
                "userId": "user-1",
                "status": "INACTIVE",
                "role": "OPERATOR",
                "authVersion": 1,
            },
        ),
        (
            "subject-123",
            {
                "PK": "COGNITO#subject-123",
                "SK": "AUTHORIZATION",
                "userId": "user-1",
                "status": "ACTIVE",
                "role": "VIEWER",
                "authVersion": 1,
            },
        ),
        (
            "subject-123",
            {
                "PK": "COGNITO#other",
                "SK": "AUTHORIZATION",
                "userId": "user-1",
                "status": "ACTIVE",
                "role": "ADMIN",
                "authVersion": 1,
            },
        ),
        (
            "subject-123",
            {
                "PK": "COGNITO#subject-123",
                "SK": "OTHER",
                "userId": "user-1",
                "status": "ACTIVE",
                "role": "ADMIN",
                "authVersion": 1,
            },
        ),
        (
            "subject-123",
            {
                "PK": "COGNITO#subject-123",
                "SK": "AUTHORIZATION",
                "userId": "user-1",
                "status": "ACTIVE",
                "role": "ADMIN",
                "authVersion": "1",
            },
        ),
        (
            "subject-123",
            {
                "PK": "COGNITO#subject-123",
                "SK": "AUTHORIZATION",
                "status": "ACTIVE",
                "role": "ADMIN",
                "authVersion": 1,
            },
        ),
    ],
)
def test_create_student_fails_closed_for_invalid_authorization(
    subject: str | None, item: dict[str, Any] | None
) -> None:
    with pytest.raises(ForbiddenError):
        AuthorizationService(FakeUsersTable(item)).authorize_create_student(subject)
