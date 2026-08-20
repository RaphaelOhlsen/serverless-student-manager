from uuid import UUID

import pytest

from tools.bootstrap_admin.ids import Uuid4Generator, validate_uuid4

_CANONICAL_UUID4 = "123e4567-e89b-42d3-a456-426614174000"


def test_uuid4_generator_returns_canonical_lowercase_uuid4() -> None:
    value = Uuid4Generator().new_uuid4()

    assert UUID(value).version == 4
    assert str(UUID(value)) == value
    assert value == value.lower()
    assert len(value) == 36


def test_validate_uuid4_returns_valid_value_unchanged() -> None:
    assert validate_uuid4(_CANONICAL_UUID4) == _CANONICAL_UUID4


@pytest.mark.parametrize(
    "value",
    [
        "123e4567-e89b-12d3-a456-426614174000",
        "123e4567-e89b-52d3-a456-426614174000",
        _CANONICAL_UUID4.upper(),
        _CANONICAL_UUID4.replace("-", ""),
        "not-a-uuid",
        "",
    ],
    ids=["uuid1", "uuid5", "uppercase", "without-hyphens", "arbitrary", "empty"],
)
def test_validate_uuid4_rejects_noncanonical_or_non_v4_values(value: str) -> None:
    with pytest.raises(ValueError, match="canonical UUIDv4"):
        validate_uuid4(value)
