import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from students_api.cursor import normalize_name
from students_api.errors import (
    InvalidCreateStudentRequestError,
    InvalidStudentLifecycleRequestError,
    InvalidUpdateStudentRequestError,
)

_FIELDS = {"fullName", "registrationNumber", "studentEmail", "phone", "birthDate"}
_REGISTRATION_PATTERN = re.compile(r"[A-Z0-9-]{4,20}\Z")
_PHONE_PATTERN = re.compile(r"\+[1-9][0-9]{7,14}\Z")


@dataclass(frozen=True)
class CreateStudentInput:
    full_name: str
    normalized_name: str
    registration_number: str
    student_email: str
    phone: str
    birth_date: str

    def payload(self) -> dict[str, str]:
        return {
            "fullName": self.full_name,
            "registrationNumber": self.registration_number,
            "studentEmail": self.student_email,
            "phone": self.phone,
            "birthDate": self.birth_date,
        }


def parse_create_student_body(
    body: str,
    *,
    today: date | None = None,
) -> CreateStudentInput:
    try:
        value = json.loads(body, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        raise InvalidCreateStudentRequestError from None
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise InvalidCreateStudentRequestError
    if not all(isinstance(value[field], str) for field in _FIELDS):
        raise InvalidCreateStudentRequestError

    full_name = _normalize_full_name(value["fullName"])
    registration_number = value["registrationNumber"].strip().upper()
    if _REGISTRATION_PATTERN.fullmatch(registration_number) is None:
        raise InvalidCreateStudentRequestError
    student_email = _normalize_email(value["studentEmail"])
    phone = _validate_phone(value["phone"])
    birth_date = _validate_birth_date(value["birthDate"], today=today)

    return CreateStudentInput(
        full_name=full_name,
        normalized_name=normalize_name(full_name),
        registration_number=registration_number,
        student_email=student_email,
        phone=phone,
        birth_date=birth_date,
    )


@dataclass(frozen=True)
class UpdateStudentInput:
    expected_version: int
    full_name: str | None = None
    student_email: str | None = None
    phone: str | None = None
    birth_date: str | None = None

    @property
    def normalized_name(self) -> str | None:
        return normalize_name(self.full_name) if self.full_name is not None else None

    def payload(self) -> dict[str, str | int]:
        result: dict[str, str | int] = {"expectedVersion": self.expected_version}
        for key, value in (
            ("fullName", self.full_name),
            ("studentEmail", self.student_email),
            ("phone", self.phone),
            ("birthDate", self.birth_date),
        ):
            if value is not None:
                result[key] = value
        return result


def parse_update_student_body(body: str, *, today: date | None = None) -> UpdateStudentInput:
    try:
        value = json.loads(body, object_pairs_hook=_unique_object)
    except (ValueError, UnicodeDecodeError):
        raise InvalidUpdateStudentRequestError from None
    mutable = {"fullName", "studentEmail", "phone", "birthDate"}
    if (
        not isinstance(value, dict)
        or not set(value) <= mutable | {"expectedVersion"}
        or not set(value) & mutable
        or type(value.get("expectedVersion")) is not int
        or value["expectedVersion"] < 1
        or any(not isinstance(value[key], str) for key in set(value) & mutable)
    ):
        raise InvalidUpdateStudentRequestError
    try:
        return UpdateStudentInput(
            expected_version=value["expectedVersion"],
            full_name=_normalize_full_name(value["fullName"]) if "fullName" in value else None,
            student_email=_normalize_email(value["studentEmail"])
            if "studentEmail" in value
            else None,
            phone=_validate_phone(value["phone"]) if "phone" in value else None,
            birth_date=(
                _validate_birth_date(value["birthDate"], today=today)
                if "birthDate" in value
                else None
            ),
        )
    except InvalidCreateStudentRequestError:
        raise InvalidUpdateStudentRequestError from None


@dataclass(frozen=True)
class DeactivateStudentInput:
    expected_version: int
    reason: str = field(repr=False)

    def payload(self) -> dict[str, str | int]:
        return {"expectedVersion": self.expected_version, "reason": self.reason}


@dataclass(frozen=True)
class ReactivateStudentInput:
    expected_version: int

    def payload(self) -> dict[str, int]:
        return {"expectedVersion": self.expected_version}


def parse_deactivate_student_body(body: str) -> DeactivateStudentInput:
    value = _parse_lifecycle_object(body)
    if (
        set(value) != {"expectedVersion", "reason"}
        or type(value["expectedVersion"]) is not int
        or value["expectedVersion"] < 1
        or not isinstance(value["reason"], str)
        or any(_is_unsafe_reason_character(character) for character in value["reason"])
    ):
        raise InvalidStudentLifecycleRequestError
    reason = value["reason"].strip()
    if not 5 <= len(reason) <= 300:
        raise InvalidStudentLifecycleRequestError
    return DeactivateStudentInput(expected_version=value["expectedVersion"], reason=reason)


def parse_reactivate_student_body(body: str) -> ReactivateStudentInput:
    value = _parse_lifecycle_object(body)
    if (
        set(value) != {"expectedVersion"}
        or type(value["expectedVersion"]) is not int
        or value["expectedVersion"] < 1
    ):
        raise InvalidStudentLifecycleRequestError
    return ReactivateStudentInput(expected_version=value["expectedVersion"])


def _parse_lifecycle_object(body: str) -> dict[str, Any]:
    if not isinstance(body, str):
        raise InvalidStudentLifecycleRequestError
    try:
        value = json.loads(body, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        raise InvalidStudentLifecycleRequestError from None
    if not isinstance(value, dict):
        raise InvalidStudentLifecycleRequestError
    return value


def _normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if (
        not normalized
        or len(normalized) > 254
        or any(character.isspace() or _is_control(character) for character in normalized)
    ):
        raise InvalidCreateStudentRequestError
    return normalized


def _validate_phone(value: str) -> str:
    if _PHONE_PATTERN.fullmatch(value) is None:
        raise InvalidCreateStudentRequestError
    return value


def _validate_birth_date(value: str, *, today: date | None) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise InvalidCreateStudentRequestError from None
    if parsed.isoformat() != value or parsed > (today or datetime.now(UTC).date()):
        raise InvalidCreateStudentRequestError
    return value


def _normalize_full_name(value: str) -> str:
    if any(_is_control(character) for character in value):
        raise InvalidCreateStudentRequestError
    normalized = " ".join(value.strip().split())
    if not 3 <= len(normalized) <= 150:
        raise InvalidCreateStudentRequestError
    return normalized


def _is_control(character: str) -> bool:
    return unicodedata.category(character).startswith("C")


def _is_unsafe_reason_character(character: str) -> bool:
    return unicodedata.category(character).startswith("C") or unicodedata.category(character) in {
        "Zl",
        "Zp",
    }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result
