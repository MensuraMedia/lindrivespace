"""The scan banner at the top of the content area (needs a display)."""

from __future__ import annotations

import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from lindrivespace.services.scan_registry import STATE_DONE, expected_bytes  # noqa: E402
from lindrivespace.ui.widgets.scan_banner import format_countdown  # noqa: E402


def _pump(cond, timeout: float = 30.0) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while not cond() and time.monotonic() < deadline:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        GLib.MainContext.default().iteration(False)
        time.sleep(0.002)


def test_format_countdown() -> None:
    assert format_countdown(None) == "estimating…"
    assert format_countdown(3) == "< 5 s left"
    assert format_countdown(42) == "≈ 42 s left"
    assert format_countdown(102) == "≈ 1:42 left"
    assert format_countdown(3723) == "≈ 1:02:03 left"


def test_expected_bytes_mount_and_folder(tmp_path: Path) -> None:
    assert expected_bytes("/") > 0  # statvfs used bytes of the root mount
    assert expected_bytes(str(tmp_path)) == 0  # unknown folder, no previous scan
    assert expected_bytes(str(tmp_path), last_alloc=1234) == 1234


def test_banner_shows_during_scan_and_hides_after(window, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "bannerroot"
    (root / "d").mkdir(parents=True)
    for i in range(40):
        (root / "d" / f"f{i}.bin").write_bytes(b"b" * 50_000)
    banner = window.scan_banner
    registry = window.app.scan_registry
    assert not banner.get_visible()
    registry.request(str(root))
    _pump(lambda: banner.get_visible(), timeout=10.0)
    assert banner.get_visible()
    assert banner.path_label.get_text() == str(root)
    assert "entries" not in banner.stats_label.get_text()
    assert banner.spinner.get_property("active")
    _pump(lambda: registry.get(str(root)).state == STATE_DONE, timeout=30.0)
    _pump(lambda: not banner.get_visible(), timeout=5.0)
    assert not banner.get_visible()
    # a second scan of the same folder knows the expected total → real progress
    entry = registry.get(str(root))
    assert entry.last_alloc > 0
    registry.request(str(root), force=True)
    _pump(lambda: banner.get_visible(), timeout=10.0)
    assert registry.get(str(root)).expected_bytes == entry.last_alloc
    _pump(lambda: registry.get(str(root)).state == STATE_DONE, timeout=30.0)


def test_banner_stop_cancels(window, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "stoproot"
    root.mkdir()
    for i in range(3000):
        (root / f"f{i}").write_bytes(b"x")
    registry = window.app.scan_registry
    banner = window.scan_banner
    registry.request(str(root))
    _pump(lambda: banner.get_visible(), timeout=10.0)
    banner.stop_button.clicked()
    _pump(lambda: registry.active is None, timeout=30.0)
    assert registry.get(str(root)).state in ("cancelled", STATE_DONE)
    assert not banner.get_visible()
