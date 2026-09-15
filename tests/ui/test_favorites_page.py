"""FavoritesPage tests (needs a display). Uses the session-scoped ``window``
fixture from ``tests/ui/conftest.py`` -- see its docstring for why a full
``LinDriveSpaceApp`` is only built once per test session.
"""

from __future__ import annotations

from pathlib import Path

import gi
import pytest

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from lindrivespace.services.favorites import get_store  # noqa: E402


def _pump() -> None:
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)


@pytest.fixture
def page(window):  # type: ignore[no-untyped-def]
    window.show_page("favorites")
    page = window.pages["favorites"]
    store = get_store(window.app)
    # Leave the store empty at the start of every test -- other UI test
    # modules share this session-scoped window/app and must not see leftovers.
    for fav in list(store.list()):
        store.remove(fav.path)
    _pump()
    return page


def test_empty_state_visible_with_no_favorites(page) -> None:  # type: ignore[no-untyped-def]
    assert page.empty_label.get_visible() is True
    assert "No favorites yet" in page.empty_label.get_text()
    assert page.list_box.get_visible() is False
    assert len(page.list_box.get_children()) == 0


def test_add_favorite_shows_one_row_with_label(page, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    folder = tmp_path / "Reports"
    folder.mkdir()
    store = get_store(page.app)

    store.add(str(folder))
    _pump()

    assert page.empty_label.get_visible() is False
    assert page.list_box.get_visible() is True
    rows = page.list_box.get_children()
    assert len(rows) == 1
    assert rows[0].favorite_path == str(folder)


def test_activating_a_directory_row_requests_scan_of_that_directory(
    page, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    folder = tmp_path / "Photos"
    folder.mkdir()
    store = get_store(page.app)
    store.add(str(folder))
    _pump()

    calls: list[str] = []
    monkeypatch.setattr(page.window, "request_scan", lambda path: calls.append(path))
    page.window.pending_reveal = None

    row = page.list_box.get_children()[0]
    page.list_box.select_row(row)
    page.list_box.emit("row-activated", row)

    assert calls == [str(folder)]
    assert page.window.pending_reveal is None


def test_activating_a_file_row_requests_scan_of_parent_and_sets_pending_reveal(
    page, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    file_path = tmp_path / "budget.ods"
    file_path.write_text("data")
    store = get_store(page.app)
    store.add(str(file_path))
    _pump()

    calls: list[str] = []
    monkeypatch.setattr(page.window, "request_scan", lambda path: calls.append(path))
    page.window.pending_reveal = None

    row = page.list_box.get_children()[0]
    page.list_box.select_row(row)
    page.list_box.emit("row-activated", row)

    assert calls == [str(tmp_path)]
    assert page.window.pending_reveal == str(file_path)


def test_remove_button_empties_the_list(page, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    folder = tmp_path / "Archive"
    folder.mkdir()
    store = get_store(page.app)
    store.add(str(folder))
    _pump()

    row = page.list_box.get_children()[0]
    outer = row.get_child()
    buttons = [
        child for child in outer.get_children()[-1].get_children() if isinstance(child, Gtk.Button)
    ]
    remove_button = next(b for b in buttons if b.get_label() == "Remove")
    remove_button.clicked()
    _pump()

    assert page.empty_label.get_visible() is True
    assert len(page.list_box.get_children()) == 0
    assert store.list() == []


def test_sidebar_has_a_favorites_button(window) -> None:  # type: ignore[no-untyped-def]
    assert "favorites" in window.sidebar.buttons
