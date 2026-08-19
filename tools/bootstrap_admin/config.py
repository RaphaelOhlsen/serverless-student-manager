import os


def _get_required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"{name} environment variable is required")

    return value


def get_aws_region() -> str:
    return _get_required_env("AWS_REGION")


def get_cognito_user_pool_id() -> str:
    return _get_required_env("COGNITO_USER_POOL_ID")


def get_users_table_name() -> str:
    return _get_required_env("USERS_TABLE_NAME")


def get_audit_table_name() -> str:
    return _get_required_env("AUDIT_TABLE_NAME")


def get_idempotency_table_name() -> str:
    return _get_required_env("IDEMPOTENCY_TABLE_NAME")
