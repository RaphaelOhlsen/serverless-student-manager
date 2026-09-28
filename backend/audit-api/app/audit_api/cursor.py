import base64
import binascii
import json
import re
from dataclasses import dataclass
from typing import Any

from audit_api.errors import InvalidAuditCursorError, InvalidAuditQueryRequestError
from audit_api.query import AccessPath, AuditQuery, normalize_rfc3339_utc, valid_exact_value

_TOP_LEVEL_FIELDS = {"v", "query", "continuation"}
_QUERY_FIELDS = {
    "from",
    "to",
    "resourceType",
    "resourceId",
    "eventType",
    "actorId",
    "result",
    "correlationId",
    "limit",
    "accessPath",
}
_CONTINUATION_FIELDS = {"bucket", "position"}
_POSITION_FIELDS = {"occurredAt", "eventId", "resourceType", "resourceId"}
_MONTH_PATTERN = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])\Z")


@dataclass(frozen=True)
class EventPosition:
    occurred_at: str
    event_id: str
    resource_type: str
    resource_id: str


@dataclass(frozen=True)
class CursorContinuation:
    bucket: str | None
    position: EventPosition | None


def encode_cursor(query: AuditQuery, continuation: CursorContinuation) -> str:
    try:
        validate_continuation(query, continuation)
    except InvalidAuditCursorError:
        raise RuntimeError("Cannot encode invalid audit cursor continuation") from None
    payload = {
        "v": 1,
        "query": query.cursor_binding(),
        "continuation": {
            "bucket": continuation.bucket,
            "position": _position_payload(continuation.position),
        },
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(value: str, query: AuditQuery) -> CursorContinuation:
    if not value or "=" in value or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        raise InvalidAuditCursorError
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        if base64.urlsafe_b64encode(raw).decode().rstrip("=") != value:
            raise ValueError("non-canonical Base64URL")
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise InvalidAuditCursorError from None

    if not isinstance(payload, dict) or set(payload) != _TOP_LEVEL_FIELDS:
        raise InvalidAuditCursorError
    if type(payload["v"]) is not int or payload["v"] != 1:
        raise InvalidAuditCursorError
    binding = payload["query"]
    if (
        not isinstance(binding, dict)
        or set(binding) != _QUERY_FIELDS
        or not _valid_binding_types(binding)
        or binding != query.cursor_binding()
    ):
        raise InvalidAuditCursorError

    raw_continuation = payload["continuation"]
    if not isinstance(raw_continuation, dict) or set(raw_continuation) != _CONTINUATION_FIELDS:
        raise InvalidAuditCursorError
    bucket = raw_continuation["bucket"]
    if bucket is not None and not isinstance(bucket, str):
        raise InvalidAuditCursorError
    continuation = CursorContinuation(
        bucket=bucket,
        position=_parse_position(raw_continuation["position"]),
    )
    validate_continuation(query, continuation)
    return continuation


def validate_continuation(query: AuditQuery, continuation: CursorContinuation) -> None:
    position = continuation.position
    if query.access_path is AccessPath.PERIOD:
        if not _valid_bucket(continuation.bucket, query):
            raise InvalidAuditCursorError
        if position is not None and position.occurred_at[:7] != continuation.bucket:
            raise InvalidAuditCursorError
    elif continuation.bucket is not None or position is None:
        raise InvalidAuditCursorError

    if position is None:
        return
    try:
        normalized, occurred_at = normalize_rfc3339_utc(position.occurred_at)
        _, from_datetime = normalize_rfc3339_utc(query.from_timestamp)
        _, to_datetime = normalize_rfc3339_utc(query.to_timestamp)
    except InvalidAuditQueryRequestError:
        raise InvalidAuditCursorError from None
    if (
        normalized != position.occurred_at
        or not from_datetime <= occurred_at <= to_datetime
        or position.resource_type not in {"STUDENT", "USER"}
        or not valid_exact_value(position.event_id)
        or not valid_exact_value(position.resource_id)
    ):
        raise InvalidAuditCursorError
    if query.access_path is AccessPath.RESOURCE and (
        position.resource_type != query.resource_type or position.resource_id != query.resource_id
    ):
        raise InvalidAuditCursorError


def _valid_bucket(bucket: str | None, query: AuditQuery) -> bool:
    return (
        isinstance(bucket, str)
        and _MONTH_PATTERN.fullmatch(bucket) is not None
        and query.from_timestamp[:7] <= bucket <= query.to_timestamp[:7]
    )


def _valid_binding_types(binding: dict[str, object]) -> bool:
    required_strings = ("from", "to", "accessPath")
    optional_strings = (
        "resourceType",
        "resourceId",
        "eventType",
        "actorId",
        "result",
        "correlationId",
    )
    return (
        all(isinstance(binding[name], str) for name in required_strings)
        and all(
            binding[name] is None or isinstance(binding[name], str) for name in optional_strings
        )
        and type(binding["limit"]) is int
    )


def _position_payload(position: EventPosition | None) -> dict[str, str] | None:
    if position is None:
        return None
    return {
        "occurredAt": position.occurred_at,
        "eventId": position.event_id,
        "resourceType": position.resource_type,
        "resourceId": position.resource_id,
    }


def _parse_position(value: object) -> EventPosition | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != _POSITION_FIELDS:
        raise InvalidAuditCursorError
    occurred_at = value["occurredAt"]
    event_id = value["eventId"]
    resource_type = value["resourceType"]
    resource_id = value["resourceId"]
    if not all(
        isinstance(field, str) for field in (occurred_at, event_id, resource_type, resource_id)
    ):
        raise InvalidAuditCursorError
    return EventPosition(occurred_at, event_id, resource_type, resource_id)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result
