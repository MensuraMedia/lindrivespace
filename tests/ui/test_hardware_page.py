"""HardwarePage tests -- uses the shared session-scoped ``window`` fixture
(see ``tests/ui/test_settings_page.py`` for why: only one ``Gtk.Application``
may register per process).

Collection runs on a background thread and reports back through
``GLib.idle_add``, so every assertion that depends on the report being ready
pumps the default ``GLib.MainContext`` until a condition holds (same pattern
as ``tests/ui/test_overview.py``'s ``_pump_until``).
"""

from __future__ import annotations

import time

import gi
import pytest

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402


def _pump_until(condition, timeout: float = 10.0) -> None:  # type: ignore[no-untyped-def]
    ctx = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise TimeoutError("condition not met before timeout")
        if not ctx.iteration(False):
            time.sleep(0.01)


def _iter_widgets(widget: Gtk.Widget):  # type: ignore[no-untyped-def]
    yield widget
    get_children = getattr(widget, "get_children", None)
    if callable(get_children):
        for child in get_children():
            yield from _iter_widgets(child)


def _find_label_text(root: Gtk.Widget, text: str) -> bool:
    for widget in _iter_widgets(root):
        if isinstance(widget, Gtk.Label) and widget.get_text() == text:
            return True
    return False


def _find_tree_views(root: Gtk.Widget) -> list[Gtk.TreeView]:
    return [w for w in _iter_widgets(root) if isinstance(w, Gtk.TreeView)]


@pytest.fixture
def page(window):  # type: ignore[no-untyped-def]
    window.show_page("hardware")
    hw_page = window.pages["hardware"]
    _pump_until(lambda: hw_page._report is not None, timeout=15.0)
    return hw_page


# ---- collection lifecycle -----------------------------------------------------------


def test_showing_page_triggers_collection(window) -> None:  # type: ignore[no-untyped-def]
    # Navigate away first so a fresh on_shown() fires (show_page no-ops when
    # the target is already current).
    window.show_page("overview")
    window.show_page("hardware")
    hw_page = window.pages["hardware"]
    assert hw_page._collecting or hw_page._report is not None
    _pump_until(lambda: hw_page._report is not None, timeout=15.0)
    assert hw_page._report is not None
    assert hw_page._report.system.kernel


def test_system_group_shows_kernel(window, page) -> None:  # type: ignore[no-untyped-def]
    kernel = page._report.system.kernel
    assert kernel
    assert _find_label_text(page.content_box, kernel)


def test_hostname_shown(window, page) -> None:  # type: ignore[no-untyped-def]
    hostname = page._report.system.hostname
    assert hostname
    assert _find_label_text(page.content_box, hostname)


# ---- disks table ----------------------------------------------------------------------


def test_disks_table_has_at_least_one_row(window, page) -> None:  # type: ignore[no-untyped-def]
    assert len(page._report.disks) >= 1
    assert page.disks_store is not None
    assert len(page.disks_store) >= 1

    tree_views = _find_tree_views(page.content_box)
    assert len(tree_views) >= 1


# ---- I/O activity timer -----------------------------------------------------------------


def test_io_timer_starts_on_show_and_stops_on_hide(window, page) -> None:  # type: ignore[no-untyped-def]
    assert page._io_timer_id is not None

    window.show_page("overview")
    assert page._io_timer_id is None

    window.show_page("hardware")
    _pump_until(lambda: page._io_timer_id is not None, timeout=5.0)
    assert page._io_timer_id is not None
    # leave the suite on a sane page
    window.show_page("overview")
    assert page._io_timer_id is None
    window.show_page("hardware")


def test_io_activity_group_rebuilt_after_refresh(window, page) -> None:  # type: ignore[no-untyped-def]
    if not page._report.disks:
        pytest.skip("no disks on this machine")
    assert page.io_store is not None
    known = {row[0] for row in page.io_store}
    assert known == {d.kname for d in page._report.disks}


# ---- copy report ------------------------------------------------------------------------


def test_copy_report_sets_clipboard_text(window, page) -> None:  # type: ignore[no-untyped-def]
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    page._on_copy_clicked(page.copy_button)
    text = clipboard.wait_for_text()
    if text is None:
        pytest.skip("no clipboard manager available in this test environment")
    assert page._report.system.hostname in text
    assert "Hardware report" in text
