import json

import pytest
from students_api.errors import InvalidStudentLifecycleRequestError
from students_api.validation import (
    DeactivateStudentInput,
    parse_deactivate_student_body,
    parse_reactivate_student_body,
)


@pytest.mark.parametrize("version", [1, 7])
def test_deactivate_accepts_versions_and_trims_reason(version: int) -> None:
    result = parse_deactivate_student_body(
        json.dumps({"expectedVersion": version, "reason": "  Correção administrativa  "})
    )

    assert result.payload() == {
        "expectedVersion": version,
        "reason": "Correção administrativa",
    }


@pytest.mark.parametrize("reason", ["á" * 5, "ç" * 300, "Revisão válida em português"])
def test_deactivate_accepts_reason_boundaries_and_unicode(reason: str) -> None:
    result = parse_deactivate_student_body(json.dumps({"expectedVersion": 1, "reason": reason}))

    assert result.reason == reason


def test_deactivate_preserves_internal_whitespace_and_hides_reason_from_repr() -> None:
    result = parse_deactivate_student_body(
        json.dumps({"expectedVersion": 1, "reason": "  Motivo   preservado  "})
    )

    assert result.reason == "Motivo   preservado"
    assert "Motivo" not in repr(result)


@pytest.mark.parametrize("version", [None, 0, -1, True, False, "1", 1.0, [], {}])
def test_deactivate_rejects_invalid_version(version: object) -> None:
    with pytest.raises(InvalidStudentLifecycleRequestError):
        parse_deactivate_student_body(
            json.dumps({"expectedVersion": version, "reason": "Motivo válido"})
        )


@pytest.mark.parametrize(
    "reason",
    [None, True, 42, [], {}, "", "   ", "abcd", "a" * 301],
)
def test_deactivate_rejects_invalid_reason(reason: object) -> None:
    with pytest.raises(InvalidStudentLifecycleRequestError):
        parse_deactivate_student_body(json.dumps({"expectedVersion": 1, "reason": reason}))


@pytest.mark.parametrize(
    "reason",
    ["Motivo\ninválido", "Motivo\tinválido", "Motivo\u200binválido", "Motivo\u2028inválido"],
)
def test_deactivate_rejects_control_and_line_characters(reason: str) -> None:
    with pytest.raises(InvalidStudentLifecycleRequestError):
        parse_deactivate_student_body(json.dumps({"expectedVersion": 1, "reason": reason}))


@pytest.mark.parametrize(
    "body",
    [
        "",
        "bad",
        "null",
        "[]",
        "true",
        "{}",
        '{"expectedVersion":1}',
        '{"reason":"Motivo válido"}',
        '{"expectedVersion":1,"reason":"Motivo válido","extra":true}',
        '{"expectedVersion":1,"expectedVersion":2,"reason":"Motivo válido"}',
        '{"expectedVersion":1,"reason":"Primeiro","reason":"Segundo"}',
    ],
)
def test_deactivate_rejects_invalid_shape_extras_and_duplicates(body: str) -> None:
    with pytest.raises(InvalidStudentLifecycleRequestError):
        parse_deactivate_student_body(body)


@pytest.mark.parametrize("version", [1, 9])
def test_reactivate_accepts_positive_integer_version(version: int) -> None:
    result = parse_reactivate_student_body(json.dumps({"expectedVersion": version}))

    assert result.payload() == {"expectedVersion": version}


@pytest.mark.parametrize("version", [None, 0, -1, True, False, "1", 1.0, [], {}])
def test_reactivate_rejects_invalid_version(version: object) -> None:
    with pytest.raises(InvalidStudentLifecycleRequestError):
        parse_reactivate_student_body(json.dumps({"expectedVersion": version}))


@pytest.mark.parametrize(
    "body",
    [
        "",
        "bad",
        "null",
        "[]",
        "{}",
        '{"expectedVersion":1,"extra":true}',
        '{"expectedVersion":1,"expectedVersion":2}',
    ],
)
def test_reactivate_rejects_invalid_shape_extras_and_duplicates(body: str) -> None:
    with pytest.raises(InvalidStudentLifecycleRequestError):
        parse_reactivate_student_body(body)


def test_non_string_body_is_rejected_without_leaking_content() -> None:
    with pytest.raises(InvalidStudentLifecycleRequestError) as error:
        parse_deactivate_student_body(None)  # type: ignore[arg-type]

    assert error.value.args == ()


def test_request_error_does_not_include_reason() -> None:
    sensitive_synthetic_reason = "synthetic-secret-reason"

    with pytest.raises(InvalidStudentLifecycleRequestError) as error:
        parse_deactivate_student_body(
            json.dumps({"expectedVersion": 1, "reason": sensitive_synthetic_reason, "extra": 1})
        )

    assert sensitive_synthetic_reason not in str(error.value)
    assert sensitive_synthetic_reason not in repr(error.value)


def test_deactivate_input_type_keeps_reason_out_of_repr() -> None:
    value = DeactivateStudentInput(expected_version=1, reason="synthetic-reason")

    assert repr(value) == "DeactivateStudentInput(expected_version=1)"
