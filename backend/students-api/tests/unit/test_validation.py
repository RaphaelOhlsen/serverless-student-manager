from datetime import date

import pytest
from students_api.errors import InvalidCreateStudentRequestError
from students_api.validation import parse_create_student_body

TODAY = date(2026, 9, 4)
VALID = (
    '{"fullName":"  Maria   da Silva  ","registrationNumber":" mat-0001 ",'
    '"studentEmail":" Maria@Example.COM ","phone":"+5527999999999",'
    '"birthDate":"2010-05-21"}'
)


def test_normalizes_valid_create_student_body() -> None:
    result = parse_create_student_body(VALID, today=TODAY)

    assert result.full_name == "Maria da Silva"
    assert result.normalized_name == "maria da silva"
    assert result.registration_number == "MAT-0001"
    assert result.student_email == "maria@example.com"
    assert result.phone == "+5527999999999"
    assert result.birth_date == "2010-05-21"


@pytest.mark.parametrize(
    "body",
    [
        "not-json",
        "[]",
        '{"fullName":"Maria"}',
        VALID[:-1] + ',"extra":true}',
        VALID.replace('"  Maria   da Silva  "', "42"),
        VALID.replace('"fullName"', '"fullName":"duplicate","fullName"', 1),
    ],
)
def test_rejects_invalid_shape(body: str) -> None:
    with pytest.raises(InvalidCreateStudentRequestError):
        parse_create_student_body(body, today=TODAY)


@pytest.mark.parametrize("value", ["ABC", "AB_C", "ABCDEFGHIJKLMNOPQRSTU"])
def test_rejects_invalid_registration_number(value: str) -> None:
    with pytest.raises(InvalidCreateStudentRequestError):
        parse_create_student_body(VALID.replace(" mat-0001 ", value), today=TODAY)


@pytest.mark.parametrize("value", ["", "bad email@example.com", "bad\n@example.com"])
def test_rejects_invalid_email_rules(value: str) -> None:
    with pytest.raises(InvalidCreateStudentRequestError):
        parse_create_student_body(VALID.replace(" Maria@Example.COM ", value), today=TODAY)


@pytest.mark.parametrize("value", ["5527999999999", "+012345678", "+1234567", "+1234567890123456"])
def test_rejects_non_e164_phone(value: str) -> None:
    with pytest.raises(InvalidCreateStudentRequestError):
        parse_create_student_body(VALID.replace("+5527999999999", value), today=TODAY)


@pytest.mark.parametrize("value", ["A", "Maria\nSilva", "   "])
def test_rejects_invalid_full_name(value: str) -> None:
    with pytest.raises(InvalidCreateStudentRequestError):
        parse_create_student_body(VALID.replace("  Maria   da Silva  ", value), today=TODAY)


@pytest.mark.parametrize(
    "value", ["2025-02-29", "2026-09-05", "04/09/2010", "2010-05-21T00:00:00Z"]
)
def test_rejects_invalid_or_future_birth_date(value: str) -> None:
    with pytest.raises(InvalidCreateStudentRequestError):
        parse_create_student_body(VALID.replace("2010-05-21", value), today=TODAY)
