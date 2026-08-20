import pytest

from tools.bootstrap_admin.config import (
    get_app_environment,
    get_audit_retention_days,
    get_audit_table_name,
    get_aws_region,
    get_cognito_user_pool_id,
    get_idempotency_table_name,
    get_users_table_name,
)


@pytest.mark.parametrize(
    ("env_name", "getter"),
    [
        ("AWS_REGION", get_aws_region),
        ("COGNITO_USER_POOL_ID", get_cognito_user_pool_id),
        ("USERS_TABLE_NAME", get_users_table_name),
        ("AUDIT_TABLE_NAME", get_audit_table_name),
        ("IDEMPOTENCY_TABLE_NAME", get_idempotency_table_name),
    ],
)
def test_required_environment_variable_is_returned(
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    getter: object,
) -> None:
    monkeypatch.setenv(env_name, "expected-value")

    assert callable(getter)
    assert getter() == "expected-value"


@pytest.mark.parametrize(
    ("env_name", "getter"),
    [
        ("AWS_REGION", get_aws_region),
        ("COGNITO_USER_POOL_ID", get_cognito_user_pool_id),
        ("USERS_TABLE_NAME", get_users_table_name),
        ("AUDIT_TABLE_NAME", get_audit_table_name),
        ("IDEMPOTENCY_TABLE_NAME", get_idempotency_table_name),
    ],
)
def test_required_environment_variable_missing_raises(
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    getter: object,
) -> None:
    monkeypatch.delenv(env_name, raising=False)

    assert callable(getter)

    with pytest.raises(
        RuntimeError,
        match=rf"^{env_name} environment variable is required$",
    ):
        getter()


def test_app_environment_is_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "dev")

    assert get_app_environment() == "dev"


@pytest.mark.parametrize("value", [None, ""])
def test_app_environment_is_required(
    monkeypatch: pytest.MonkeyPatch,
    value: str | None,
) -> None:
    if value is None:
        monkeypatch.delenv("APP_ENVIRONMENT", raising=False)
    else:
        monkeypatch.setenv("APP_ENVIRONMENT", value)

    with pytest.raises(
        RuntimeError,
        match=r"^APP_ENVIRONMENT environment variable is required$",
    ):
        get_app_environment()


def test_audit_retention_days_returns_positive_integer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", "90")

    assert get_audit_retention_days() == 90


@pytest.mark.parametrize("value", ["0", "-1", "invalid", "1.5"])
def test_audit_retention_days_rejects_invalid_value(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", value)

    with pytest.raises(
        RuntimeError,
        match=r"^AUDIT_RETENTION_DAYS must be a positive integer$",
    ):
        get_audit_retention_days()


def test_audit_retention_days_is_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUDIT_RETENTION_DAYS", raising=False)

    with pytest.raises(
        RuntimeError,
        match=r"^AUDIT_RETENTION_DAYS environment variable is required$",
    ):
        get_audit_retention_days()
