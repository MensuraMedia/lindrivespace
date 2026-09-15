"""SettingsPage tests (WP12) — uses the shared session-scoped ``window``
fixture from ``tests/ui/conftest.py`` (never build a second ``Gtk.Application``
in this process; see ``tests/ui/test_overview.py`` for why).

Every test that changes a setting either restores it or is itself the
"restore" (the theme test switches to the light preview and back to dark),
since ``window`` -- and therefore ``window.app.settings`` -- is shared with
every other module in the session.
"""

from __future__ import annotations

import gi
import pytest

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from lindrivespace.config.settings import DEFAULTS  # noqa: E402
from lindrivespace.core.options import DEFAULT_EXCLUDES  # noqa: E402


@pytest.fixture
def page(window):  # type: ignore[no-untyped-def]
    window.show_page("settings")
    return window.pages["settings"]


def _iter_widgets(widget: Gtk.Widget):  # type: ignore[no-untyped-def]
    yield widget
    get_children = getattr(widget, "get_children", None)
    if callable(get_children):
        for child in get_children():
            yield from _iter_widgets(child)


def _exclude_row_path(row: Gtk.ListBoxRow) -> str:
    box = row.get_child()
    label = box.get_children()[0]
    return str(label.get_text())


# ---- Units ------------------------------------------------------------------


def test_toggling_units_radio_persists(window, page) -> None:  # type: ignore[no-untyped-def]
    settings = window.app.settings
    original = settings.get("units", "decimal")
    try:
        page.units_binary_radio.set_active(True)
        assert settings.get("units") == "binary"

        page.units_decimal_radio.set_active(True)
        assert settings.get("units") == "decimal"
    finally:
        page._set_units_radio_active(original)
        settings.set("units", original)
        settings.save()


def test_toggling_primary_radio_persists(window, page) -> None:  # type: ignore[no-untyped-def]
    settings = window.app.settings
    original = settings.get("primary_size", "allocated")
    try:
        page.primary_apparent_radio.set_active(True)
        assert settings.get("primary_size") == "apparent"

        page.primary_allocated_radio.set_active(True)
        assert settings.get("primary_size") == "allocated"
    finally:
        page._set_primary_radio_active(original)
        settings.set("primary_size", original)
        settings.save()


# ---- Scanning defaults --------------------------------------------------


def test_toggling_scan_switch_persists(window, page) -> None:  # type: ignore[no-untyped-def]
    settings = window.app.settings
    original = bool(settings.get("scan.follow_symlinks", False))
    try:
        page.follow_symlinks_switch.set_active(not original)
        assert settings.get("scan.follow_symlinks") == (not original)
    finally:
        page.follow_symlinks_switch.set_active(original)
        settings.set("scan.follow_symlinks", original)
        settings.save()


def test_top_files_spin_persists(window, page) -> None:  # type: ignore[no-untyped-def]
    settings = window.app.settings
    original = int(settings.get("scan.top_files", 50))
    try:
        page.top_files_spin.set_value(75)
        assert settings.get("scan.top_files") == 75
    finally:
        page.top_files_spin.set_value(original)
        settings.set("scan.top_files", original)
        settings.save()


# ---- Exclusions ---------------------------------------------------------


def test_adding_exclusion_appears_in_list_and_settings(window, page) -> None:  # type: ignore[no-untyped-def]
    settings = window.app.settings
    before = list(settings.get("scan.excludes", list(DEFAULT_EXCLUDES)))
    new_path = "/tmp/lindrivespace-test-exclude"
    try:
        page.exclude_entry.set_text(new_path)
        page._on_add_exclude(page.exclude_entry)

        assert new_path in settings.get("scan.excludes")
        rows = page.excludes_listbox.get_children()
        assert new_path in [_exclude_row_path(r) for r in rows]
    finally:
        settings.set("scan.excludes", before)
        settings.save()
        page._rebuild_excludes_list()


def test_invalid_relative_path_shows_error_and_is_not_added(window, page) -> None:  # type: ignore[no-untyped-def]
    settings = window.app.settings
    before = list(settings.get("scan.excludes", list(DEFAULT_EXCLUDES)))

    page.exclude_entry.set_text("relative/path")
    page._on_add_exclude(page.exclude_entry)

    assert settings.get("scan.excludes") == before
    assert page.exclude_error_label.get_visible()
    assert page.exclude_error_label.get_text()

    page.exclude_entry.set_text("")
    page.exclude_error_label.set_visible(False)


