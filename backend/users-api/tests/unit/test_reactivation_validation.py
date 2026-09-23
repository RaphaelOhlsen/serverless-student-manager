import json

import pytest
from users_api.errors import InvalidAdminUserWriteRequestError
from users_api.validation import parse_reactivation_body, validate_idempotency_key


def test_reactivation_body_accepts_only_positive_integer_version() -> None:
    parsed = parse_reactivation_body('{"expectedVersion":1}')

    assert parsed.expected_version == 1
    assert parsed.canonical_payload() == {"expectedVersion": 1}


@pytest.mark.parametrize("value", [True, "1", 1.0, None, 0, -1])
def test_reactivation_body_rejects_invalid_version(value: object) -> None:
    with pytest.raises(InvalidAdminUserWriteRequestError):
        parse_reactivation_body(json.dumps({"expectedVersion": value}))


@pytest.mark.parametrize(
    "body",
    [
        "",
        "{}",
        '{"expectedVersion":1,"extra":1}',
        '{"expectedVersion":1,"expectedVersion":2}',
        "null",
        "[]",
        "{",
    ],
)
def test_reactivation_body_is_strict(body: str) -> None:
    with pytest.raises(InvalidAdminUserWriteRequestError):
        parse_reactivation_body(body)


def test_reactivation_body_rejects_missing_value() -> None:
    with pytest.raises(InvalidAdminUserWriteRequestError):
        parse_reactivation_body(None)  # type: ignore[arg-type]


def test_reactivation_idempotency_key_must_be_canonical_uuid() -> None:
    key = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

    assert validate_idempotency_key(key) == key
    for invalid in (key.upper(), "not-a-uuid", "", None, 1):
        with pytest.raises(InvalidAdminUserWriteRequestError):
            validate_idempotency_key(invalid)
