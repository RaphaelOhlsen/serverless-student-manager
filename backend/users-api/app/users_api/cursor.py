import base64
import binascii
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from users_api.errors import InvalidAdminUserListRequestError

_USER_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_CURSOR_FIELDS = {"v", "role", "status", "namePrefix", "email", "position"}
_POSITION_FIELDS = {"userId", "normalizedName"}


@dataclass(frozen=True)
class UserCursorPosition:
    user_id: str
    normalized_name: str


def normalize_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).strip().split()).casefold()


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if (
        not normalized
        or len(normalized) > 254
        or any(
            character.isspace() or unicodedata.category(character).startswith("C")
            for character in normalized
        )
    ):
        raise InvalidAdminUserListRequestError
    return normalized


def encode_cursor(
    *,
    role: str,
    status: str,
    name_prefix: str | None,
    position: UserCursorPosition,
) -> str:
    if (
        role not in {"ADMIN", "OPERATOR", "ALL"}
        or status not in {"INVITED", "ACTIVE", "INACTIVE", "ALL"}
        or not _valid_user_id(position.user_id)
        or not _valid_normalized_name(position.normalized_name)
    ):
        raise RuntimeError("Cannot encode invalid user cursor position")
    payload = {
        "v": 1,
        "role": role,
        "status": status,
        "namePrefix": name_prefix,
        "email": None,
        "position": {
            "userId": position.user_id,
            "normalizedName": position.normalized_name,
        },
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(
    value: str,
    *,
    role: str,
    status: str,
    name_prefix: str | None,
) -> UserCursorPosition:
    if not value or "=" in value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise InvalidAdminUserListRequestError
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        if base64.urlsafe_b64encode(raw).decode().rstrip("=") != value:
            raise ValueError("non-canonical Base64")
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise InvalidAdminUserListRequestError from None

    if not isinstance(payload, dict) or set(payload) != _CURSOR_FIELDS:
        raise InvalidAdminUserListRequestError
    if type(payload["v"]) is not int or payload["v"] != 1:
        raise InvalidAdminUserListRequestError
    if (
        payload["role"] != role
        or payload["status"] != status
        or payload["namePrefix"] != name_prefix
        or payload["email"] is not None
    ):
        raise InvalidAdminUserListRequestError
    position = payload["position"]
    if not isinstance(position, dict) or set(position) != _POSITION_FIELDS:
        raise InvalidAdminUserListRequestError
    user_id = position["userId"]
    normalized_name = position["normalizedName"]
    if not _valid_user_id(user_id) or not _valid_normalized_name(normalized_name):
        raise InvalidAdminUserListRequestError
    return UserCursorPosition(user_id=user_id, normalized_name=normalized_name)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _valid_user_id(value: object) -> bool:
    return isinstance(value, str) and _USER_ID_PATTERN.fullmatch(value) is not None


def _valid_normalized_name(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value.encode("utf-8")) <= 512
        and not any(unicodedata.category(character).startswith("C") for character in value)
        and normalize_name(value) == value
    )
