import json
from datetime import date

import pytest
from students_api.errors import InvalidUpdateStudentRequestError
from students_api.validation import parse_update_student_body

TODAY = date(2026, 9, 10)
FIELDS = {
    "fullName": "  Áluno   Silva  ",
    "studentEmail": " USER@EXAMPLE.COM ",
    "phone": "+5527999999999",
    "birthDate": "2000-02-29",
}
NORMALIZED = {**FIELDS, "fullName": "Áluno Silva", "studentEmail": "user@example.com"}


@pytest.mark.parametrize("field", FIELDS)
def test_single_field_preserves_omissions(field: str) -> None:
    result = parse_update_student_body(
        json.dumps({"expectedVersion": 3, field: FIELDS[field]}), today=TODAY
    )
    assert result.payload() == {"expectedVersion": 3, field: NORMALIZED[field]}
    assert result.normalized_name == ("áluno silva" if field == "fullName" else None)


def test_multiple_fields_are_normalized() -> None:
    result = parse_update_student_body(json.dumps({"expectedVersion": 1, **FIELDS}), today=TODAY)
    assert result.payload() == {"expectedVersion": 1, **NORMALIZED}


@pytest.mark.parametrize("version", [None, 0, -1, True, False, "1", 1.0, [], {}])
def test_invalid_version(version: object) -> None:
    with pytest.raises(InvalidUpdateStudentRequestError):
        parse_update_student_body(
            json.dumps({"expectedVersion": version, "phone": FIELDS["phone"]})
        )


@pytest.mark.parametrize(
    "body",
    [
        '{"fullName":"Aluno"}',
        '{"expectedVersion":1}',
        "{}",
        "[]",
        "null",
        "true",
        "1",
        "bad",
        '{"expectedVersion":1,"expectedVersion":2,"fullName":"Aluno"}',
        '{"expectedVersion":1,"fullName":"Aluno","fullName":"Outro"}',
    ],
)
def test_invalid_shape_and_duplicate_keys(body: str) -> None:
    with pytest.raises(InvalidUpdateStudentRequestError):
        parse_update_student_body(body)


@pytest.mark.parametrize(
    "extra",
    [
        "extra",
        "studentId",
        "registrationNumber",
        "status",
        "version",
        "createdAt",
        "createdBy",
        "updatedAt",
        "updatedBy",
    ],
)
def test_rejects_extra_fields(extra: str) -> None:
    with pytest.raises(InvalidUpdateStudentRequestError):
        parse_update_student_body(json.dumps({"expectedVersion": 1, **FIELDS, extra: "value"}))


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("value", [None, True, 42, [], {}])
def test_rejects_non_string_field(field: str, value: object) -> None:
    with pytest.raises(InvalidUpdateStudentRequestError):
        parse_update_student_body(json.dumps({"expectedVersion": 1, field: value}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("fullName", "ab"),
        ("fullName", "a" * 151),
        ("fullName", "   "),
        ("fullName", "Ana\nSilva"),
        ("fullName", "Ana\u200bSilva"),
        ("studentEmail", ""),
        ("studentEmail", "  "),
        ("studentEmail", "a" * 255),
        ("studentEmail", "a b"),
        ("studentEmail", "a\u200bb"),
        ("phone", "+012345678"),
        ("phone", "+1234567"),
        ("phone", "+1234567890123456"),
        ("phone", " +5527999999999 "),
        ("birthDate", "2026-09-11"),
        ("birthDate", "2025-02-29"),
        ("birthDate", "20000229"),
        ("birthDate", "29/02/2000"),
    ],
)
def test_rejects_invalid_values(field: str, value: str) -> None:
    with pytest.raises(InvalidUpdateStudentRequestError):
        parse_update_student_body(json.dumps({"expectedVersion": 1, field: value}), today=TODAY)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("fullName", "Ana"),
        ("fullName", "a" * 150),
        ("studentEmail", "a" * 254),
        ("phone", "+12345678"),
        ("phone", "+123456789012345"),
        ("birthDate", "2026-09-10"),
    ],
)
def test_accepts_boundaries(field: str, value: str) -> None:
    assert parse_update_student_body(
        json.dumps({"expectedVersion": 1, field: value}), today=TODAY
    ).payload() == {"expectedVersion": 1, field: value}
