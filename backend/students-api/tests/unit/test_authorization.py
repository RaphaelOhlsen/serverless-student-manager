from typing import Any

import pytest
from students_api.authorization import AuthorizationService
from students_api.errors import ForbiddenError


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
def test_active_allowed_roles_can_create_student(role: str) -> None:
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

    actor_id = AuthorizationService(table).authorize_create_student("subject-123")

    assert actor_id == "user-1"
    assert table.call == {
        "Key": {"PK": "COGNITO#subject-123", "SK": "AUTHORIZATION"},
        "ConsistentRead": True,
    }


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