def test_reset_excludes_restores_defaults(window, page) -> None:  # type: ignore[no-untyped-def]
    settings = window.app.settings
    before = list(settings.get("scan.excludes", list(DEFAULT_EXCLUDES)))
    try:
        page.exclude_entry.set_text("/custom/exclude/path")
        page._on_add_exclude(page.exclude_entry)
        assert "/custom/exclude/path" in settings.get("scan.excludes")

        page._on_reset_excludes(None)
        assert settings.get("scan.excludes") == list(DEFAULT_EXCLUDES)
    finally:
        settings.set("scan.excludes", before)
        settings.save()
        page._rebuild_excludes_list()


# ---- Theme --------------------------------------------------------------


def test_theme_combo_switches_to_light_preview_and_back_to_dark(window, page) -> None:  # type: ignore[no-untyped-def]
    settings = window.app.settings

    page.theme_combo.set_active_id("gray-temperature-light")
    assert window.app.theme.id == "gray-temperature-light"
    assert settings.get("theme") == "gray-temperature-light"

    # Session must end on the dark theme -- other test modules assert this.
    page.theme_combo.set_active_id("gray-temperature-dark")
    assert window.app.theme.id == "gray-temperature-dark"
    assert settings.get("theme") == "gray-temperature-dark"


# ---- Explorer -------------------------------------------------------------


def test_reset_column_layout_resets_explorer_settings(window, page) -> None:  # type: ignore[no-untyped-def]
    settings = window.app.settings
    before = settings.get("explorer", {})
    try:
        settings.set("explorer.columns", ["name", "size"])
        settings.set("explorer.widths", {"name": 999})
        settings.set("explorer.hidden_columns", ["owner"])
        settings.set("explorer.sort", {"column": "name", "descending": False})
        settings.save()

        page._on_reset_columns(None)

        assert settings.get("explorer.columns") == DEFAULTS["explorer"]["columns"]
        assert settings.get("explorer.widths") == {}
        assert settings.get("explorer.hidden_columns") == DEFAULTS["explorer"]["hidden_columns"]
        assert settings.get("explorer.sort") == {"column": "alloc", "descending": True}
    finally:
        settings.set("explorer", before)
        settings.save()
        explorer = window.pages.get("explorer")
        tree = getattr(explorer, "tree", None)
        restore = getattr(tree, "restore_state", None)
        if callable(restore):
            restore()


# ---- Accessibility --------------------------------------------------------


def test_every_switch_spin_combo_entry_has_an_accessible_name(page) -> None:  # type: ignore[no-untyped-def]
    target_types = (Gtk.Switch, Gtk.SpinButton, Gtk.ComboBoxText, Gtk.Entry)
    controls = [w for w in _iter_widgets(page) if isinstance(w, target_types)]
    assert controls, "expected at least one Switch/SpinButton/ComboBoxText/Entry on the page"
    for widget in controls:
        name = widget.get_accessible().get_name()
        assert name, f"{widget.get_name()} ({type(widget).__name__}) has no accessible name"


def test_primary_secondary_mountpoints(window) -> None:  # type: ignore[no-untyped-def]
    page = window.pages["settings"]
    settings = window.app.settings
    combo = page.role_combos["primary"]
    assert combo.get_active_id() == ""
    combo.append("/mnt/data", "/mnt/data")
    combo.append("/", "/")
    combo.set_active_id("/mnt/data")
    assert settings.get("mounts.primary") == "/mnt/data"
    # the same mountpoint cannot be both roles
    sec = page.role_combos["secondary"]
    sec.append("/mnt/data", "/mnt/data")
    sec.set_active_id("/mnt/data")
    assert settings.get("mounts.secondary") == "/mnt/data"
    assert settings.get("mounts.primary") == ""
    overview = window.pages["overview"]
    assert overview.mount_roles() == {"/mnt/data": "secondary"}
    sec.set_active_id("")
    assert settings.get("mounts.secondary") == ""
