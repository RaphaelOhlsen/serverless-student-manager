from typing import Protocol
from uuid import UUID, uuid4


class IdGenerator(Protocol):
    def new_uuid4(self) -> str: ...


class Uuid4Generator:
    def new_uuid4(self) -> str:
        return str(uuid4())


def validate_uuid4(value: str) -> str:
    try:
        parsed = UUID(value)
    except ValueError:
        raise ValueError("value must be a canonical UUIDv4") from None

    if parsed.version != 4 or str(parsed) != value or len(value) != 36:
        raise ValueError("value must be a canonical UUIDv4")

    return value
