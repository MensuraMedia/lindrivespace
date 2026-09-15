#!/usr/bin/env python3
"""Stdlib-only CLI wrapper around :class:`core.scanner.Scanner`.

This is the process ``pkexec`` launches to run a privileged scan (see
``docs/CONCEPT-AND-TECHNICAL-DESIGN.md`` §16 errata: ``pkexec
/usr/libexec/lindrivespace/lindrivespace-scan-helper --json <path>``). It must
run both as a module (``python -m lindrivespace.core.scanner_cli``) and as a
standalone script copied or symlinked anywhere (``python
/abs/path/scanner_cli.py``), with no GTK, no third-party dependencies, and
even with an empty ``PYTHONPATH`` — hence the ``sys.path`` bootstrap below.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import signal
import sys
import threading
from types import FrameType

if __package__ in (None, ""):
    # Running as a plain script: make ``lindrivespace`` importable by
    # inserting the ``src`` directory (three parents up from this file:
    # core/ -> lindrivespace/ -> src/) at the front of sys.path.
    try:
        import lindrivespace  # noqa: F401
    except ImportError:
        _src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if _src not in sys.path:
            sys.path.insert(0, _src)

from lindrivespace.core import units
from lindrivespace.core.events import DirDone, Finished, ScanError, ScanEvent
from lindrivespace.core.options import DEFAULT_EXCLUDES, ScanOptions
from lindrivespace.core.scanner import Scanner


def _event_to_json(event: ScanEvent) -> dict[str, object]:
    payload: dict[str, object] = dataclasses.asdict(event)
    if isinstance(event, DirDone):
        payload["top_files"] = [list(tf) for tf in event.top_files]
    payload["event"] = type(event).__name__
    return payload


def _run_json(root: str, options: ScanOptions, cancel: threading.Event) -> int:
    scanner = Scanner()
    out = sys.stdout
    cancelled_by_error = False

    def emit(event: ScanEvent) -> None:
        out.write(json.dumps(_event_to_json(event)))
        out.write("\n")
        if isinstance(event, Finished):
            out.flush()

    try:
        scanner.scan(root, options, emit, cancel=cancel)
    except OSError as exc:
        emit(ScanError(path=root, message=str(exc)))
        emit(Finished(root_id=0, entries=0, elapsed=0.0, cancelled=False))
        cancelled_by_error = True
    return 1 if cancelled_by_error else 0


def _run_text(root: str, options: ScanOptions, cancel: threading.Event) -> int:
    scanner = Scanner()
    events: list[ScanEvent] = []
    try:
        root_node = scanner.scan(root, options, events.append, cancel=cancel)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    finished = next((e for e in events if isinstance(e, Finished)), None)
    print(f"{root_node.path()}")
    print(
        f"  {units.format_bytes(root_node.alloc)} allocated, "
        f"{units.format_bytes(root_node.size)} apparent, "
        f"{units.format_count(root_node.files)} files, "
        f"{units.format_count(root_node.dirs)} dirs"
    )
    for child in root_node.children[:20]:
        print(f"  {units.format_bytes(child.alloc):>12}  {child.name}")
    if finished is not None and finished.cancelled:
        print("(cancelled)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scanner_cli.py",
        description="Scan a directory tree and report sizes (stdlib only).",
    )
    parser.add_argument("path", help="directory to scan")
    parser.add_argument("--json", action="store_true", help="emit one JSON event per line")
    parser.add_argument(
        "--cross-mounts", action="store_true", help="descend into other filesystems"
    )
    parser.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="accepted for forward compatibility; v1 never follows symlinks",
    )
    parser.add_argument(
        "--no-hardlink-dedupe",
        action="store_true",
        help="count every hard-linked file, not just the first",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATH",
        help="path to prune (repeatable); replaces the built-in default excludes",
    )
    parser.add_argument(
        "--top-files", type=int, default=50, metavar="N", help="largest files kept per directory"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not os.path.isdir(args.path):
        print(f"error: not a directory: {args.path}", file=sys.stderr)
        return 1

    options = ScanOptions(
        follow_symlinks=args.follow_symlinks,
        cross_mounts=args.cross_mounts,
        count_hardlinks_once=not args.no_hardlink_dedupe,
        excludes=tuple(args.exclude) if args.exclude else DEFAULT_EXCLUDES,
        top_files=args.top_files,
    )

    cancel = threading.Event()
    interrupted = False

    def _on_sigint(signum: int, frame: FrameType | None) -> None:
        nonlocal interrupted
        interrupted = True
        cancel.set()

    old_handler = signal.signal(signal.SIGINT, _on_sigint)
    try:
        rc = (
            _run_json(args.path, options, cancel)
            if args.json
            else _run_text(args.path, options, cancel)
        )
    except KeyboardInterrupt:
        # Race: SIGINT landed before the handler was installed, or between
        # the handler firing and the scan noticing `cancel`.
        interrupted = True
        rc = 0
    finally:
        signal.signal(signal.SIGINT, old_handler)

    return 130 if interrupted else rc


if __name__ == "__main__":
    sys.exit(main())
