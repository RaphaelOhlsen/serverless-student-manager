from typing import Protocol

MAC_ALGORITHM = "HMAC_SHA_256"
MAC_BYTES = 32


class CursorMacProtocol(Protocol):
    def generate(self, message: bytes) -> bytes: ...

    def verify(self, message: bytes, mac: bytes) -> bool: ...


class KmsClientProtocol(Protocol):
    def generate_mac(self, **kwargs: object) -> dict[str, object]: ...

    def verify_mac(self, **kwargs: object) -> dict[str, object]: ...


class KmsCursorMac:
    def __init__(self, client: KmsClientProtocol, key_id: str) -> None:
        self._client = client
        self._key_id = key_id

    def generate(self, message: bytes) -> bytes:
        response = self._client.generate_mac(
            KeyId=self._key_id,
            Message=message,
            MacAlgorithm=MAC_ALGORITHM,
        )
        mac = response.get("Mac")
        if not isinstance(mac, bytes) or len(mac) != MAC_BYTES:
            raise RuntimeError("KMS returned an invalid cursor MAC")
        return mac

    def verify(self, message: bytes, mac: bytes) -> bool:
        response = self._client.verify_mac(
            KeyId=self._key_id,
            Message=message,
            Mac=mac,
            MacAlgorithm=MAC_ALGORITHM,
        )
        valid = response.get("MacValid")
        if type(valid) is not bool:
            raise RuntimeError("KMS returned an invalid cursor verification result")
        return valid
