"""WP10 UI tests for the Snapshots page. Needs a display (DISPLAY=:0).

Deliberately does *not* build a full ``LinDriveSpaceApp`` + ``MainWindow`` (the
pattern in ``tests/ui/test_smoke.py``): a ``Gtk.Application`` registers a
D-Bus object at a path derived from its (fixed) application id, and a second
live instance of that same id within the same test process -- i.e. this
module's own fixture, on top of ``test_smoke.py``'s -- reliably raises "An
object is already exported for the interface org.gtk.Application" when the
whole ``tests/ui`` suite runs together. ``BasePage``/``SnapshotsPage`` only
ever touch ``window.app.settings``, ``window.app.theme`` and
``window.pages.get("explorer")``, so a tiny double covers everything the page
needs -- same spirit as ``tests/ui/test_overview.py`` and
``tests/ui/test_widgets.py`` (a bare ``Gtk.OffscreenWindow``, no application).
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import gi
import pytest

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from lindrivespace.config.settings import Settings  # noqa: E402
from lindrivespace.config.theme import get_theme  # noqa: E402
from lindrivespace.core.fsnode import FsNode  # noqa: E402
from lindrivespace.core.snapshot import default_snapshot_dir  # noqa: E402
from lindrivespace.ui.pages.snapshots import SnapshotsPage  # noqa: E402


def _pump() -> None:
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)


def _build_root(id_offset: int, name: str, big: bool) -> FsNode:
    """A small 4-node tree: root -> {keep, grower, newdir-or-gone}.

    ``big=False`` is the "before" snapshot (has "gone", small "grower");
    ``big=True`` is the "after" snapshot (has "newdir", bigger "grower").
    """
    now = time.time()
    root = FsNode(id_offset, name, None, mtime=now)
    keep = FsNode(id_offset + 1, "keep", root, mtime=now)
    keep.add_file(1_000_000, 1_000_000, now, "keep.bin")
    grower = FsNode(id_offset + 2, "grower", root, mtime=now)
    grower_alloc = 2_000_000 if big else 500_000
    grower.add_file(grower_alloc, grower_alloc, now, "g.bin")
    if big:
        extra = FsNode(id_offset + 3, "newdir", root, mtime=now)
        extra.add_file(3_000_000, 3_000_000, now, "n.bin")
    else:
        extra = FsNode(id_offset + 3, "gone", root, mtime=now)
        extra.add_file(4_000_000, 4_000_000, now, "gone.bin")

    for child in list(root.children):
        child.finalize()
    root.finalize()
    return root


class _FakeApp:
    """Just the two attributes BasePage reads off ``window.app``."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.theme = get_theme(settings.get("theme"))


class _FakeWindow:
    """Stands in for MainWindow: only what BasePage/SnapshotsPage touch."""

    def __init__(self, settings: Settings) -> None:
        self.app = _FakeApp(settings)
        self.pages: dict[str, object] = {}


@pytest.fixture(scope="module")
def window():  # type: ignore[no-untyped-def]
    settings = Settings(path=Path(tempfile.mkdtemp(prefix="lds-snapshots-")) / "settings.json")
    win = _FakeWindow(settings)

    offscreen = Gtk.OffscreenWindow()
    page = SnapshotsPage(win)
    offscreen.add(page)
    offscreen.show_all()
    _pump()

    win.pages = {"snapshots": page}
    yield win
    offscreen.destroy()


def test_save_current_creates_a_snapshot_file_and_list_row(window) -> None:  # type: ignore[no-untyped-def]
    page = window.pages["snapshots"]
    root = _build_root(1000, "/tmp/x", big=False)

    saved = page.save_current(root, root.path())
    _pump()

    assert saved is not None
    assert saved.exists()
    assert saved.parent == default_snapshot_dir()
    assert len(page.list_store) == 1


def test_compare_two_snapshots_reports_expected_kinds(window) -> None:  # type: ignore[no-untyped-def]
    page = window.pages["snapshots"]

    root_before = _build_root(2000, "/tmp/y", big=False)
    root_after = _build_root(3000, "/tmp/y", big=True)

    page.save_current(root_before, root_before.path())
    time.sleep(1.1)  # snapshot filenames are second-resolution: keep them ordered
    page.save_current(root_after, root_after.path())
    _pump()

    assert len(page.list_store) == 2
    # list_snapshots (and so the combos) are newest first: index 0 = "after".
    page.combo_a.set_active(1)  # before
    page.combo_b.set_active(0)  # after
    page._on_compare_clicked(None)
    _pump()

    kinds = {row[1] for row in page.diff_store}
    assert kinds == {"grew", "new", "deleted"}


def test_delete_without_confirm_removes_the_file(window) -> None:  # type: ignore[no-untyped-def]
    page = window.pages["snapshots"]
    root = _build_root(4000, "/tmp/z", big=False)
    saved = page.save_current(root, root.path())
    _pump()
    assert saved is not None and saved.exists()

    page.list_view.get_selection().select_path(Gtk.TreePath.new_first())
    removed = page.delete(confirm=False)
    _pump()

    assert removed is True
    assert not saved.exists()
    assert len(page.list_store) == 0
