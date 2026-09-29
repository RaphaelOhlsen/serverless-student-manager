import base64
import json
from urllib.parse import urlencode

import pytest
from audit_api.cursor import CursorContinuation, EventPosition, decode_cursor, encode_cursor
from audit_api.errors import InvalidAuditCursorError
from audit_api.query import MAX_CURSOR_BYTES, AuditQuery, parse_audit_query


def query(*, limit: int = 50, actor_id: str = "admin-1") -> AuditQuery:
    return parse_audit_query(
        {
            "rawQueryString": (
                "from=2026-09-01T00%3A00%3A00Z&to=2026-09-28T00%3A00%3A00Z"
                f"&actorId={actor_id}&limit={limit}"
            )
        }
    )


def raw_cursor(payload: str) -> str:
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def legacy_cursor(query_value: AuditQuery, continuation: CursorContinuation) -> str:
    payload = {
        "v": 1,
        "query": query_value.cursor_binding(),
        "continuation": {
            "bucket": continuation.bucket,
            "position": {
                "occurredAt": continuation.position.occurred_at,
                "eventId": continuation.position.event_id,
                "resourceType": continuation.position.resource_type,
                "resourceId": continuation.position.resource_id,
            }
            if continuation.position is not None
            else None,
        },
    }
    return raw_cursor(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def position(month: str = "2026-09") -> EventPosition:
    return EventPosition(
        occurred_at=f"{month}-20T00:00:00.000Z",
        event_id="event-1",
        resource_type="STUDENT",
        resource_id="student-1",
    )


def test_cursor_round_trip_is_url_safe_unpadded_and_query_bound() -> None:
    original_query = query()
    continuation = CursorContinuation(bucket=None, position=position())
    cursor = encode_cursor(original_query, continuation)

    assert "=" not in cursor
    assert decode_cursor(cursor, original_query) == continuation


def test_v2_cursor_is_compact_and_self_accepted_by_request_parser() -> None:
    original_query = query(limit=1)
    continuation = CursorContinuation(bucket=None, position=position())
    cursor = encode_cursor(original_query, continuation)
    payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))

    resumed_query = parse_audit_query(
        {
            "rawQueryString": urlencode(
                {
                    "from": "2026-09-01T00:00:00Z",
                    "to": "2026-09-28T00:00:00Z",
                    "actorId": "admin-1",
                    "limit": "1",
                    "cursor": cursor,
                }
            )
        }
    )

    assert payload["v"] == 2
    assert isinstance(payload["query"], str)
    assert len(payload["query"]) == 64
    assert len(cursor.encode()) <= MAX_CURSOR_BYTES
    assert decode_cursor(resumed_query.cursor or "", resumed_query) == continuation


def test_maximum_valid_v2_cursor_remains_within_safety_limit() -> None:
    maximum_value = '"' * 512
    original_query = parse_audit_query(
        {
            "rawQueryString": urlencode(
                {
                    "from": "2026-08-01T00:00:00Z",
                    "to": "2026-09-30T23:59:59.999Z",
                    "resourceType": "STUDENT",
                    "resourceId": maximum_value,
                    "eventType": maximum_value,
                    "actorId": maximum_value,
                    "result": "SUCCESS",
                    "correlationId": maximum_value,
                    "limit": "100",
                }
            )
        }
    )
    continuation = CursorContinuation(
        bucket=None,
        position=EventPosition(
            occurred_at="2026-09-20T00:00:00.000Z",
            event_id=maximum_value,
            resource_type="STUDENT",
            resource_id=maximum_value,
        ),
    )

    cursor = encode_cursor(original_query, continuation)

    assert len(cursor.encode()) == 3024
    assert len(cursor.encode()) <= MAX_CURSOR_BYTES
    assert decode_cursor(cursor, original_query) == continuation


def test_decodes_legacy_v1_cursor_within_safety_limit() -> None:
    original_query = query()
    continuation = CursorContinuation(bucket=None, position=position())
    cursor = legacy_cursor(original_query, continuation)
    resumed_query = parse_audit_query(
        {
            "rawQueryString": urlencode(
                {
                    "from": "2026-09-01T00:00:00Z",
                    "to": "2026-09-28T00:00:00Z",
                    "actorId": "admin-1",
                    "limit": "50",
                    "cursor": cursor,
                }
            )
        }
    )

    assert len(cursor.encode()) <= MAX_CURSOR_BYTES
    assert decode_cursor(resumed_query.cursor or "", resumed_query) == continuation


