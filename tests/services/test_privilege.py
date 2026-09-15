"""Headless tests for services.privilege (WP11).

Real ``pkexec`` is never invoked here (it would prompt for a password and
block CI); every test uses ``PrivilegedScan(..., use_pkexec=False)`` to run
the helper script directly with the current interpreter, as the work order
requires. The helper resolves ``core/scanner_cli.py`` through
``$LINDRIVESPACE_SCANNER_CLI`` so it always runs the checkout copy under
test, never an installed one.
"""

from __future__ import annotations

import os
import queue
import stat
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from lindrivespace.core.events import DirDone, DirStarted, Finished, ScanError, ScanEvent
from lindrivespace.core.options import ScanOptions
from lindrivespace.core.scanner import Scanner
from lindrivespace.services.privilege import (
    PrivilegedScan,
    can_scan_as_admin,
    helper_path,
    pkexec_available,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC = PROJECT_ROOT / "src"
SCANNER_CLI = SRC / "lindrivespace" / "core" / "scanner_cli.py"
HELPER = PROJECT_ROOT / "data" / "bin" / "lindrivespace-scan-helper"
POLICY = PROJECT_ROOT / "data" / "polkit" / "com.mensuramedia.lindrivespace.policy"


def _drain(q: queue.SimpleQueue[ScanEvent], timeout: float = 15.0) -> list[ScanEvent]:
    events: list[ScanEvent] = []
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"timed out waiting for Finished; got {len(events)} events")
        try:
            event = q.get(timeout=remaining)
        except queue.Empty as exc:
            raise AssertionError(
                f"timed out waiting for Finished; got {len(events)} events"
            ) from exc
        events.append(event)
        if isinstance(event, Finished):
            return events


@pytest.fixture
def scanner_cli_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINDRIVESPACE_SCANNER_CLI", str(SCANNER_CLI))


def _wait_until_not_alive(producer: PrivilegedScan, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while producer.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not producer.is_alive(), "process did not end in time"


def _make_tree(root: Path, *, dirs: int = 1, files_per_dir: int = 3) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for d in range(dirs):
        sub = root / f"dir{d}"
        sub.mkdir()
        for f in range(files_per_dir):
            (sub / f"file{f}.bin").write_bytes(b"x" * (100 + f))
    (root / "top.txt").write_text("hello world")


# ---------------------------------------------------------------------------
# basic scan
# ---------------------------------------------------------------------------


def test_privileged_scan_basic(tmp_path: Path, scanner_cli_env: None) -> None:
    root = tmp_path / "root"
    _make_tree(root, dirs=3, files_per_dir=4)
    options = ScanOptions()

    q: queue.SimpleQueue[ScanEvent] = queue.SimpleQueue()
    producer = PrivilegedScan(str(root), options, q, use_pkexec=False, python=sys.executable)
    producer.start()
    events = _drain(q)

    assert isinstance(events[0], DirStarted)
    assert events[0].parent_id is None
    assert isinstance(events[-1], Finished)
    assert events[-1].cancelled is False

    root_id = events[0].id
    root_done = next(e for e in events if isinstance(e, DirDone) and e.id == root_id)

    expected_root = Scanner().scan(str(root), options, lambda _e: None)

    assert root_done.size == expected_root.size
    assert root_done.alloc == expected_root.alloc
    assert root_done.files == expected_root.files
    assert root_done.dirs == expected_root.dirs

    # Finished lands on the queue as soon as the reader thread parses that
    # line; the child process itself (and proc.wait()/returncode) finishes
    # closing out a moment later, so give it a brief window.
    _wait_until_not_alive(producer)
    assert producer.returncode == 0


def test_privileged_scan_no_errors_reported(tmp_path: Path, scanner_cli_env: None) -> None:
    root = tmp_path / "root"
    _make_tree(root)
    q: queue.SimpleQueue[ScanEvent] = queue.SimpleQueue()
    producer = PrivilegedScan(str(root), ScanOptions(), q, use_pkexec=False, python=sys.executable)
    producer.start()
    events = _drain(q)
    assert not any(isinstance(e, ScanError) for e in events)


# ---------------------------------------------------------------------------
# cancellation
# ---------------------------------------------------------------------------


def test_cancel_mid_scan_ends_process_with_cancelled_finished(
    tmp_path: Path, scanner_cli_env: None
) -> None:
    root = tmp_path / "root"
    # A few thousand files so a natural finish would take measurably longer
    # than the pause()/cancel()/resume() sequence below.
    _make_tree(root, dirs=40, files_per_dir=100)

    q: queue.SimpleQueue[ScanEvent] = queue.SimpleQueue()
    producer = PrivilegedScan(str(root), ScanOptions(), q, use_pkexec=False, python=sys.executable)
    producer.start()
    # Freeze the child before it can get far (SIGSTOP), queue up the
    # cancellation signal (delivered once resumed -- a stopped process only
    # reacts to SIGCONT/SIGKILL), then let it run: it should see SIGINT
    # essentially immediately and finish as "cancelled" well before actually
    # walking the whole tree.
    producer.pause()
    producer.cancel()
    producer.resume()

    events = _drain(q, timeout=15.0)
    assert isinstance(events[-1], Finished)
    assert events[-1].cancelled is True

    _wait_until_not_alive(producer)


# ---------------------------------------------------------------------------
# helper script argument validation (invoked directly, never via pkexec)
# ---------------------------------------------------------------------------


def test_helper_is_executable() -> None:
    mode = HELPER.stat().st_mode
    assert mode & stat.S_IXUSR


def test_helper_rejects_relative_path(tmp_path: Path, scanner_cli_env: None) -> None:
    result = subprocess.run(
        [sys.executable, str(HELPER), "--json", "relative/path"],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        check=False,
        cwd=str(tmp_path),
    )
    assert result.returncode != 0
    assert "relative" in result.stderr.lower()


def test_helper_rejects_unknown_flag(tmp_path: Path, scanner_cli_env: None) -> None:
    result = subprocess.run(
        [sys.executable, str(HELPER), "--not-a-real-flag", str(tmp_path)],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        check=False,
    )
    assert result.returncode != 0
    assert "unknown option" in result.stderr.lower()


def test_helper_requires_at_least_one_argument() -> None:
    result = subprocess.run(
        [sys.executable, str(HELPER)],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        check=False,
    )
    assert result.returncode != 0


def test_helper_runs_a_real_scan(tmp_path: Path, scanner_cli_env: None) -> None:
    root = tmp_path / "root"
    _make_tree(root)
    result = subprocess.run(
        [sys.executable, str(HELPER), "--json", str(root)],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        check=False,
    )
    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line]
    assert lines
    assert '"DirStarted"' in lines[0]
    assert '"Finished"' in lines[-1]


