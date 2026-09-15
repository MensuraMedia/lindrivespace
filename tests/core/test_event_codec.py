from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from lindrivespace.core.event_codec import (
    decode_event,
    encode_event,
    event_to_json_line,
    parse_event_line,
)
from lindrivespace.core.events import DirDone, DirStarted, Finished, Progress, ScanError
from lindrivespace.core.fsnode import DENIED, TopFile

SRC = Path(__file__).resolve().parents[2] / "src"
CLI = SRC / "lindrivespace" / "core" / "scanner_cli.py"


# ---------------------------------------------------------------------------
# round trip for every event type
# ---------------------------------------------------------------------------


def _round_trip(event: object) -> object:
    line = event_to_json_line(event)  # type: ignore[arg-type]
    parsed = parse_event_line(line)
    assert parsed == event
    return parsed


def test_round_trip_dir_started_with_flags() -> None:
    ev = DirStarted(id=3, parent_id=1, name="Downloads", mtime=1700000000.5, flags=DENIED)
    _round_trip(ev)


def test_round_trip_dir_started_root() -> None:
    ev = DirStarted(id=0, parent_id=None, name="/home/user", mtime=1234.0)
    _round_trip(ev)


def test_round_trip_dir_done_with_top_files() -> None:
    top = (
        TopFile(alloc=4096, size=4000, mtime=1700000001.0, name="big.iso"),
        TopFile(alloc=2048, size=2000, mtime=1700000002.0, name="small.bin"),
    )
    ev = DirDone(
        id=3,
        size=6000,
        alloc=6144,
        files=2,
        dirs=0,
        mtime_max=1700000002.0,
        flags=0,
        top_files=top,
    )
    _round_trip(ev)


def test_round_trip_dir_done_without_top_files() -> None:
    ev = DirDone(id=1, size=0, alloc=0, files=0, dirs=0, mtime_max=0.0)
    _round_trip(ev)


def test_round_trip_progress() -> None:
    ev = Progress(entries=12345, alloc=987654321, current_path="/home/user/big/dir")
    _round_trip(ev)


def test_round_trip_finished_cancelled() -> None:
    ev = Finished(root_id=0, entries=42, elapsed=1.2345, cancelled=True)
    _round_trip(ev)


def test_round_trip_finished_normal() -> None:
    ev = Finished(root_id=7, entries=1000, elapsed=0.5)
    _round_trip(ev)


def test_round_trip_scan_error() -> None:
    ev = ScanError(path="/root", message="Permission denied")
    _round_trip(ev)


def test_encode_event_matches_expected_shape() -> None:
    ev = DirDone(
        id=2,
        size=10,
        alloc=20,
        files=1,
        dirs=0,
        mtime_max=5.0,
        top_files=(TopFile(alloc=20, size=10, mtime=5.0, name="f"),),
    )
    payload = encode_event(ev)
    assert payload["event"] == "DirDone"
    assert payload["top_files"] == [[20, 10, 5.0, "f"]]
    # round-trippable through json itself (no non-serializable objects, e.g. tuples/NamedTuples)
    json.dumps(payload)


def test_decode_event_unknown_type_raises() -> None:
    try:
        decode_event({"event": "NotAnEvent"})
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


# ---------------------------------------------------------------------------
# malformed input
# ---------------------------------------------------------------------------


def test_parse_event_line_blank() -> None:
    assert parse_event_line("") is None
    assert parse_event_line("   \n") is None


def test_parse_event_line_not_json() -> None:
    assert parse_event_line("not json at all {{{") is None


def test_parse_event_line_not_an_object() -> None:
    assert parse_event_line("[1, 2, 3]") is None
    assert parse_event_line('"just a string"') is None


def test_parse_event_line_missing_discriminator() -> None:
    assert parse_event_line(json.dumps({"id": 1})) is None


def test_parse_event_line_unknown_discriminator() -> None:
    assert parse_event_line(json.dumps({"event": "SomethingElse", "x": 1})) is None


def test_parse_event_line_wrong_field_type() -> None:
    assert parse_event_line(json.dumps({"event": "ScanError", "path": 5, "message": "x"})) is None


def test_parse_event_line_missing_field() -> None:
    assert parse_event_line(json.dumps({"event": "ScanError", "path": "/x"})) is None


def test_parse_event_line_malformed_top_files_entry() -> None:
    line = json.dumps(
        {
            "event": "DirDone",
            "id": 1,
            "size": 0,
            "alloc": 0,
            "files": 0,
            "dirs": 0,
            "mtime_max": 0.0,
            "flags": 0,
            "top_files": [[1, 2, 3]],  # only 3 elements, needs 4
        }
    )
    assert parse_event_line(line) is None


# ---------------------------------------------------------------------------
# real scanner_cli.py output
# ---------------------------------------------------------------------------


def _build_tree(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_text("hello world")
    (root / "sub" / "b.txt").write_text("x" * 5000)
    return root


def test_decodes_every_line_from_real_cli(tmp_path: Path) -> None:
    root = _build_tree(tmp_path)
    result = subprocess.run(
        [sys.executable, str(CLI), "--json", str(root)],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(SRC)},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line]
    assert lines, "cli produced no output"

    events = [parse_event_line(line) for line in lines]
    assert all(event is not None for event in events), "a real CLI line failed to decode"

    assert isinstance(events[0], DirStarted)
    assert events[0].parent_id is None
    assert isinstance(events[-1], Finished)
    assert events[-1].cancelled is False

    dir_done_events = [e for e in events if isinstance(e, DirDone)]
    assert dir_done_events
    root_done = next(e for e in dir_done_events if e.id == events[0].id)
    assert root_done.files == 2
    assert root_done.dirs == 1
    assert root_done.size == len("hello world") + 5000

    # Every line the real CLI wrote must decode to exactly what re-encoding
    # our own dataclass would produce -- i.e. our codec's wire format and
    # scanner_cli's are the same format, not just individually parseable.
    for line, event in zip(lines, events, strict=True):
        assert json.loads(line) == encode_event(event)  # type: ignore[arg-type]