def test_legacy_v1_cursor_remains_query_bound() -> None:
    original_query = query()
    cursor = legacy_cursor(original_query, CursorContinuation(None, position()))

    with pytest.raises(InvalidAuditCursorError):
        decode_cursor(cursor, query(actor_id="admin-2"))


@pytest.mark.parametrize("value", ["***", "YWJj=", "AB"])
def test_rejects_malformed_or_noncanonical_encoding(value: str) -> None:
    with pytest.raises(InvalidAuditCursorError):
        decode_cursor(value, query())


def test_rejects_unsupported_version() -> None:
    valid = json.loads(
        base64.urlsafe_b64decode(
            encode_cursor(query(), CursorContinuation(None, position())) + "=="
        )
    )
    valid["v"] = 3

    with pytest.raises(InvalidAuditCursorError):
        decode_cursor(raw_cursor(json.dumps(valid, separators=(",", ":"))), query())


def test_rejects_duplicate_json_fields() -> None:
    cursor = encode_cursor(query(), CursorContinuation(None, position()))
    payload = base64.urlsafe_b64decode(cursor + "==").decode()
    duplicate = payload[:-1] + ',"v":1}'

    with pytest.raises(InvalidAuditCursorError):
        decode_cursor(raw_cursor(duplicate), query())


def test_rejects_unknown_fields() -> None:
    cursor = encode_cursor(query(), CursorContinuation(None, position()))
    payload = json.loads(base64.urlsafe_b64decode(cursor + "=="))
    payload["unexpected"] = True

    with pytest.raises(InvalidAuditCursorError):
        decode_cursor(raw_cursor(json.dumps(payload, separators=(",", ":"))), query())


def test_rejects_tampered_query_fingerprint() -> None:
    original_query = query()
    cursor = encode_cursor(original_query, CursorContinuation(None, position()))
    payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    payload["query"] = "0" * 64

    with pytest.raises(InvalidAuditCursorError):
        decode_cursor(raw_cursor(json.dumps(payload, separators=(",", ":"))), original_query)


@pytest.mark.parametrize(
    "different_query",
    [
        query(actor_id="admin-2"),
        query(limit=51),
        parse_audit_query(
            {
                "rawQueryString": (
                    "from=2026-09-01T00%3A00%3A00Z&to=2026-09-28T00%3A00%3A00Z"
                    "&correlationId=correlation-1&limit=50"
                )
            }
        ),
    ],
)
def test_rejects_cursor_for_different_query_limit_or_access_path(
    different_query: AuditQuery,
) -> None:
    cursor = encode_cursor(query(), CursorContinuation(None, position()))

    with pytest.raises(InvalidAuditCursorError):
        decode_cursor(cursor, different_query)


def test_rejects_impossible_period_bucket_position_combination() -> None:
    period_query = parse_audit_query(
        {"rawQueryString": ("from=2026-08-01T00%3A00%3A00Z&to=2026-09-30T00%3A00%3A00Z&limit=50")}
    )

    with pytest.raises(RuntimeError):
        encode_cursor(period_query, CursorContinuation("2026-08", position("2026-09")))


def test_rejects_bucket_on_single_partition_cursor() -> None:
    with pytest.raises(RuntimeError):
        encode_cursor(query(), CursorContinuation("2026-09", position()))


def test_decode_rejects_structurally_impossible_period_position() -> None:
    period_query = parse_audit_query(
        {"rawQueryString": "from=2026-08-01T00%3A00%3A00Z&to=2026-09-30T00%3A00%3A00Z"}
    )
    valid = encode_cursor(period_query, CursorContinuation("2026-09", position("2026-09")))
    payload = json.loads(base64.urlsafe_b64decode(valid + "=" * (-len(valid) % 4)))
    payload["continuation"]["bucket"] = "2026-08"

    with pytest.raises(InvalidAuditCursorError):
        decode_cursor(raw_cursor(json.dumps(payload, separators=(",", ":"))), period_query)
