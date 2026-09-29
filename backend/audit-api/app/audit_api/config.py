import os

SERVICE_NAME = os.getenv("POWERTOOLS_SERVICE_NAME", "audit-api")
METRICS_NAMESPACE = os.getenv("POWERTOOLS_METRICS_NAMESPACE", "ServerlessStudentManager")


def get_users_table_name() -> str:
    return _required("USERS_TABLE_NAME")


def get_audit_table_name() -> str:
    return _required("AUDIT_TABLE_NAME")


def _required(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"{name} environment variable is required")
    return value
