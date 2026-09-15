"""Human-readable formatting helpers: byte sizes, counts, percentages, dates.

Pure stdlib, no GTK. Shared by the tree model, the overview dashboard and
``scanner_cli`` for its plain-text summary.
"""

from __future__ import annotations

import datetime
import re

_DECIMAL_UNITS: tuple[str, ...] = ("Bytes", "KB", "MB", "GB", "TB", "PB", "EB")
_BINARY_UNITS: tuple[str, ...] = ("Bytes", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB")

_PARSE_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*([A-Za-z]*)\s*$")

_DECIMAL_SUFFIXES: dict[str, int] = {
    "b": 1,
    "bytes": 1,
    "kb": 1000,
    "mb": 1000**2,
    "gb": 1000**3,
    "tb": 1000**4,
    "pb": 1000**5,
    "eb": 1000**6,
}

_BINARY_SUFFIXES: dict[str, int] = {
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "tib": 1024**4,
    "pib": 1024**5,
    "eib": 1024**6,
}


def format_bytes(n: int, binary: bool = False, precision: int = 1) -> str:
    """Render a byte count with a scaled unit.

    ``0`` renders as ``"0 Bytes"``; values under one kilo(bi)byte render as an
    exact byte count ("512 Bytes"). TB/TiB and above always use 2 decimals,
    regardless of ``precision``, to match the mockups.
    """
    if n == 0:
        return "0 Bytes"
    base = 1024 if binary else 1000
    units = _BINARY_UNITS if binary else _DECIMAL_UNITS
    negative = n < 0
    value = float(-n if negative else n)
    if value < base:
        text = f"{int(value)} {units[0]}"
        return f"-{text}" if negative else text
    idx = 0
    while value >= base and idx < len(units) - 1:
        value /= base
        idx += 1
    prec = 2 if idx >= 4 else precision
    text = f"{value:.{prec}f} {units[idx]}"
    return f"-{text}" if negative else text


def format_count(n: int) -> str:
    """Format an integer with en-US thousands separators, e.g. ``12,345``."""
    return f"{n:,}"


def format_percent(p: float) -> str:
    """Format a percentage with one decimal, e.g. ``82.3 %``."""
    return f"{p:.1f} %"


def format_date(ts: float) -> str:
    """Format a unix timestamp as a local ``YYYY-MM-DD`` date."""
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def format_datetime(ts: float) -> str:
    """Format a unix timestamp as a local ``YYYY-MM-DD HH:MM`` datetime."""
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def parse_bytes(text: str) -> int:
    """Parse a human byte string such as ``"1.5 GB"`` or ``"512"`` into an int.

    Accepts decimal (kB/MB/GB/...) and binary (KiB/MiB/GiB/...) suffixes,
    case-insensitively, with or without a space. Bare numbers are bytes.
    """
    match = _PARSE_RE.match(text)
    if not match:
        raise ValueError(f"cannot parse byte value: {text!r}")
    number_part, unit_part = match.groups()
    number = float(number_part)
    unit = unit_part.strip().lower()
    if not unit:
        return int(number)
    if unit in _BINARY_SUFFIXES:
        return int(number * _BINARY_SUFFIXES[unit])
    if unit in _DECIMAL_SUFFIXES:
        return int(number * _DECIMAL_SUFFIXES[unit])
    raise ValueError(f"unknown byte unit: {unit_part!r}")
