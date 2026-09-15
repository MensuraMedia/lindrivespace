"""Runs a privileged scan via ``pkexec`` + the scan helper (WP11).

Design note: this module is stdlib/threads only, deliberately mirroring
``core-purity`` even though ``services/`` is not covered by that rule --
`PrivilegedScan` implements the exact same ``Producer`` protocol
(``cancel``/``pause``/``resume``/``is_alive``) that
``services.scan_controller.ScanController.consume()`` already accepts for
``FakeProducer`` and the in-process ``ScanThread``, so the controller drains a
privileged scan on the GTK main loop with no code changes and no GLib import
here: a daemon reader thread parses the helper's NDJSON stdout with
``core.event_codec.parse_event_line`` and puts events on the same
``queue.SimpleQueue`` the controller already drains.

Explorer usage (once wired up by the UI work package that owns the "Scan as
administrator" action)::

    from lindrivespace.services.privilege import PrivilegedScan

    q: queue.SimpleQueue[ScanEvent] = queue.SimpleQueue()
    producer = PrivilegedScan(path, options, q)
    producer.start()
    controller.consume(path, q, producer, options)

Merging a denied subtree into an already-displayed tree is out of scope for
v1: a "Scan as administrator" click re-scans that folder as a new root (see
the change manifest for this work package).
"""

from __future__ import annotations

import os
import queue
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import IO

from lindrivespace.core.event_codec import parse_event_line
from lindrivespace.core.events import DirStarted, Finished, Progress, ScanError, ScanEvent
from lindrivespace.core.options import ScanOptions

_TERM_GRACE_SECONDS = 3.0
_HELPER_ENV_VAR = "LINDRIVESPACE_SCAN_HELPER"


def pkexec_available() -> bool:
    """Whether a ``pkexec`` binary is on ``PATH``."""
    return shutil.which("pkexec") is not None


def helper_path() -> Path:
    """Locate the scan helper script.

    Resolution order: ``$LINDRIVESPACE_SCAN_HELPER`` (tests) -> the checkout
    copy at ``data/bin/lindrivespace-scan-helper`` (this file lives at
    ``src/lindrivespace/services/privilege.py``, so ``parents[3]`` is the
    project root) -> the installed location under ``/usr/libexec``.
    """
    override = os.environ.get(_HELPER_ENV_VAR)
    if override:
        return Path(override)
    checkout = Path(__file__).resolve().parents[3] / "data" / "bin" / "lindrivespace-scan-helper"
    if checkout.exists():
        return checkout
    return Path("/usr/libexec/lindrivespace/lindrivespace-scan-helper")


def can_scan_as_admin() -> tuple[bool, str]:
    """Whether a privileged scan is currently possible, and why (not) for the UI to show."""
    if not pkexec_available():
        return False, "pkexec is not installed"
    path = helper_path()
    if not path.exists():
        return False, f"scan helper not found at {path}"
    return True, "ready"


def _options_to_flags(options: ScanOptions) -> list[str]:
    """Translate ``ScanOptions`` into the CLI flags ``scanner_cli.py``/the helper accept."""
    flags: list[str] = []
    if options.cross_mounts:
        flags.append("--cross-mounts")
    if options.follow_symlinks:
        flags.append("--follow-symlinks")
    if not options.count_hardlinks_once:
        flags.append("--no-hardlink-dedupe")
    for excluded in options.excludes:
        flags.append("--exclude")
        flags.append(excluded)
    flags.append("--top-files")
    flags.append(str(options.top_files))
    return flags


def _error_message_for_returncode(returncode: int, stderr_tail: str) -> str:
    if returncode == 126:
        return "Authorisation was cancelled"
    if returncode == 127:
        return "Not authorised"
    if stderr_tail:
        return f"helper exited with code {returncode}: {stderr_tail}"
    return f"helper exited with code {returncode}"


class PrivilegedScan:
    """A ``Producer`` that runs the scan helper (under ``pkexec`` by default) as a subprocess.

    ``start()`` launches the helper and a daemon reader thread that turns its
    NDJSON stdout into events on ``queue``. The controller never talks to the
    subprocess directly -- only through this object's ``cancel``/``pause``/
    ``resume``/``is_alive``, exactly like any other ``Producer``.
    """

    def __init__(
        self,
        path: str,
        options: ScanOptions,
        q: queue.SimpleQueue[ScanEvent],
        *,
        use_pkexec: bool = True,
        python: str | None = None,
    ) -> None:
        self.path = path
        self.options = options
        self.queue = q
        self.use_pkexec = use_pkexec
        self.python = python or "python3"
        self.process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._started_at = 0.0
        self._entries_seen = 0
        self._root_id = 0
        self._finished_seen = False
        self._stderr_lines: list[str] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------- lifecycle

    def start(self) -> None:
        helper = str(helper_path())
        args = ["--json", *_options_to_flags(self.options), self.path]
        argv = ["pkexec", helper, *args] if self.use_pkexec else [self.python, helper, *args]
        self._started_at = time.monotonic()
        self.process = subprocess.Popen(  # noqa: S603 - argv is built from fixed, validated parts
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        proc = self.process
        assert proc is not None
        assert proc.stdout is not None
        assert proc.stderr is not None

        stderr_thread = threading.Thread(
            target=self._drain_stderr, args=(proc.stderr,), daemon=True
        )
        stderr_thread.start()

        for line in proc.stdout:
            event = parse_event_line(line)
            if event is None:
                continue
            if isinstance(event, DirStarted) and event.parent_id is None:
                self._root_id = event.id
            if isinstance(event, (Progress, Finished)):
                self._entries_seen = event.entries
            if isinstance(event, Finished):
                self._finished_seen = True
            self.queue.put(event)

        proc.stdout.close()
        returncode = proc.wait()
        stderr_thread.join(timeout=1.0)

        if not self._finished_seen:
            message = _error_message_for_returncode(returncode, self.stderr_tail)
            elapsed = time.monotonic() - self._started_at if self._started_at else 0.0
            self.queue.put(ScanError(self.path, message))
            self.queue.put(
                Finished(
                    root_id=self._root_id,
                    entries=self._entries_seen,
                    elapsed=elapsed,
                    cancelled=True,
                )
            )

    def _drain_stderr(self, stderr: IO[str]) -> None:
        for raw_line in stderr:
            line = raw_line.rstrip("\n")
            if line:
                with self._lock:
                    self._stderr_lines.append(line)
        stderr.close()

    # ------------------------------------------------------------- controls

    def cancel(self) -> None:
        proc = self.process
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.send_signal(signal.SIGINT)
        except ProcessLookupError:
            return

        def _escalate() -> None:
            time.sleep(_TERM_GRACE_SECONDS)
            if proc.poll() is None:
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass

        threading.Thread(target=_escalate, daemon=True).start()

    def pause(self) -> None:
        proc = self.process
        if proc is not None and proc.poll() is None:
            try:
                proc.send_signal(signal.SIGSTOP)
            except ProcessLookupError:
                pass

    def resume(self) -> None:
        proc = self.process
        if proc is not None and proc.poll() is None:
            try:
                proc.send_signal(signal.SIGCONT)
            except ProcessLookupError:
                pass

    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    @property
    def returncode(self) -> int | None:
        return self.process.returncode if self.process is not None else None

    @property
    def stderr_tail(self) -> str:
        with self._lock:
            return self._stderr_lines[-1] if self._stderr_lines else ""
