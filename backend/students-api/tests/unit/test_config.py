import pytest
from students_api.config import (
    get_audit_retention_days,
    get_audit_table_name,
    get_environment,
    get_idempotency_table_name,
)


def test_create_student_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIT_TABLE_NAME", "Audit")
    monkeypatch.setenv("IDEMPOTENCY_TABLE_NAME", "Idempotency")
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", "90")

    assert get_audit_table_name() == "Audit"
    assert get_idempotency_table_name() == "Idempotency"
    assert get_environment() == "dev"
    assert get_audit_retention_days() == 90


@pytest.mark.parametrize("value", ["", "zero", "0", "-1"])
def test_invalid_audit_retention_is_rejected(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", value)

    with pytest.raises(RuntimeError):
        get_audit_retention_days()
