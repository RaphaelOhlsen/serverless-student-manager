from datetime import UTC, datetime, timedelta, timezone

import pytest

from tools.bootstrap_admin.clock import (
    SystemClock,
    format_utc_rfc3339_millis,
    to_epoch_seconds,
)


def test_system_clock_returns_timezone_aware_utc_datetime() -> None:
    value = SystemClock().now()

    assert value.tzinfo is not None
    assert value.utcoffset() == timedelta(0)


def test_formatter_uses_exact_millisecond_precision_and_z_suffix() -> None:
    value = datetime(2026, 8, 20, 13, 45, 12, 347891, tzinfo=UTC)

    assert format_utc_rfc3339_millis(value) == "2026-08-20T13:45:12.347Z"


def test_formatter_converts_non_utc_offset_to_utc() -> None:
    value = datetime(
        2026,
        8,
        20,
        10,
        45,
        12,
        347891,
        tzinfo=timezone(timedelta(hours=-3)),
    )

    assert format_utc_rfc3339_millis(value) == "2026-08-20T13:45:12.347Z"


def test_formatter_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        format_utc_rfc3339_millis(datetime(2026, 8, 20, 13, 45, 12))


def test_epoch_converter_returns_known_utc_epoch_seconds() -> None:
    value = datetime(1970, 1, 1, tzinfo=UTC)

    assert to_epoch_seconds(value) == 0


def test_epoch_converter_accepts_equivalent_non_utc_datetime() -> None:
    value = datetime(
        1969,
        12,
        31,
        21,
        tzinfo=timezone(timedelta(hours=-3)),
    )

    assert to_epoch_seconds(value) == 0


def test_epoch_converter_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        to_epoch_seconds(datetime(1970, 1, 1))
