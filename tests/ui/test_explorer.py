"""WP8: Explorer page + tree widgets (needs a display)."""

from __future__ import annotations

import time
from pathlib import Path

import gi
import pytest

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from lindrivespace.ui.widgets.explorer_tree import ExplorerTree  # noqa: E402
from lindrivespace.ui.widgets.tree_context_menu import TreeContextMenu  # noqa: E402


def _pump(cond, timeout: float = 30.0) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while not cond() and time.monotonic() < deadline:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        GLib.MainContext.default().iteration(False)
        time.sleep(0.002)
    # one more pass to let any idle_add callbacks scheduled by the last
    # iteration (e.g. columns-changed debouncing) run to completion.
    for _ in range(20):
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        GLib.MainContext.default().iteration(False)


def _make_tree(tmp_path: Path) -> Path:
    """root/{a/{f1,f2}, b/{big}, c/sub/{small}} — three top-level dirs."""
    root = tmp_path / "scanroot"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir(parents=True)
    (root / "c" / "sub").mkdir(parents=True)
    (root / "a" / "f1").write_bytes(b"x" * 1000)
    (root / "a" / "f2").write_bytes(b"y" * 2000)
    (root / "b" / "big").write_bytes(b"z" * 500_000)
    (root / "c" / "sub" / "small").write_bytes(b"w" * 10)
    return root


@pytest.fixture
def page(window):  # type: ignore[no-untyped-def]
    window.show_page("explorer")
    return window.pages["explorer"]


# ---- end-to-end scan --------------------------------------------------------


def test_scan_populates_tree_sorted_by_allocated(window, page, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    root = _make_tree(tmp_path)
    page.start_scan(str(root))
    _pump(lambda: not page.controller.running)

    assert page.model.root is not None
    assert page.model.root.finalized
    children = sorted(page.model.root.children, key=lambda n: n.alloc, reverse=True)
    assert [c.name for c in children] == ["b", "a", "c"]

    root_it = page.model.store.get_iter_first()
    assert root_it is not None
    names = []
    child = page.model.store.iter_children(root_it)
    while child is not None:
        node = page.model.node_for_iter(child)
        names.append(node.name if node is not None else None)
        child = page.model.store.iter_next(child)
    assert names == ["b", "a", "c"]  # default sort: alloc desc

    assert str(root) in window.scan_history


def test_expanding_row_populates_children(window, page, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    root = _make_tree(tmp_path)
    page.start_scan(str(root))
    _pump(lambda: not page.controller.running)

    c_node = next(c for c in page.model.root.children if c.name == "c")
    c_it = page.model.iter_for_node(c_node)
    assert c_it is not None
    assert page.model.store.iter_n_children(c_it) == 1
    dummy = page.model.store.iter_children(c_it)
    assert dummy is not None and page.model.is_dummy(dummy)

    path = page.model.store.get_path(c_it)
    page.tree.treeview.expand_row(path, False)
    _pump(lambda: c_node.id in page.model.populated, timeout=5.0)

    assert c_node.id in page.model.populated
    child = page.model.store.iter_children(c_it)
    assert child is not None and not page.model.is_dummy(child)
    node = page.model.node_for_iter(child)
    assert node is not None and node.name == "sub"


# ---- column reorder ----------------------------------------------------------


def test_move_column_to_persists_order(page) -> None:  # type: ignore[no-untyped-def]
    tree: ExplorerTree = page.tree
    tree.move_column_to("modified", 1)
    _pump(lambda: page.settings.get("explorer.columns", [])[1] == "modified", timeout=5.0)
    order = page.settings.get("explorer.columns")
    assert order[0] == "name"
    assert order[1] == "modified"


# ---- sorting -----------------------------------------------------------------


def test_header_click_sorts_and_toggles(page) -> None:  # type: ignore[no-untyped-def]
    tree: ExplorerTree = page.tree
    column = tree.get_column("files")
    assert column is not None

    column.clicked()
    assert tree.model.sort_column == "files"
    assert tree.model.sort_descending is True
    assert column.get_sort_indicator() is True
    assert column.get_sort_order() == Gtk.SortType.DESCENDING

    column.clicked()
    assert tree.model.sort_descending is False
    assert column.get_sort_order() == Gtk.SortType.ASCENDING

    name_column = tree.get_column("name")
    assert name_column is not None
    name_column.clicked()
    assert tree.model.sort_column == "name"
    assert tree.model.sort_descending is False
    assert column.get_sort_indicator() is False
    assert name_column.get_sort_indicator() is True


# ---- visibility ----------------------------------------------------------


def test_set_column_visible_shows_and_persists(page) -> None:  # type: ignore[no-untyped-def]
    tree: ExplorerTree = page.tree
    tree.set_column_visible("owner", False)
    assert "owner" in page.settings.get("explorer.hidden_columns", [])

    tree.set_column_visible("owner", True)
    owner_column = tree.get_column("owner")
    assert owner_column is not None
    assert owner_column.get_visible() is True
    assert "owner" not in page.settings.get("explorer.hidden_columns", [])


# ---- context menu -----------------------------------------------------------


def test_context_menu_copy_path_sets_clipboard(page, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    root = _make_tree(tmp_path)
    page.start_scan(str(root))
    _pump(lambda: not page.controller.running)

    node = page.model.root
    menu = TreeContextMenu(node)
    menu.connect("action", page._on_menu_action)
    menu.emit("action", "copy-path", node)

    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    text = clipboard.wait_for_text()
    if text is None:
        pytest.skip("clipboard not available in this environment")
    assert text == node.path()


def test_context_menu_sensitivity() -> None:
    from lindrivespace.core import fsnode as fs
    from lindrivespace.core.fsnode import FsNode

    normal = FsNode(1, "normal", None)
    denied = FsNode(2, "denied", None, flags=fs.DENIED)

    menu_normal = TreeContextMenu(normal, has_side_panel=False)
    items = menu_normal.get_children()
    # favorite, separator, 3 items, separator, 2 items, separator, admin, treemap, sep, columns
    admin_item = items[9]
    assert admin_item.get_label() == "Scan as administrator"
    assert admin_item.get_sensitive() is False
    assert items[10].get_sensitive() is False  # show in treemap, no side panel

    menu_denied = TreeContextMenu(denied, has_side_panel=True)
    items2 = menu_denied.get_children()
    assert items2[7].get_sensitive() is True
    assert items2[8].get_sensitive() is True  # show in treemap, has_side_panel=True


def test_favorites_star_and_reveal(window, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Ctrl+D / toolbar star / context menu toggle the favourite; file favourites reveal."""
    page = window.pages["explorer"]
    root = tmp_path / "favroot"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "keep.bin").write_bytes(b"k" * 5000)
    page.start_scan(str(root))
    _pump(lambda: not page.controller.running)
    page.tree.select_node(page.model.root)
    assert page.selected_path() == str(root)
    assert page.toggle_favorite() is True
    assert page.favorites.is_favorite(str(root))
    assert page.toolbar.favorite_button.get_active() is True
    assert page.toggle_favorite() is False
    assert page.toolbar.favorite_button.get_active() is False
    # reveal a file favourite: folder expanded, file row selected
    assert page.reveal_path(str(root / "sub" / "keep.bin")) is True
    row = page.tree.get_selected_row()
    assert row is not None and row.name == "keep.bin"
    # pending reveal is honoured after a scan
    window.pending_reveal = str(root / "sub")
    page.start_scan(str(root))
    _pump(lambda: not page.controller.running)
    node = page.tree.get_selected_node()
    assert node is not None and node.name == "sub"
    assert window.pending_reveal is None
