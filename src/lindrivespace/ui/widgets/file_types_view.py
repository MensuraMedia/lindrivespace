"""FileTypesView — allocation share by file type (WP9 insight panel).

Data comes from ``core.classify.summarize_top_files``, an estimate bounded by
each directory's ``top_files`` ring (see that function's docstring); the
footnote reminding the user of that estimate lives in the panel container,
not here, since this widget is the bare ``Gtk.TreeView``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from lindrivespace.config.theme import ThemeDefinition  # noqa: E402
from lindrivespace.core.classify import class_label, class_order, summarize_top_files  # noqa: E402
from lindrivespace.core.units import format_count  # noqa: E402
from lindrivespace.ui.widgets.percent_bar_renderer import PercentBarRenderer  # noqa: E402

if TYPE_CHECKING:
    from lindrivespace.core.fsnode import FsNode
    from lindrivespace.models.tree_model import ScanTreeModel

COL_LABEL, COL_FILES, COL_ALLOC_TEXT, COL_PERCENT, COL_PERCENT_TEXT = range(5)


class FileTypesView(Gtk.TreeView):
    """Allocation breakdown by :class:`~lindrivespace.core.classify.FileClass`."""

    __gtype_name__ = "LdsFileTypesView"

    def __init__(self, theme: ThemeDefinition) -> None:
        self._store = Gtk.ListStore(str, str, str, float, str)
        super().__init__(model=self._store)
        self._theme = theme
        self._node: FsNode | None = None
        self._model: ScanTreeModel | None = None
        self._dirty = True

        self.set_headers_visible(True)
        self.set_fixed_height_mode(True)

        type_col = Gtk.TreeViewColumn("Type")
        type_col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        type_col.set_expand(True)
        type_renderer = Gtk.CellRendererText()
        type_col.pack_start(type_renderer, True)
        type_col.add_attribute(type_renderer, "text", COL_LABEL)
        self.append_column(type_col)

        files_col = Gtk.TreeViewColumn("Files")
        files_col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        files_col.set_fixed_width(56)
        files_renderer = Gtk.CellRendererText()
        files_renderer.set_property("xalign", 1.0)
        files_col.pack_start(files_renderer, False)
        files_col.add_attribute(files_renderer, "text", COL_FILES)
        self.append_column(files_col)

        alloc_col = Gtk.TreeViewColumn("Allocated")
        alloc_col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        alloc_col.set_fixed_width(76)
        alloc_renderer = Gtk.CellRendererText()
        alloc_renderer.set_property("xalign", 1.0)
        alloc_col.pack_start(alloc_renderer, False)
        alloc_col.add_attribute(alloc_renderer, "text", COL_ALLOC_TEXT)
        self.append_column(alloc_col)

        share_col = Gtk.TreeViewColumn("Share")
        share_col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        share_col.set_fixed_width(100)
        self._share_renderer = PercentBarRenderer(theme)
        share_col.pack_start(self._share_renderer, False)
        share_col.add_attribute(self._share_renderer, "percent", COL_PERCENT)
        share_col.add_attribute(self._share_renderer, "text", COL_PERCENT_TEXT)
        self.append_column(share_col)

    # ---- theme / data -----------------------------------------------------

    def set_theme(self, theme: ThemeDefinition) -> None:
        self._theme = theme
        self._share_renderer.set_theme(theme)
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
    def rows(self) -> list[tuple[str, str, str, float, str]]:
        return [tuple(row) for row in self._store]

    # ---- build --------------------------------------------------------------

    def _rebuild(self) -> None:
        self._store.clear()
        node = self._node
        model = self._model
        if node is None or model is None:
            return
        totals = summarize_top_files(node)
        grand_total = sum(alloc for _count, alloc in totals.values()) or 1
        for file_class in class_order():
            counted = totals.get(file_class)
            if not counted:
                continue
            count, alloc = counted
            percent = alloc * 100.0 / grand_total
            self._store.append(
                [
                    class_label(file_class),
                    format_count(count),
                    model.fmt_bytes(alloc),
                    percent,
                    f"{percent:.1f} %",
                ]
            )
