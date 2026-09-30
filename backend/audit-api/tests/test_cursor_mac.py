from typing import Any

import pytest
from audit_api.cursor_mac import MAC_ALGORITHM, KmsCursorMac


class RecordingKmsClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def generate_mac(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("generate", kwargs))
        return {"Mac": b"m" * 32}

    def verify_mac(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("verify", kwargs))
        return {"MacValid": True}


def test_kms_cursor_mac_uses_hmac_sha_256_and_configured_key() -> None:
    client = RecordingKmsClient()
    cursor_mac = KmsCursorMac(client, "key-arn")

    assert cursor_mac.generate(b"payload") == b"m" * 32
    assert cursor_mac.verify(b"payload", b"m" * 32) is True
    assert client.calls == [
        (
            "generate",
            {"KeyId": "key-arn", "Message": b"payload", "MacAlgorithm": MAC_ALGORITHM},
        ),
        (
            "verify",
            {
                "KeyId": "key-arn",
                "Message": b"payload",
                "Mac": b"m" * 32,
                "MacAlgorithm": MAC_ALGORITHM,
            },
        ),
    ]
    assert MAC_ALGORITHM == "HMAC_SHA_256"


@pytest.mark.parametrize("response", [{}, {"Mac": "not-bytes"}, {"Mac": b"short"}])
def test_generate_rejects_invalid_kms_response(response: dict[str, object]) -> None:
    client: Any = RecordingKmsClient()
    client.generate_mac = lambda **kwargs: response

    with pytest.raises(RuntimeError, match="invalid cursor MAC"):
        KmsCursorMac(client, "key-arn").generate(b"payload")


@pytest.mark.parametrize("response", [{}, {"MacValid": "true"}])
def test_verify_rejects_invalid_kms_response(response: dict[str, object]) -> None:
    client: Any = RecordingKmsClient()
    client.verify_mac = lambda **kwargs: response

    with pytest.raises(RuntimeError, match="invalid cursor verification result"):
        KmsCursorMac(client, "key-arn").verify(b"payload", b"m" * 32)


def test_kms_operational_error_propagates() -> None:
    client: Any = RecordingKmsClient()

    def fail(**kwargs: object) -> dict[str, object]:
        raise RuntimeError("kms access denied internal detail")

    client.verify_mac = fail

    with pytest.raises(RuntimeError, match="kms access denied"):
        KmsCursorMac(client, "key-arn").verify(b"payload", b"m" * 32)
