"""TopFilesView — largest files across a subtree (WP9 insight panel).

Gathers every node's bounded ``top_files`` ring across the selected subtree
(``FsNode.walk``) and keeps the 200 largest by allocated size. Paths are shown
relative to the selected node so long absolute paths stay legible.
"""

from __future__ import annotations

import heapq
import os
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import GObject, Gtk, Pango  # noqa: E402

from lindrivespace.config.theme import ThemeDefinition  # noqa: E402
from lindrivespace.core.units import format_date  # noqa: E402

if TYPE_CHECKING:
    from lindrivespace.core.fsnode import FsNode
    from lindrivespace.models.tree_model import ScanTreeModel

_MAX_ROWS = 200
_ACCENT_ROWS = 3

COL_REL_PATH, COL_SIZE, COL_MODIFIED, COL_ABS_PATH = range(4)


class TopFilesView(Gtk.TreeView):
    """The largest files anywhere under the selected node, largest first."""

    __gtype_name__ = "LdsTopFilesView"
    __gsignals__ = {
        "file-activated": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, theme: ThemeDefinition) -> None:
        self._store = Gtk.ListStore(str, str, str, str)
        super().__init__(model=self._store)
        self._theme = theme
        self._node: FsNode | None = None
        self._model: ScanTreeModel | None = None
        self._dirty = True

        self.set_headers_visible(True)
        self.set_fixed_height_mode(True)

        path_col = Gtk.TreeViewColumn("Path")
        path_col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        path_col.set_expand(True)
        path_renderer = Gtk.CellRendererText()
        path_renderer.set_property("ellipsize", Pango.EllipsizeMode.MIDDLE)
        path_renderer.set_property("family", theme.font_mono)
        path_col.pack_start(path_renderer, True)
        path_col.add_attribute(path_renderer, "text", COL_REL_PATH)
        self.append_column(path_col)

        size_col = Gtk.TreeViewColumn("Size")
        size_col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        size_col.set_fixed_width(84)
        self._size_renderer = Gtk.CellRendererText()
        self._size_renderer.set_property("xalign", 1.0)
        size_col.pack_start(self._size_renderer, False)
        size_col.add_attribute(self._size_renderer, "text", COL_SIZE)
        size_col.set_cell_data_func(self._size_renderer, self._size_cell_data)
        self.append_column(size_col)

        modified_col = Gtk.TreeViewColumn("Modified")
        modified_col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        modified_col.set_fixed_width(88)
        modified_renderer = Gtk.CellRendererText()
        modified_col.pack_start(modified_renderer, False)
        modified_col.add_attribute(modified_renderer, "text", COL_MODIFIED)
        self.append_column(modified_col)

        self.connect("row-activated", self._on_row_activated)

    # ---- theme / data -----------------------------------------------------

    def set_theme(self, theme: ThemeDefinition) -> None:
        self._theme = theme
        self.queue_draw()

    def set_node(self, node: FsNode | None, model: ScanTreeModel) -> None:
        self._node = node
        self._model = model
        self._dirty = True

    def ensure_fresh(self) -> None:
        if self._dirty:
            self._rebuild()
            self._dirty = False

    @property
    def rows(self) -> list[tuple[str, str, str, str]]:
        return [tuple(row) for row in self._store]

    # ---- build --------------------------------------------------------------

    def _rebuild(self) -> None:
        self._store.clear()
        node = self._node
        model = self._model
        if node is None or model is None:
            return
        base = node.path()
        entries: list[tuple[int, int, float, str]] = []
        for descendant in node.walk():
            owner_path = descendant.path().rstrip("/")
            for top_file in descendant.top_files:
                entries.append(
                    (top_file.alloc, top_file.size, top_file.mtime, f"{owner_path}/{top_file.name}")
                )
        largest = heapq.nlargest(_MAX_ROWS, entries, key=lambda entry: entry[0])
        for alloc, _size, mtime, full_path in largest:
            rel_path = os.path.relpath(full_path, base)
            modified = format_date(mtime) if mtime > 0 else ""
            self._store.append([rel_path, model.fmt_bytes(alloc), modified, full_path])

    def _size_cell_data(
        self, _column: Gtk.TreeViewColumn, cell: Gtk.CellRenderer, model, it, _data: object
    ) -> None:
        index = model.get_path(it).get_indices()[0]
        if index < _ACCENT_ROWS:
            cell.set_property("foreground", self._theme.accent)
            cell.set_property("foreground-set", True)
        else:
            cell.set_property("foreground-set", False)

    def _on_row_activated(
        self, _view: Gtk.TreeView, path: Gtk.TreePath, _column: Gtk.TreeViewColumn
    ) -> None:
        it = self._store.get_iter(path)
        abs_path = self._store.get_value(it, COL_ABS_PATH)
        self.emit("file-activated", abs_path)
