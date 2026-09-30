from functools import lru_cache
from typing import Any

import boto3  # type: ignore[import-untyped]

from audit_api.authorization import AdminAuthorizationService
from audit_api.config import (
    get_audit_cursor_kms_key_arn,
    get_audit_table_name,
    get_users_table_name,
)
from audit_api.cursor_mac import KmsCursorMac
from audit_api.query_engine import AuditQueryEngine
from audit_api.repository import AuditEventRepository
from audit_api.service import AuditQueryService


@lru_cache
def get_audit_query_service() -> AuditQueryService:
    dynamodb = boto3.resource("dynamodb")
    users_table: Any = dynamodb.Table(get_users_table_name())
    audit_table: Any = dynamodb.Table(get_audit_table_name())
    kms: Any = boto3.client("kms")
    return AuditQueryService(
        AdminAuthorizationService(users_table),
        AuditQueryEngine(
            AuditEventRepository(audit_table),
            KmsCursorMac(kms, get_audit_cursor_kms_key_arn()),
        ),
    )
