import base64
import binascii
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from students_api.errors import InvalidListRequestError

_STUDENT_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_CURSOR_FIELDS = {"v", "status", "namePrefix", "position"}
_POSITION_FIELDS = {"studentId", "normalizedName"}


@dataclass(frozen=True)
class CursorPosition:
    student_id: str
    normalized_name: str


def normalize_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).strip().split()).casefold()


def encode_cursor(status: str, name_prefix: str | None, position: CursorPosition) -> str:
    if (
        status not in {"ACTIVE", "INACTIVE", "ALL"}
        or not _valid_student_id(position.student_id)
        or not _valid_normalized_name(position.normalized_name)
    ):
        raise RuntimeError("Cannot encode invalid cursor position")
    payload = {
        "v": 1,
        "status": status,
        "namePrefix": name_prefix,
        "position": {
            "studentId": position.student_id,
            "normalizedName": position.normalized_name,
        },
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(value: str, status: str, name_prefix: str | None) -> CursorPosition:
    if not value or "=" in value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise InvalidListRequestError

    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        if base64.urlsafe_b64encode(raw).decode().rstrip("=") != value:
            raise ValueError("non-canonical Base64")
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise InvalidListRequestError from None

    if not isinstance(payload, dict) or set(payload) != _CURSOR_FIELDS:
        raise InvalidListRequestError
    version = payload["v"]
    cursor_status = payload["status"]
    if type(version) is not int or version != 1:  # bool is not a valid JSON version number
        raise InvalidListRequestError
    if not isinstance(cursor_status, str) or cursor_status not in {"ACTIVE", "INACTIVE", "ALL"}:
        raise InvalidListRequestError
    cursor_prefix = payload["namePrefix"]
    if cursor_prefix is not None and not isinstance(cursor_prefix, str):
        raise InvalidListRequestError
    if cursor_status != status or cursor_prefix != name_prefix:
        raise InvalidListRequestError

    position = payload["position"]
    if not isinstance(position, dict) or set(position) != _POSITION_FIELDS:
        raise InvalidListRequestError
    student_id = position["studentId"]
    normalized_name = position["normalizedName"]
    if not _valid_student_id(student_id):
        raise InvalidListRequestError
    if not _valid_normalized_name(normalized_name):
        raise InvalidListRequestError

    return CursorPosition(student_id=student_id, normalized_name=normalized_name)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _valid_normalized_name(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value.encode("utf-8")) <= 512
        and not any(unicodedata.category(character).startswith("C") for character in value)
        and normalize_name(value) == value
    )


def _valid_student_id(value: Any) -> bool:
    return isinstance(value, str) and _STUDENT_ID_PATTERN.fullmatch(value) is not None
