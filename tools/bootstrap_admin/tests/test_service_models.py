from dataclasses import FrozenInstanceError

import pytest

from tools.bootstrap_admin.service_models import (
    BootstrapResult,
    FirstAdminBootstrapConfig,
)


def test_first_admin_bootstrap_config_accepts_valid_values() -> None:
    config = FirstAdminBootstrapConfig(
        environment="dev",
        user_pool_id="pool-123",
        users_table_name="users-table",
        audit_table_name="audit-table",
        audit_retention_days=90,
    )

    assert config.environment == "dev"
    assert config.audit_retention_days == 90


@pytest.mark.parametrize(
    "field",
    ["environment", "user_pool_id", "users_table_name", "audit_table_name"],
)
def test_first_admin_bootstrap_config_rejects_empty_string(field: str) -> None:
    values: dict[str, object] = {
        "environment": "dev",
        "user_pool_id": "pool-123",
        "users_table_name": "users-table",
        "audit_table_name": "audit-table",
        "audit_retention_days": 90,
    }
    values[field] = ""

    with pytest.raises(ValueError, match=field):
        FirstAdminBootstrapConfig(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("retention_days", [0, -1])
def test_first_admin_bootstrap_config_rejects_nonpositive_retention(
    retention_days: int,
) -> None:
    with pytest.raises(ValueError, match="audit_retention_days"):
        FirstAdminBootstrapConfig(
            environment="dev",
            user_pool_id="pool-123",
            users_table_name="users-table",
            audit_table_name="audit-table",
            audit_retention_days=retention_days,
        )


@pytest.mark.parametrize(
    "state",
    ["COMPLETED", "COMPENSATED", "RECONCILIATION_REQUIRED"],
)
def test_bootstrap_result_accepts_terminal_state(state: str) -> None:
    result = BootstrapResult(
        operation_id="operation-123",
        user_id="user-123",
        state=state,  # type: ignore[arg-type]
        replayed=False,
    )

    assert result.state == state


def test_bootstrap_result_is_immutable() -> None:
    result = BootstrapResult(
        operation_id="operation-123",
        user_id="user-123",
        state="COMPLETED",
        replayed=False,
    )

    with pytest.raises(FrozenInstanceError):
        result.replayed = True  # type: ignore[misc]
