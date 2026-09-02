import os

SERVICE_NAME = os.getenv("POWERTOOLS_SERVICE_NAME", "users-api")
METRICS_NAMESPACE = os.getenv("POWERTOOLS_METRICS_NAMESPACE", "ServerlessStudentManager")


def _required(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"{name} is required")
    return value


def get_users_table_name() -> str:
    return _required("USERS_TABLE_NAME")


def get_audit_table_name() -> str:
    return _required("AUDIT_TABLE_NAME")


def get_idempotency_table_name() -> str:
    return _required("IDEMPOTENCY_TABLE_NAME")


def get_user_pool_id() -> str:
    return _required("USER_POOL_ID")


def get_environment() -> str:
    return _required("ENVIRONMENT")


def get_audit_retention_days() -> int:
    raw_value = _required("AUDIT_RETENTION_DAYS")
    try:
        value = int(raw_value)
    except ValueError as error:
        raise RuntimeError("AUDIT_RETENTION_DAYS must be a positive integer") from error
    if value <= 0:
        raise RuntimeError("AUDIT_RETENTION_DAYS must be a positive integer")
    return value
