from collections.abc import Callable

import pytest
from users_api import config


@pytest.mark.parametrize(
    ("name", "getter"),
    [
        ("USERS_TABLE_NAME", config.get_users_table_name),
        ("AUDIT_TABLE_NAME", config.get_audit_table_name),
        ("IDEMPOTENCY_TABLE_NAME", config.get_idempotency_table_name),
        ("USER_POOL_ID", config.get_user_pool_id),
        ("ENVIRONMENT", config.get_environment),
    ],
)
def test_required_configuration(
    monkeypatch: pytest.MonkeyPatch, name: str, getter: Callable[[], str]
) -> None:
    monkeypatch.setenv(name, "configured")
    assert getter() == "configured"
    monkeypatch.delenv(name)
    with pytest.raises(RuntimeError):
        getter()


def test_audit_retention_must_be_positive_integer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", "90")
    assert config.get_audit_retention_days() == 90
    for invalid in ("zero", "0", "-1"):
        monkeypatch.setenv("AUDIT_RETENTION_DAYS", invalid)
        with pytest.raises(RuntimeError):
            config.get_audit_retention_days()
