from __future__ import annotations

import pytest

from lindrivespace.core.units import (
    format_bytes,
    format_count,
    format_date,
    format_datetime,
    format_percent,
    parse_bytes,
)


def test_format_bytes_zero_and_sub_kilo() -> None:
    assert format_bytes(0) == "0 Bytes"
    assert format_bytes(999) == "999 Bytes"
    assert format_bytes(512) == "512 Bytes"


def test_format_bytes_decimal_boundaries() -> None:
    assert format_bytes(1000) == "1.0 KB"
    assert format_bytes(1023) == "1.0 KB"
    assert format_bytes(1024) == "1.0 KB"
    assert format_bytes(1_000_000) == "1.0 MB"
    assert format_bytes(int(1e12)) == "1.00 TB"


def test_format_bytes_binary() -> None:
    assert format_bytes(0, binary=True) == "0 Bytes"
    assert format_bytes(1023, binary=True) == "1023 Bytes"
    assert format_bytes(1024, binary=True) == "1.0 KiB"
    assert format_bytes(1024**3, binary=True) == "1.0 GiB"
    assert format_bytes(1024**4, binary=True) == "1.00 TiB"


def test_format_bytes_matches_mockup_style() -> None:
    assert format_bytes(142_800_000_000) == "142.8 GB"
    assert format_bytes(1_700_000_000_000) == "1.70 TB"
    assert format_bytes(932_600_000) == "932.6 MB"


def test_format_bytes_negative() -> None:
    assert format_bytes(-1000) == "-1.0 KB"
    assert format_bytes(-500) == "-500 Bytes"


def test_format_count() -> None:
    assert format_count(0) == "0"
    assert format_count(999) == "999"
    assert format_count(1000) == "1,000"
    assert format_count(1_234_567) == "1,234,567"


def test_format_percent() -> None:
    assert format_percent(82.34) == "82.3 %"
    assert format_percent(0) == "0.0 %"
    assert format_percent(100) == "100.0 %"


def test_format_date_and_datetime() -> None:
    # 2024-01-15 12:34:56 UTC-ish; just check shape/roundtrip via local tz.
    import datetime

    ts = datetime.datetime(2024, 1, 15, 12, 34, 56).timestamp()
    assert format_date(ts) == "2024-01-15"
    assert format_datetime(ts) == "2024-01-15 12:34"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0", 0),
        ("512", 512),
        ("1.5 GB", 1_500_000_000),
        ("1.5GB", 1_500_000_000),
        ("1KB", 1000),
        ("1 KiB", 1024),
        ("1.5 GiB", int(1.5 * 1024**3)),
        ("2 MiB", 2 * 1024**2),
        ("3 TB", 3 * 1000**4),
    ],
)
def test_parse_bytes(text: str, expected: int) -> None:
    assert parse_bytes(text) == expected


def test_parse_bytes_invalid() -> None:
    with pytest.raises(ValueError):
        parse_bytes("not a size")
    with pytest.raises(ValueError):
        parse_bytes("5 QQ")
