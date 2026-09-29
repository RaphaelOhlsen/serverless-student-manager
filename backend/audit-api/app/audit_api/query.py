import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TypeGuard
from urllib.parse import parse_qsl

from audit_api.errors import InvalidAuditCursorError, InvalidAuditQueryRequestError

_ALLOWED_PARAMETERS = {
    "from",
    "to",
    "resourceType",
    "resourceId",
    "eventType",
    "actorId",
    "result",
    "correlationId",
    "limit",
    "cursor",
}
_RFC3339_UTC_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z\Z")
_MAX_EXACT_VALUE_BYTES = 512
MAX_CURSOR_BYTES = 4096


class AccessPath(StrEnum):
    CORRELATION = "CORRELATION"
    RESOURCE = "RESOURCE"
    ACTOR = "ACTOR"
    PERIOD = "PERIOD"


@dataclass(frozen=True)
class AuditQuery:
    from_timestamp: str
    to_timestamp: str
    resource_type: str | None
    resource_id: str | None
    event_type: str | None
    actor_id: str | None
    result: str | None
    correlation_id: str | None
    limit: int
    cursor: str | None
    access_path: AccessPath

    def cursor_binding(self) -> dict[str, str | int | None]:
        return {
            "from": self.from_timestamp,
            "to": self.to_timestamp,
            "resourceType": self.resource_type,
            "resourceId": self.resource_id,
            "eventType": self.event_type,
            "actorId": self.actor_id,
            "result": self.result,
            "correlationId": self.correlation_id,
            "limit": self.limit,
            "accessPath": self.access_path.value,
        }


def parse_audit_query(event: Mapping[str, object]) -> AuditQuery:
    raw_query = event.get("rawQueryString")
    if not isinstance(raw_query, str) or re.search(r"%(?![0-9A-Fa-f]{2})", raw_query):
        raise InvalidAuditQueryRequestError

    try:
        pairs = parse_qsl(
            raw_query,
            keep_blank_values=True,
            strict_parsing=True,
            errors="strict",
            max_num_fields=len(_ALLOWED_PARAMETERS),
        )
    except (UnicodeDecodeError, ValueError):
        raise InvalidAuditQueryRequestError from None

    parameters: dict[str, str] = {}
    for name, value in pairs:
        if name not in _ALLOWED_PARAMETERS or name in parameters:
            raise InvalidAuditQueryRequestError
        parameters[name] = value

    if "from" not in parameters or "to" not in parameters:
        raise InvalidAuditQueryRequestError

    from_timestamp, from_datetime = normalize_rfc3339_utc(parameters["from"])
    to_timestamp, to_datetime = normalize_rfc3339_utc(parameters["to"])
    if from_datetime > to_datetime or to_datetime - from_datetime > timedelta(days=366):
        raise InvalidAuditQueryRequestError

    resource_type = parameters.get("resourceType")
    if resource_type is not None and resource_type not in {"STUDENT", "USER"}:
        raise InvalidAuditQueryRequestError

    resource_id = _optional_exact(parameters, "resourceId")
    if resource_id is not None and resource_type is None:
        raise InvalidAuditQueryRequestError

    event_type = _optional_exact(parameters, "eventType")
    actor_id = _optional_exact(parameters, "actorId")
    correlation_id = _optional_exact(parameters, "correlationId")
    result = parameters.get("result")
    if result is not None and result not in {"SUCCESS", "FAILURE"}:
        raise InvalidAuditQueryRequestError

    limit = _parse_limit(parameters.get("limit"))
    cursor = _optional_cursor(parameters)
    access_path = select_access_path(
        correlation_id=correlation_id,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_id=actor_id,
    )
    return AuditQuery(
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
        resource_type=resource_type,
        resource_id=resource_id,
        event_type=event_type,
        actor_id=actor_id,
        result=result,
        correlation_id=correlation_id,
        limit=limit,
        cursor=cursor,
        access_path=access_path,
    )


def select_access_path(
    *,
    correlation_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    actor_id: str | None = None,
) -> AccessPath:
    if correlation_id is not None:
        return AccessPath.CORRELATION
    if resource_type is not None and resource_id is not None:
        return AccessPath.RESOURCE
    if actor_id is not None:
        return AccessPath.ACTOR
    return AccessPath.PERIOD


def normalize_rfc3339_utc(value: object) -> tuple[str, datetime]:
    if not isinstance(value, str) or _RFC3339_UTC_PATTERN.fullmatch(value) is None:
        raise InvalidAuditQueryRequestError
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise InvalidAuditQueryRequestError from None
    return parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z"), parsed


def valid_exact_value(value: object) -> TypeGuard[str]:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value.encode("utf-8")) <= _MAX_EXACT_VALUE_BYTES
        and not any(unicodedata.category(character).startswith("C") for character in value)
    )


def _optional_exact(parameters: Mapping[str, str], name: str) -> str | None:
    value = parameters.get(name)
    if value is not None and not valid_exact_value(value):
        raise InvalidAuditQueryRequestError
    return value


def _optional_cursor(parameters: Mapping[str, str]) -> str | None:
    value = parameters.get("cursor")
    if value is not None and (not value or len(value.encode("utf-8")) > MAX_CURSOR_BYTES):
        raise InvalidAuditCursorError
    return value


def _parse_limit(value: str | None) -> int:
    if value is None:
        return 50
    if not value.isascii() or not value.isdecimal():
        raise InvalidAuditQueryRequestError
    limit = int(value)
    if not 1 <= limit <= 100:
        raise InvalidAuditQueryRequestError
    return limit
