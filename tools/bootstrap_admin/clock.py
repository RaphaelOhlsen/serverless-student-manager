from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def format_utc_rfc3339_millis(value: datetime) -> str:
    utc_value = _as_utc(value)
    return utc_value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def to_epoch_seconds(value: datetime) -> int:
    return int(_as_utc(value).timestamp())


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")

    return value.astimezone(UTC)
