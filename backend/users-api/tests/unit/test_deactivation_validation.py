import json

import pytest
from users_api.errors import InvalidAdminUserWriteRequestError
from users_api.validation import parse_deactivation_body


def test_deactivation_body_accepts_only_positive_integer_version() -> None:
    assert parse_deactivation_body('{"expectedVersion":1}').expected_version == 1


@pytest.mark.parametrize("value", [True, "1", 1.0, None, 0, -1])
def test_deactivation_body_rejects_invalid_version(value: object) -> None:
    with pytest.raises(InvalidAdminUserWriteRequestError):
        parse_deactivation_body(json.dumps({"expectedVersion": value}))


@pytest.mark.parametrize("body", ["{}", '{"expectedVersion":1,"extra":1}', "null", "[]", "{"])
def test_deactivation_body_is_strict(body: str) -> None:
    with pytest.raises(InvalidAdminUserWriteRequestError):
        parse_deactivation_body(body)
