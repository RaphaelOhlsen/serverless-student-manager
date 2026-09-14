import json

import pytest
from users_api.errors import InvalidAdminUserWriteRequestError
from users_api.validation import (
    normalize_admin_user_email,
    normalize_admin_user_full_name,
    parse_create_user_body,
    parse_resend_invitation_body,
    parse_role_change_body,
    validate_idempotency_key,
)


def create_body(**overrides: object) -> str:
    value: dict[str, object] = {
        "fullName": "Admin Example",
        "email": "admin@example.test",
        "role": "ADMIN",
    }
    value.update(overrides)
    return json.dumps(value)


def test_create_validation_normalizes_unicode_whitespace_and_email() -> None:
    value = parse_create_user_body(
        create_body(fullName="  Ａna   Silva  ", email=" ADMIN@EXAMPLE.TEST ")
    )
    assert value.full_name == "Ana Silva"
    assert value.normalized_name == "ana silva"
    assert value.email == "admin@example.test"
    assert value.role == "ADMIN"


@pytest.mark.parametrize("length", [2, 150])
def test_full_name_accepts_boundaries(length: int) -> None:
    assert normalize_admin_user_full_name("A" * length) == "A" * length


@pytest.mark.parametrize("value", ["A", "A" * 151, "A\x00B", " \t "])
def test_full_name_rejects_invalid_values(value: str) -> None:
    with pytest.raises(InvalidAdminUserWriteRequestError):
        normalize_admin_user_full_name(value)


def test_email_accepts_254_characters_and_normalizes() -> None:
    email = "A" * 241 + "@EXAMPLE.TEST"
    assert len(email) == 254
    assert normalize_admin_user_email(f" {email} ") == email.lower()


@pytest.mark.parametrize(
    "value",
    ["A" * 242 + "@example.test", "missing-at.example.test", "a@invalid", "a @example.test"],
)
def test_email_rejects_invalid_values(value: str) -> None:
    with pytest.raises(InvalidAdminUserWriteRequestError):
        normalize_admin_user_email(value)


@pytest.mark.parametrize("role", ["OWNER", "admin", "", None, True])
def test_create_rejects_invalid_role(role: object) -> None:
    with pytest.raises(InvalidAdminUserWriteRequestError):
        parse_create_user_body(create_body(role=role))


@pytest.mark.parametrize(
    "body",
    [
        "{}",
        create_body(extra="value"),
        '{"fullName":"One","fullName":"Two","email":"a@example.test","role":"ADMIN"}',
        "[]",
    ],
)
def test_create_body_is_strict(body: str) -> None:
    with pytest.raises(InvalidAdminUserWriteRequestError):
        parse_create_user_body(body)


def test_resend_accepts_positive_integer() -> None:
    assert parse_resend_invitation_body('{"expectedVersion":1}').expected_version == 1


@pytest.mark.parametrize("value", [True, "1", 1.0, None, 0])
def test_resend_rejects_invalid_version(value: object) -> None:
    with pytest.raises(InvalidAdminUserWriteRequestError):
        parse_resend_invitation_body(json.dumps({"expectedVersion": value}))


@pytest.mark.parametrize(
    "body",
    ["{}", '{"expectedVersion":1,"extra":true}', '{"expectedVersion":1,"expectedVersion":2}'],
)
def test_resend_body_is_strict(body: str) -> None:
    with pytest.raises(InvalidAdminUserWriteRequestError):
        parse_resend_invitation_body(body)


def test_idempotency_key_must_be_canonical_uuid() -> None:
    key = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert validate_idempotency_key(key) == key
    for invalid in (key.upper(), "not-a-uuid", None):
        with pytest.raises(InvalidAdminUserWriteRequestError):
            validate_idempotency_key(invalid)


@pytest.mark.parametrize("role", ["ADMIN", "OPERATOR"])
def test_role_change_accepts_strict_contract(role: str) -> None:
    parsed = parse_role_change_body(json.dumps({"expectedVersion": 1, "role": role}))
    assert parsed.expected_version == 1
    assert parsed.role == role


@pytest.mark.parametrize("value", [True, "1", 1.0, None, 0, -1])
def test_role_change_rejects_invalid_expected_version(value: object) -> None:
    with pytest.raises(InvalidAdminUserWriteRequestError):
        parse_role_change_body(json.dumps({"expectedVersion": value, "role": "ADMIN"}))


@pytest.mark.parametrize(
    "body",
    [
        "{}",
        '{"expectedVersion":1,"role":"OWNER"}',
        '{"expectedVersion":1,"role":null}',
        '{"expectedVersion":1,"role":"ADMIN","extra":true}',
        '{"expectedVersion":1,"expectedVersion":2,"role":"ADMIN"}',
    ],
)
def test_role_change_body_is_strict(body: str) -> None:
    with pytest.raises(InvalidAdminUserWriteRequestError):
        parse_role_change_body(body)
