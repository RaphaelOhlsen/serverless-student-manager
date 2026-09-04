import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from students_api.cursor import normalize_name
from students_api.errors import InvalidCreateStudentRequestError

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
    student_email = value["studentEmail"].strip().lower()
    phone = value["phone"]
    birth_date = value["birthDate"]

    if _REGISTRATION_PATTERN.fullmatch(registration_number) is None:
        raise InvalidCreateStudentRequestError
    if (
        not student_email
        or len(student_email) > 254
        or any(character.isspace() or _is_control(character) for character in student_email)
    ):
        raise InvalidCreateStudentRequestError
    if _PHONE_PATTERN.fullmatch(phone) is None:
        raise InvalidCreateStudentRequestError

    try:
        parsed_birth_date = date.fromisoformat(birth_date)
    except ValueError:
        raise InvalidCreateStudentRequestError from None
    if parsed_birth_date.isoformat() != birth_date:
        raise InvalidCreateStudentRequestError
    current_date = today or datetime.now(UTC).date()
    if parsed_birth_date > current_date:
        raise InvalidCreateStudentRequestError

    return CreateStudentInput(
        full_name=full_name,
        normalized_name=normalize_name(full_name),
        registration_number=registration_number,
        student_email=student_email,
        phone=phone,
        birth_date=birth_date,
    )


def _normalize_full_name(value: str) -> str:
    if any(_is_control(character) for character in value):
        raise InvalidCreateStudentRequestError
    normalized = " ".join(value.strip().split())
    if not 3 <= len(normalized) <= 150:
        raise InvalidCreateStudentRequestError
    return normalized


def _is_control(character: str) -> bool:
    return unicodedata.category(character).startswith("C")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result
