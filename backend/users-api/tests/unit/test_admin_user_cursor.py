import base64

import pytest
from users_api.cursor import UserCursorPosition, decode_cursor, encode_cursor
from users_api.errors import InvalidAdminUserListRequestError


def test_cursor_round_trip_is_opaque_and_bound_to_query() -> None:
    position = UserCursorPosition(user_id="user-1", normalized_name="ana silva")
    cursor = encode_cursor(role="ADMIN", status="ACTIVE", name_prefix="ana", position=position)

    assert "user-1" not in cursor
    assert decode_cursor(cursor, role="ADMIN", status="ACTIVE", name_prefix="ana") == position

    with pytest.raises(InvalidAdminUserListRequestError):
        decode_cursor(cursor, role="OPERATOR", status="ACTIVE", name_prefix="ana")


@pytest.mark.parametrize("cursor", ["", "%%%", "abcd=", "e30"])
def test_rejects_malformed_cursor(cursor: str) -> None:
    with pytest.raises(InvalidAdminUserListRequestError):
        decode_cursor(cursor, role="ALL", status="ALL", name_prefix=None)


def test_rejects_duplicate_json_fields() -> None:
    raw = b'{"v":1,"v":1,"role":"ALL"}'
    cursor = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    with pytest.raises(InvalidAdminUserListRequestError):
        decode_cursor(cursor, role="ALL", status="ALL", name_prefix=None)
