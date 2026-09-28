from decimal import Decimal

import pytest
from audit_api.authorization import AdminAuthorizationService
from audit_api.errors import AuditForbiddenError

SUB = "cognito-sub-1"
USER_ID = "user-1"


def authorization_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "PK": f"COGNITO#{SUB}",
        "SK": "AUTHORIZATION",
        "userId": USER_ID,
        "cognitoSub": SUB,
        "role": "ADMIN",
        "status": "ACTIVE",
        "authVersion": Decimal("3"),
    }
    item.update(overrides)
    return item


def profile_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "PK": f"USER#{USER_ID}",
        "SK": "PROFILE",
        "userId": USER_ID,
        "cognitoSub": SUB,
        "role": "ADMIN",
        "status": "ACTIVE",
        "authVersion": Decimal("3"),
    }
    item.update(overrides)
    return item


class FakeTable:
    def __init__(self, authorization: object, profile: object) -> None:
        self.authorization = authorization
        self.profile = profile
        self.calls: list[dict[str, object]] = []

    def get_item(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        key = kwargs["Key"]
        assert isinstance(key, dict)
        if key["SK"] == "AUTHORIZATION":
            return {} if self.authorization is None else {"Item": self.authorization}
        return {} if self.profile is None else {"Item": self.profile}


def test_authorizes_reconciled_active_admin_with_consistent_reads() -> None:
    table = FakeTable(authorization_item(), profile_item())

    actor = AdminAuthorizationService(table).authorize(SUB)

    assert actor.user_id == USER_ID
    assert table.calls == [
        {"Key": {"PK": f"COGNITO#{SUB}", "SK": "AUTHORIZATION"}, "ConsistentRead": True},
        {"Key": {"PK": f"USER#{USER_ID}", "SK": "PROFILE"}, "ConsistentRead": True},
    ]


@pytest.mark.parametrize("role", ["OPERATOR", "STUDENT"])
def test_non_admin_is_forbidden(role: str) -> None:
    table = FakeTable(authorization_item(role=role), profile_item(role=role))

    with pytest.raises(AuditForbiddenError):
        AdminAuthorizationService(table).authorize(SUB)


@pytest.mark.parametrize("status", ["INVITED", "INACTIVE"])
def test_non_active_user_is_forbidden(status: str) -> None:
    table = FakeTable(authorization_item(status=status), profile_item(status=status))

    with pytest.raises(AuditForbiddenError):
        AdminAuthorizationService(table).authorize(SUB)


@pytest.mark.parametrize(
    ("authorization", "profile"),
    [
        (None, profile_item()),
        (authorization_item(), None),
        (authorization_item(authVersion=Decimal("0")), profile_item(authVersion=Decimal("0"))),
        (authorization_item(), profile_item(role="OPERATOR")),
        (authorization_item(), profile_item(cognitoSub="different")),
        (authorization_item(), profile_item(userId="different")),
        (authorization_item(PK="wrong"), profile_item()),
    ],
)
def test_missing_malformed_or_inconsistent_state_is_forbidden(
    authorization: object, profile: object
) -> None:
    with pytest.raises(AuditForbiddenError):
        AdminAuthorizationService(FakeTable(authorization, profile)).authorize(SUB)
