"""NDJSON codec for :mod:`lindrivespace.core.events` (stdlib only, no third-party imports).

This is the wire format between the scanner and any out-of-process consumer of
its events: ``scanner_cli.py --json`` writes one JSON object per line (see its
``_event_to_json`` helper), and both the in-process test-suite and
``services.privilege.PrivilegedScan`` (WP11, reading the pkexec helper's
stdout) need to turn those lines back into the frozen dataclasses from
``core/events.py``.

``encode_event``/``event_to_json_line`` intentionally duplicate
``scanner_cli._event_to_json``'s exact logic (``dataclasses.asdict`` plus a
``top_files`` tuple-of-tuples -> list-of-lists conversion for ``DirDone``,
plus an ``"event"`` discriminator key) rather than importing that private
helper, so this module has no dependency on scanner_cli's internals -- only on
the wire format it produces. ``tests/core/test_event_codec.py`` proves the two
agree by running the real CLI in a subprocess and decoding its actual output.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from lindrivespace.core.events import DirDone, DirStarted, Finished, Progress, ScanError, ScanEvent
from lindrivespace.core.fsnode import TopFile

_EVENT_NAMES = {
    "DirStarted": DirStarted,
    "DirDone": DirDone,
    "Progress": Progress,
    "Finished": Finished,
    "ScanError": ScanError,
}


def encode_event(ev: ScanEvent) -> dict[str, Any]:
    """Turn one event into the plain-dict wire format (matches ``scanner_cli.py``)."""
    payload: dict[str, Any] = dataclasses.asdict(ev)
    if isinstance(ev, DirDone):
        payload["top_files"] = [list(tf) for tf in ev.top_files]
    payload["event"] = type(ev).__name__
    return payload


def event_to_json_line(ev: ScanEvent) -> str:
    """Encode one event as a single JSON line (no trailing newline)."""
    return json.dumps(encode_event(ev))


def _as_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"expected int for {field!r}, got {value!r}")
    return value


def _as_opt_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    return _as_int(value, field)


def _as_float(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"expected float for {field!r}, got {value!r}")
    return float(value)


def _as_str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"expected str for {field!r}, got {value!r}")
    return value


def _as_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"expected bool for {field!r}, got {value!r}")
    return value


def _decode_top_file(item: object) -> TopFile:
    if not isinstance(item, (list, tuple)) or len(item) != 4:
        raise ValueError(f"malformed top_files entry: {item!r}")
    alloc, size, mtime, name = item
    return TopFile(
        alloc=_as_int(alloc, "top_files.alloc"),
        size=_as_int(size, "top_files.size"),
        mtime=_as_float(mtime, "top_files.mtime"),
        name=_as_str(name, "top_files.name"),
    )


def _decode_top_files(value: object) -> tuple[TopFile, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"expected list for 'top_files', got {value!r}")
    return tuple(_decode_top_file(item) for item in value)


def decode_event(obj: dict[str, Any]) -> ScanEvent:
    """Reconstruct the dataclass a wire-format dict was encoded from.

    Raises ``ValueError``/``KeyError`` on malformed input; use
    :func:`parse_event_line` when you want ``None`` instead of an exception.
    """
    kind = obj.get("event")
    if kind not in _EVENT_NAMES:
        raise ValueError(f"unknown event type: {kind!r}")

    if kind == "DirStarted":
        return DirStarted(
            id=_as_int(obj["id"], "id"),
            parent_id=_as_opt_int(obj["parent_id"], "parent_id"),
            name=_as_str(obj["name"], "name"),
            mtime=_as_float(obj["mtime"], "mtime"),
            flags=_as_int(obj.get("flags", 0), "flags"),
        )
    if kind == "DirDone":
        return DirDone(
            id=_as_int(obj["id"], "id"),
            size=_as_int(obj["size"], "size"),
            alloc=_as_int(obj["alloc"], "alloc"),
            files=_as_int(obj["files"], "files"),
            dirs=_as_int(obj["dirs"], "dirs"),
            mtime_max=_as_float(obj["mtime_max"], "mtime_max"),
            flags=_as_int(obj.get("flags", 0), "flags"),
            top_files=_decode_top_files(obj.get("top_files")),
        )
    if kind == "Progress":
        return Progress(
            entries=_as_int(obj["entries"], "entries"),
            alloc=_as_int(obj["alloc"], "alloc"),
            current_path=_as_str(obj["current_path"], "current_path"),
        )
    if kind == "Finished":
        return Finished(
            root_id=_as_int(obj["root_id"], "root_id"),
            entries=_as_int(obj["entries"], "entries"),
            elapsed=_as_float(obj["elapsed"], "elapsed"),
            cancelled=_as_bool(obj.get("cancelled", False), "cancelled"),
        )
    # kind == "ScanError"
    return ScanError(
        path=_as_str(obj["path"], "path"),
        message=_as_str(obj["message"], "message"),
    )


def parse_event_line(line: str) -> ScanEvent | None:
    """Parse one NDJSON line into an event, or ``None`` if it is malformed.

    Never raises: any JSON error, non-object payload, unknown/missing
    ``"event"`` discriminator, or field type mismatch yields ``None`` so a
    reader thread can skip a corrupt line (e.g. stray stderr text merged into
    stdout) without dying.
    """
    stripped = line.strip()
    if not stripped:
        return None
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    try:
        return decode_event(obj)
    except (KeyError, ValueError, TypeError):
        return None
