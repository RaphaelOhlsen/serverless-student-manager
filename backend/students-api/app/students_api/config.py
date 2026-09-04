import os

SERVICE_NAME = os.getenv("POWERTOOLS_SERVICE_NAME", "students-api")
METRICS_NAMESPACE = os.getenv(
    "POWERTOOLS_METRICS_NAMESPACE",
    "ServerlessStudentManager",
)


def get_students_table_name() -> str:
    table_name = os.getenv("STUDENTS_TABLE_NAME")

    if not table_name:
        raise RuntimeError("STUDENTS_TABLE_NAME environment variable is required")

    return table_name


def get_users_table_name() -> str:
    table_name = os.getenv("USERS_TABLE_NAME")

    if not table_name:
        raise RuntimeError("USERS_TABLE_NAME environment variable is required")

    return table_name


def _required(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"{name} environment variable is required")
    return value


def get_audit_table_name() -> str:
    return _required("AUDIT_TABLE_NAME")


def get_idempotency_table_name() -> str:
    return _required("IDEMPOTENCY_TABLE_NAME")


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