# ---------------------------------------------------------------------------
# pkexec exit-code mapping
# ---------------------------------------------------------------------------


def _write_fake_helper(path: Path, exit_code: int) -> None:
    path.write_text(f"#!/usr/bin/env python3\nimport sys\nsys.exit({exit_code})\n")
    path.chmod(0o755)


def test_pkexec_dismissed_maps_to_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_helper = tmp_path / "fake-helper-126"
    _write_fake_helper(fake_helper, 126)
    monkeypatch.setenv("LINDRIVESPACE_SCAN_HELPER", str(fake_helper))

    q: queue.SimpleQueue[ScanEvent] = queue.SimpleQueue()
    producer = PrivilegedScan(
        str(tmp_path), ScanOptions(), q, use_pkexec=False, python=sys.executable
    )
    producer.start()
    events = _drain(q)

    errors = [e for e in events if isinstance(e, ScanError)]
    assert errors
    assert errors[-1].message == "Authorisation was cancelled"
    assert isinstance(events[-1], Finished)
    assert events[-1].cancelled is True


def test_pkexec_not_authorised_maps_to_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_helper = tmp_path / "fake-helper-127"
    _write_fake_helper(fake_helper, 127)
    monkeypatch.setenv("LINDRIVESPACE_SCAN_HELPER", str(fake_helper))

    q: queue.SimpleQueue[ScanEvent] = queue.SimpleQueue()
    producer = PrivilegedScan(
        str(tmp_path), ScanOptions(), q, use_pkexec=False, python=sys.executable
    )
    producer.start()
    events = _drain(q)

    errors = [e for e in events if isinstance(e, ScanError)]
    assert errors
    assert errors[-1].message == "Not authorised"
    assert isinstance(events[-1], Finished)
    assert events[-1].cancelled is True


# ---------------------------------------------------------------------------
# path/availability helpers
# ---------------------------------------------------------------------------


def test_helper_path_resolves_checkout_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINDRIVESPACE_SCAN_HELPER", raising=False)
    resolved = helper_path()
    assert resolved == HELPER
    assert resolved.exists()


def test_helper_path_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = tmp_path / "helper"
    fake.write_text("#!/usr/bin/env python3\n")
    monkeypatch.setenv("LINDRIVESPACE_SCAN_HELPER", str(fake))
    assert helper_path() == fake


def test_pkexec_available_is_bool() -> None:
    assert isinstance(pkexec_available(), bool)


def test_can_scan_as_admin_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINDRIVESPACE_SCAN_HELPER", raising=False)
    ok, reason = can_scan_as_admin()
    assert isinstance(ok, bool)
    assert isinstance(reason, str) and reason


def test_can_scan_as_admin_false_when_pkexec_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("lindrivespace.services.privilege.pkexec_available", lambda: False)
    ok, reason = can_scan_as_admin()
    assert ok is False
    assert "pkexec" in reason.lower()


# ---------------------------------------------------------------------------
# polkit policy XML
# ---------------------------------------------------------------------------


def test_policy_xml_parses_and_has_required_fields() -> None:
    tree = ET.parse(POLICY)
    root = tree.getroot()
    assert root.tag == "policyconfig"

    vendor = root.find("vendor")
    assert vendor is not None and vendor.text == "MensuraMedia"

    action = root.find("action")
    assert action is not None
    assert action.get("id") == "com.mensuramedia.lindrivespace.scan"

    description = action.find("description")
    assert description is not None
    assert description.text == "Scan a folder as administrator"

    message = action.find("message")
    assert message is not None
    assert message.text == "Authentication is required to scan folders you cannot read"

    defaults = action.find("defaults")
    assert defaults is not None
    assert defaults.findtext("allow_any") == "no"
    assert defaults.findtext("allow_inactive") == "no"
    assert defaults.findtext("allow_active") == "auth_admin_keep"

    annotations = {a.get("key"): a.text for a in action.findall("annotate")}
    assert (
        annotations.get("org.freedesktop.policykit.exec.path")
        == "/usr/libexec/lindrivespace/lindrivespace-scan-helper"
    )
    assert annotations.get("org.freedesktop.policykit.exec.allow_gui") == "true"
