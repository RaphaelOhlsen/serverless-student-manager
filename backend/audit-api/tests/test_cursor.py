import base64
import hashlib
import hmac
import json
from typing import cast
from urllib.parse import urlencode

import pytest
from audit_api.cursor import CursorContinuation, EventPosition, decode_cursor, encode_cursor
from audit_api.errors import InvalidAuditCursorError
from audit_api.query import MAX_CURSOR_BYTES, AuditQuery, parse_audit_query


class LocalMac:
    def __init__(self, key: bytes = b"test-key") -> None:
        self.key = key
        self.generate_calls: list[bytes] = []
        self.verify_calls: list[tuple[bytes, bytes]] = []

    def generate(self, message: bytes) -> bytes:
        self.generate_calls.append(message)
        return hmac.digest(self.key, message, hashlib.sha256)

    def verify(self, message: bytes, mac: bytes) -> bool:
        self.verify_calls.append((message, mac))
        return hmac.compare_digest(self.generate(message), mac)


def query(*, limit: int = 50, actor_id: str = "admin-1") -> AuditQuery:
    return parse_audit_query(
        {
            "rawQueryString": (
                "from=2026-09-01T00%3A00%3A00Z&to=2026-09-28T00%3A00%3A00Z"
                f"&actorId={actor_id}&limit={limit}"
            )
        }
    )


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def decode_part(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def signed_raw(payload: bytes, signer: LocalMac) -> str:
    return f"{b64url(payload)}.{b64url(signer.generate(payload))}"


def cursor_payload(cursor: str) -> dict[str, object]:
    encoded_payload, _ = cursor.split(".")
    return cast(dict[str, object], json.loads(decode_part(encoded_payload)))


def position(month: str = "2026-09") -> EventPosition:
    return EventPosition(
        occurred_at=f"{month}-20T00:00:00.000Z",
        event_id="event-1",
        resource_type="STUDENT",
        resource_id="student-1",
    )


def test_cursor_v3_round_trip_is_url_safe_unpadded_signed_and_query_bound() -> None:
    signer = LocalMac()
    original_query = query()
    continuation = CursorContinuation(bucket=None, position=position())

    cursor = encode_cursor(original_query, continuation, signer)
    encoded_payload, encoded_mac = cursor.split(".")

    assert "=" not in cursor
    assert cursor_payload(cursor)["v"] == 3
    assert len(decode_part(encoded_mac)) == 32
    assert signer.generate_calls[-1] == decode_part(encoded_payload)
    assert decode_cursor(cursor, original_query, signer) == continuation


def test_v3_cursor_is_compact_and_self_accepted_by_request_parser() -> None:
    signer = LocalMac()
    original_query = query(limit=1)
    continuation = CursorContinuation(bucket=None, position=position())
    cursor = encode_cursor(original_query, continuation, signer)
    payload = cursor_payload(cursor)

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

    assert payload["v"] == 3
    assert isinstance(payload["query"], str)
    assert len(str(payload["query"])) == 64
    assert len(cursor.encode()) <= MAX_CURSOR_BYTES
    assert decode_cursor(resumed_query.cursor or "", resumed_query, signer) == continuation


def test_maximum_valid_v3_cursor_remains_within_safety_limit() -> None:
    signer = LocalMac()
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

    cursor = encode_cursor(original_query, continuation, signer)

    assert len(cursor.encode()) <= MAX_CURSOR_BYTES
    assert decode_cursor(cursor, original_query, signer) == continuation


@pytest.mark.parametrize("value", ["***", "YWJj=", "AB", "abc.", ".abc", "a.b.c"])
def test_rejects_malformed_or_noncanonical_envelope(value: str) -> None:
    with pytest.raises(InvalidAuditCursorError):
        decode_cursor(value, query(), LocalMac())


def test_rejects_oversized_cursor_before_kms_verification() -> None:
    signer = LocalMac()

    with pytest.raises(InvalidAuditCursorError):
        decode_cursor("a" * MAX_CURSOR_BYTES + ".a", query(), signer)

    assert signer.verify_calls == []


def test_rejects_one_byte_payload_tampering() -> None:
    signer = LocalMac()
    cursor = encode_cursor(query(), CursorContinuation(None, position()), signer)
    encoded_payload, encoded_mac = cursor.split(".")
    payload = bytearray(decode_part(encoded_payload))
    payload[-2] ^= 1

    with pytest.raises(InvalidAuditCursorError):
        decode_cursor(f"{b64url(bytes(payload))}.{encoded_mac}", query(), signer)


def test_rejects_tampered_truncated_or_other_key_mac() -> None:
    signer = LocalMac()
    cursor = encode_cursor(query(), CursorContinuation(None, position()), signer)
    encoded_payload, encoded_mac = cursor.split(".")
    mac = bytearray(decode_part(encoded_mac))
    mac[-1] ^= 1
    other_mac = LocalMac(b"other-key").generate(decode_part(encoded_payload))

    for candidate in (
        f"{encoded_payload}.{b64url(bytes(mac))}",
        f"{encoded_payload}.{b64url(bytes(mac[:-1]))}",
        f"{encoded_payload}.{b64url(other_mac)}",
    ):
        with pytest.raises(InvalidAuditCursorError):
            decode_cursor(candidate, query(), signer)


@pytest.mark.parametrize("version", [1, 2, 4])
def test_rejects_previous_and_unknown_versions_even_with_valid_mac(version: int) -> None:
    signer = LocalMac()
    payload = cursor_payload(encode_cursor(query(), CursorContinuation(None, position()), signer))
    payload["v"] = version
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()

    with pytest.raises(InvalidAuditCursorError):
        decode_cursor(signed_raw(raw, signer), query(), signer)


def test_verifies_mac_before_parsing_payload() -> None:
    signer = LocalMac()
    malformed_json = b'{"v":3'
    expected_mac = signer.generate(malformed_json)
    signer.verify_calls.clear()

    with pytest.raises(InvalidAuditCursorError):
        decode_cursor(
            f"{b64url(malformed_json)}.{b64url(expected_mac)}",
            query(),
            signer,
        )

    assert signer.verify_calls == [(malformed_json, expected_mac)]


def test_rejects_structurally_invalid_payload_with_valid_mac() -> None:
    signer = LocalMac()
    raw = json.dumps({"v": 3}, separators=(",", ":")).encode()

    with pytest.raises(InvalidAuditCursorError):
        decode_cursor(signed_raw(raw, signer), query(), signer)


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
def test_rejects_cursor_for_different_filters_limit_or_access_path(
    different_query: AuditQuery,
) -> None:
    signer = LocalMac()
    cursor = encode_cursor(query(), CursorContinuation(None, position()), signer)

    with pytest.raises(InvalidAuditCursorError):
        decode_cursor(cursor, different_query, signer)


def test_rejects_syntactically_valid_cursor_with_invalid_position() -> None:
    signer = LocalMac()
    payload = cursor_payload(encode_cursor(query(), CursorContinuation(None, position()), signer))
    continuation = payload["continuation"]
    assert isinstance(continuation, dict)
    position_value = continuation["position"]
    assert isinstance(position_value, dict)
    position_value["occurredAt"] = "2027-01-01T00:00:00.000Z"
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()

    with pytest.raises(InvalidAuditCursorError):
        decode_cursor(signed_raw(raw, signer), query(), signer)


def test_encode_rejects_impossible_period_bucket_position_combination() -> None:
    period_query = parse_audit_query(
        {"rawQueryString": "from=2026-08-01T00%3A00%3A00Z&to=2026-09-30T00%3A00%3A00Z"}
    )

    with pytest.raises(RuntimeError):
        encode_cursor(
            period_query,
            CursorContinuation("2026-08", position("2026-09")),
            LocalMac(),
        )


def test_decode_rejects_structurally_impossible_period_position() -> None:
    signer = LocalMac()
    period_query = parse_audit_query(
        {"rawQueryString": "from=2026-08-01T00%3A00%3A00Z&to=2026-09-30T00%3A00%3A00Z"}
    )
    payload = cursor_payload(
        encode_cursor(
            period_query,
            CursorContinuation("2026-09", position("2026-09")),
            signer,
        )
    )
    continuation = payload["continuation"]
    assert isinstance(continuation, dict)
    continuation["bucket"] = "2026-08"
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()

    with pytest.raises(InvalidAuditCursorError):
        decode_cursor(signed_raw(raw, signer), period_query, signer)
