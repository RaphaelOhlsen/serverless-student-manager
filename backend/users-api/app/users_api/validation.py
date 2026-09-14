import json
import unicodedata
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from users_api.cursor import normalize_name
from users_api.errors import InvalidAdminUserWriteRequestError


@dataclass(frozen=True)
class CreateUserInput:
    full_name: str
    normalized_name: str
    email: str
    role: str

    def canonical_payload(self) -> dict[str, str]:
        return {
            "fullName": self.full_name,
            "email": self.email,
            "role": self.role,
        }


@dataclass(frozen=True)
class ResendInvitationInput:
    expected_version: int

    def canonical_payload(self) -> dict[str, int]:
        return {"expectedVersion": self.expected_version}


def parse_create_user_body(body: str) -> CreateUserInput:
    value = _parse_strict_object(body)
    if set(value) != {"fullName", "email", "role"}:
        raise InvalidAdminUserWriteRequestError
    if any(not isinstance(value[field], str) for field in value):
        raise InvalidAdminUserWriteRequestError

    full_name = normalize_admin_user_full_name(value["fullName"])
    email = normalize_admin_user_email(value["email"])
    role = value["role"]
    if role not in {"ADMIN", "OPERATOR"}:
        raise InvalidAdminUserWriteRequestError
    return CreateUserInput(
        full_name=full_name,
        normalized_name=normalize_name(full_name),
        email=email,
        role=role,
    )


def parse_resend_invitation_body(body: str) -> ResendInvitationInput:
    value = _parse_strict_object(body)
    if (
        set(value) != {"expectedVersion"}
        or type(value["expectedVersion"]) is not int
        or value["expectedVersion"] < 1
    ):
        raise InvalidAdminUserWriteRequestError
    return ResendInvitationInput(expected_version=value["expectedVersion"])


def validate_idempotency_key(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidAdminUserWriteRequestError
    try:
        if str(UUID(value)) != value:
            raise InvalidAdminUserWriteRequestError
    except (ValueError, AttributeError):
        raise InvalidAdminUserWriteRequestError from None
    return value


def normalize_admin_user_full_name(value: str) -> str:
    if not isinstance(value, str) or any(_is_control(character) for character in value):
        raise InvalidAdminUserWriteRequestError
    normalized = unicodedata.normalize("NFKC", value)
    normalized = " ".join(normalized.strip().split())
    if not 2 <= len(normalized) <= 150:
        raise InvalidAdminUserWriteRequestError
    return normalized


def normalize_admin_user_email(value: str) -> str:
    if not isinstance(value, str):
        raise InvalidAdminUserWriteRequestError
    normalized = value.strip().lower()
    if (
        not normalized
        or len(normalized) > 254
        or any(character.isspace() or _is_control(character) for character in normalized)
        or normalized.count("@") != 1
    ):
        raise InvalidAdminUserWriteRequestError
    local, domain = normalized.split("@")
    if (
        not local
        or not domain
        or domain.startswith(".")
        or domain.endswith(".")
        or "." not in domain
    ):
        raise InvalidAdminUserWriteRequestError
    return normalized


def _parse_strict_object(body: str) -> dict[str, Any]:
    if not isinstance(body, str):
        raise InvalidAdminUserWriteRequestError
    try:
        value = json.loads(body, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        raise InvalidAdminUserWriteRequestError from None
    if not isinstance(value, dict):
        raise InvalidAdminUserWriteRequestError
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _is_control(character: str) -> bool:
    return unicodedata.category(character).startswith("C")
