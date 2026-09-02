import base64
import json

import pytest
from students_api.cursor import CursorPosition, decode_cursor, encode_cursor, normalize_name
from students_api.errors import InvalidListRequestError


def test_cursor_round_trip_is_url_safe_without_padding() -> None:
    position = CursorPosition("student_123", "ana maria")
    cursor = encode_cursor("ACTIVE", "ana", position)

    assert "=" not in cursor
    assert decode_cursor(cursor, "ACTIVE", "ana") == position


def test_name_normalization_uses_nfkc_whitespace_and_case_folding() -> None:
    assert normalize_name("  ＡNA\t  Silva  ") == "ana silva"


@pytest.mark.parametrize("value", ["invalid+base64", "abc=", "e30", ""])
def test_malformed_cursor_is_rejected(value: str) -> None:
    with pytest.raises(InvalidListRequestError):
        decode_cursor(value, "ACTIVE", None)


def test_incompatible_cursor_is_rejected() -> None:
    cursor = encode_cursor("ACTIVE", None, CursorPosition("student-1", "ana"))

    with pytest.raises(InvalidListRequestError):
        decode_cursor(cursor, "INACTIVE", None)


def test_duplicate_or_unknown_cursor_fields_are_rejected() -> None:
    raw = (
        '{"v":1,"v":1,"status":"ACTIVE","namePrefix":null,'
        '"position":{"studentId":"student-1","normalizedName":"ana"}}'
    )
    duplicate = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    payload = {
        "v": 1,
        "status": "ACTIVE",
        "namePrefix": None,
        "position": {"studentId": "student-1", "normalizedName": "ana"},
        "PK": "forbidden",
    }
    unknown = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )

    for cursor in (duplicate, unknown):
        with pytest.raises(InvalidListRequestError):
            decode_cursor(cursor, "ACTIVE", None)


def test_cursor_rejects_invalid_field_types_as_bad_request() -> None:
    payload = {
        "v": True,
        "status": ["ACTIVE"],
        "namePrefix": None,
        "position": {"studentId": "student-1", "normalizedName": "ana"},
    }
    cursor = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )

    with pytest.raises(InvalidListRequestError):
        decode_cursor(cursor, "ACTIVE", None)
