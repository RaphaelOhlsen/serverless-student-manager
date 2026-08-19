import pytest

from tools.bootstrap_admin.config import (
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
