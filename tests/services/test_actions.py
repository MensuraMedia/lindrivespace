"""Tests for lindrivespace.services.actions.

Most of these run headlessly: the interesting behaviour under test is that
these functions never raise, even when the underlying integration (a
terminal emulator, a file manager, a trash backend) is unavailable. Only the
clipboard round-trip needs a real GTK display, and is skipped without one.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from lindrivespace.services.actions import (
    copy_path,
    move_to_trash,
    open_in_file_manager,
    open_terminal,
)

HAS_DISPLAY = bool(os.environ.get("DISPLAY"))


def _gtk_ready() -> bool:
    if not HAS_DISPLAY:
        return False
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gtk

        ok, _argv = Gtk.init_check([])
        return bool(ok)
    except Exception:  # noqa: BLE001 - any failure means "no usable display"
        return False


@pytest.mark.skipif(not _gtk_ready(), reason="no display for GTK clipboard")
def test_copy_path_round_trips_through_clipboard() -> None:
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, Gtk

    copy_path("/tmp/some/interesting/path")
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    assert clipboard.wait_for_text() == "/tmp/some/interesting/path"


def test_move_to_trash_never_raises(tmp_path: Path) -> None:
    target = tmp_path / "doomed.txt"
    target.write_text("bye")
    ok, message = move_to_trash(str(target))
    assert isinstance(ok, bool)
    assert isinstance(message, str)
    if ok:
        assert not target.exists()


def test_open_terminal_returns_false_with_no_emulator_on_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    assert open_terminal(str(tmp_path)) is False


def test_open_in_file_manager_relative_path_returns_false() -> None:
    # GLib.filename_to_uri requires an absolute path -- a relative one fails
    # deterministically, regardless of what file manager (if any) is installed.
    assert open_in_file_manager("not/an/absolute/path") is False
