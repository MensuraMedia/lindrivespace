"""The Explorer tree-table: a ``Gtk.TreeView`` wrapped in its own scrolling,
reorderable/resizable/hideable columns, lazy expansion and header-click sort.

The view never touches ``FsNode`` totals directly — every cell is filled by
``ScanTreeModel.cell_data_func`` at draw time (see ``models/tree_model.py``).
This widget only owns column chrome and persistence of the user's layout
choices (order, widths, visibility, sort) in ``Settings``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GLib, GObject, Gtk, Pango  # noqa: E402

from lindrivespace.config.settings import Settings  # noqa: E402
from lindrivespace.config.theme import ThemeDefinition  # noqa: E402
from lindrivespace.models.tree_model import SORT_COLUMNS, FileRow, ScanTreeModel  # noqa: E402
from lindrivespace.ui.widgets.percent_bar_renderer import PercentBarRenderer  # noqa: E402

if TYPE_CHECKING:
    from lindrivespace.core.fsnode import FsNode

# id, header title, cell_data_func kind, xalign, default width (px), hideable
COLUMN_DEFS: tuple[tuple[str, str, str, float, int, bool], ...] = (
    ("name", "Name", "name", 0.0, 280, False),
    ("size", "Size", "size", 1.0, 90, True),
    ("alloc", "Allocated", "alloc", 1.0, 90, True),
    ("files", "Files", "files", 1.0, 80, True),
    ("dirs", "Folders", "dirs", 1.0, 80, True),
    ("percent", "Share %", "percent", 1.0, 160, True),
    ("modified", "Modified", "modified", 0.0, 100, True),
    ("owner", "Owner", "owner", 0.0, 100, True),
    ("type", "Type", "type", 0.0, 80, True),
)
DEFAULT_ORDER: tuple[str, ...] = tuple(c[0] for c in COLUMN_DEFS)
DEFAULT_WIDTHS: dict[str, int] = {c[0]: c[4] for c in COLUMN_DEFS}
# Kept in sync with config.settings.DEFAULTS["explorer"]["hidden_columns"] by convention.
_DEFAULT_HIDDEN: frozenset[str] = frozenset({"owner", "type"})
_MIN_WIDTH = 48
_NAME_SIZE_WIDTH = 72


class ExplorerTree(Gtk.ScrolledWindow):
    """Scrollable, lazily-populated tree-table over a :class:`ScanTreeModel`."""

    __gtype_name__ = "LdsExplorerTree"
    __gsignals__ = {
        "node-selected": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "file-selected": (GObject.SignalFlags.RUN_FIRST, None, (object,)),  # FileRow or None
        "file-activated": (GObject.SignalFlags.RUN_FIRST, None, (str,)),  # path
        "context-requested": (GObject.SignalFlags.RUN_FIRST, None, (object, int, int, object)),
    }

    def __init__(self, theme: ThemeDefinition, model: ScanTreeModel, settings: Settings) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.theme = theme
        self.model = model
        self.settings = settings

        self._columns: dict[str, Gtk.TreeViewColumn] = {}
        self._known_widths: dict[str, int] = {}
        self._loading = False
        self._order_save_pending = False

        self.treeview = Gtk.TreeView(model=model.store)
        self.treeview.set_fixed_height_mode(True)
        self.treeview.set_enable_tree_lines(False)
        self.treeview.set_headers_clickable(True)
        self.treeview.set_headers_visible(True)
        self.treeview.set_enable_search(True)
        self.treeview.set_search_column(int(_col_name_index()))
        self.add(self.treeview)

        self._build_columns()

        self.treeview.connect("row-expanded", self._on_row_expanded)
        self.treeview.connect("test-expand-row", self._on_test_expand_row)
        self.treeview.connect("row-activated", self._on_row_activated)
        self.treeview.connect("button-press-event", self._on_button_press)
        self.treeview.connect("columns-changed", self._on_columns_changed)

        self.selection = self.treeview.get_selection()
        self.selection.set_mode(Gtk.SelectionMode.SINGLE)
        self.selection.connect("changed", self._on_selection_changed)

        self.restore_state()

    # ------------------------------------------------------------- columns

    def _build_columns(self) -> None:
        for cid, title, kind, xalign, width, _hideable in COLUMN_DEFS:
            if cid == "name":
                column = self._build_name_column(title)
            elif kind == "percent":
                column = self._build_percent_column(title)
            else:
                column = self._build_text_column(title, kind, xalign)

            column._lds_id = cid  # type: ignore[attr-defined]
            column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            column.set_resizable(True)
            column.set_reorderable(True)
            column.set_min_width(_MIN_WIDTH)
            column.set_fixed_width(width)
            if cid in SORT_COLUMNS:
                column.set_clickable(True)
                column.connect("clicked", self._on_header_clicked)

            self.treeview.append_column(column)
            if cid == "name":
                # Must happen after the column is attached to the tree view.
                self.treeview.set_expander_column(column)
            self._columns[cid] = column
            self._known_widths[cid] = width
            column.connect("notify::width", self._on_width_changed, cid)
            self._attach_header_context_menu(column)

    def _build_name_column(self, title: str) -> Gtk.TreeViewColumn:
        column = Gtk.TreeViewColumn(title=title)

        icon_renderer = Gtk.CellRendererPixbuf()
        column.pack_start(icon_renderer, False)
        column.set_cell_data_func(icon_renderer, self.model.cell_data_func("icon"))

        size_renderer = Gtk.CellRendererText()
        size_renderer.set_property("xalign", 1.0)
        size_renderer.set_fixed_size(_NAME_SIZE_WIDTH, -1)
        r, g, b, a = self.theme.rgba("fg_muted", 1.0)
        size_renderer.set_property("foreground-rgba", Gdk.RGBA(red=r, green=g, blue=b, alpha=a))
        column.pack_start(size_renderer, False)
        column.set_cell_data_func(size_renderer, self.model.cell_data_func("name_size"))

        name_renderer = Gtk.CellRendererText()
        name_renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        column.pack_start(name_renderer, True)
        column.set_cell_data_func(name_renderer, self.model.cell_data_func("name"))

        return column

    def _build_percent_column(self, title: str) -> Gtk.TreeViewColumn:
        column = Gtk.TreeViewColumn(title=title)
        renderer = PercentBarRenderer(self.theme)
        column.pack_start(renderer, True)
        column.set_cell_data_func(renderer, self.model.cell_data_func("percent"))
        return column

    def _build_text_column(self, title: str, kind: str, xalign: float) -> Gtk.TreeViewColumn:
        column = Gtk.TreeViewColumn(title=title)
        renderer = Gtk.CellRendererText()
        renderer.set_property("xalign", xalign)
        column.pack_start(renderer, True)
        column.set_cell_data_func(renderer, self.model.cell_data_func(kind))
        return column

    def get_column(self, col_id: str) -> Gtk.TreeViewColumn | None:
        return self._columns.get(col_id)

    # ---------------------------------------------------------------- sort

    def _on_header_clicked(self, column: Gtk.TreeViewColumn) -> None:
        col_id = column._lds_id  # type: ignore[attr-defined]
        if self.model.sort_column == col_id:
            descending = not self.model.sort_descending
        else:
            descending = col_id != "name"
        self.model.set_sort(col_id, descending)
        self._update_sort_indicators()
        self._persist_sort()

    def _update_sort_indicators(self) -> None:
        for cid, column in self._columns.items():
            if cid == self.model.sort_column:
                column.set_sort_indicator(True)
                order = (
                    Gtk.SortType.DESCENDING
                    if self.model.sort_descending
                    else Gtk.SortType.ASCENDING
                )
                column.set_sort_order(order)
            else:
                column.set_sort_indicator(False)

    def _persist_sort(self) -> None:
        if self._loading:
            return
        self.settings.set(
            "explorer.sort",
            {"column": self.model.sort_column, "descending": self.model.sort_descending},
        )

    # ---------------------------------------------------------- visibility

    def _attach_header_context_menu(self, column: Gtk.TreeViewColumn) -> None:
        button = column.get_button()
        if button is not None and column.get_title() == "Share %":
            button.set_tooltip_text(
                "Share of the parent folder's size (allocated or apparent, per the toolbar toggle)"
            )
        if button is not None:
            button.connect("button-press-event", self._on_header_button_press)

    def _on_header_button_press(self, _widget: Gtk.Widget, event: Gdk.EventButton) -> bool:
        if event.button != 3:
            return False
        menu = self._build_column_menu()
        menu.popup_at_pointer(event)
        return True

    def show_column_menu(self, anchor: Gtk.Widget | None = None) -> None:
        """Open the column visibility menu (toolbar button / row context menu)."""
        menu = self._build_column_menu()
        self._column_menu = menu  # keep a reference while it is open
        if anchor is not None:
            menu.popup_at_widget(anchor, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)
        else:
            menu.popup_at_pointer(None)

    def _build_column_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()
        for cid, title, _kind, _xalign, _width, hideable in COLUMN_DEFS:
            if not hideable:
                continue
            item = Gtk.CheckMenuItem(label=title)
            item.set_active(self._columns[cid].get_visible())
            item.connect("toggled", self._on_visibility_toggled, cid)
            menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())
        reset_item = Gtk.MenuItem(label="Reset columns")
        reset_item.connect("activate", lambda _i: self.reset_columns())
        menu.append(reset_item)
        menu.show_all()
        return menu

    def _on_visibility_toggled(self, item: Gtk.CheckMenuItem, cid: str) -> None:
        self.set_column_visible(cid, item.get_active())

    def set_column_visible(self, col_id: str, visible: bool) -> None:
        column = self._columns.get(col_id)
        if column is None or col_id == "name":
            return
        column.set_visible(visible)
        if self._loading:
            return
        hidden = [cid for cid, c in self._columns.items() if not c.get_visible()]
        self.settings.set("explorer.hidden_columns", hidden)

    # --------------------------------------------------------------- order

    def _on_columns_changed(self, _treeview: Gtk.TreeView) -> None:
        if self._loading or self._order_save_pending:
            return
        self._order_save_pending = True
        GLib.idle_add(self._save_order_idle)

    def _save_order_idle(self) -> bool:
        self._order_save_pending = False
        order = [c._lds_id for c in self.treeview.get_columns()]  # type: ignore[attr-defined]
        self.settings.set("explorer.columns", order)
        return False

    def move_column_to(self, col_id: str, index: int) -> None:
        """Move column ``col_id`` to position ``index`` among the others (0-based)."""
        column = self._columns.get(col_id)
        if column is None:
            return
        others = [c for c in self.treeview.get_columns() if c is not column]
        index = max(0, min(index, len(others)))
        after = None if index == 0 else others[index - 1]
        self.treeview.move_column_after(column, after)

    def _apply_order(self, order: list[str]) -> None:
        prev: Gtk.TreeViewColumn | None = None
        for cid in order:
            column = self._columns.get(cid)
            if column is None:
                continue
            self.treeview.move_column_after(column, prev)
            prev = column

    def _apply_widths(self, widths: dict[str, int]) -> None:
        for cid, column in self._columns.items():
            width = int(widths.get(cid, DEFAULT_WIDTHS[cid]))
            column.set_fixed_width(width)
            self._known_widths[cid] = width

    def _apply_visibility(self, hidden: set[str]) -> None:
        for cid, column in self._columns.items():
            column.set_visible(cid == "name" or cid not in hidden)

    def _on_width_changed(
        self, column: Gtk.TreeViewColumn, _pspec: GObject.ParamSpec, cid: str
    ) -> None:
        if self._loading:
            return
        new_width = column.get_width()
        if new_width <= 0:
            return
        last = self._known_widths.get(cid)
        self._known_widths[cid] = new_width
        if last is not None and last != new_width:
            widths = dict(self.settings.get("explorer.widths", {}) or {})
            widths[cid] = new_width
            self.settings.set("explorer.widths", widths)

    # ----------------------------------------------------------- state I/O

    def save_state(self) -> None:
        order = [c._lds_id for c in self.treeview.get_columns()]  # type: ignore[attr-defined]
        self.settings.set("explorer.columns", order)
        widths = {cid: col.get_width() for cid, col in self._columns.items() if col.get_width() > 0}
        if widths:
            self.settings.set("explorer.widths", widths)
        hidden = [cid for cid, col in self._columns.items() if not col.get_visible()]
        self.settings.set("explorer.hidden_columns", hidden)
        self._persist_sort_unconditional()

    def _persist_sort_unconditional(self) -> None:
        self.settings.set(
            "explorer.sort",
            {"column": self.model.sort_column, "descending": self.model.sort_descending},
        )

    def restore_state(self) -> None:
        self._loading = True
        try:
            order = list(
                self.settings.get("explorer.columns", list(DEFAULT_ORDER)) or DEFAULT_ORDER
            )
            order += [cid for cid in DEFAULT_ORDER if cid not in order]
            self._apply_order(order)

            widths = dict(self.settings.get("explorer.widths", {}) or {})
            self._apply_widths(widths)

            hidden = set(self.settings.get("explorer.hidden_columns", list(_DEFAULT_HIDDEN)) or [])
            self._apply_visibility(hidden)

            sort = self.settings.get("explorer.sort", {}) or {}
            column = sort.get("column", self.model.sort_column)
            descending = bool(sort.get("descending", self.model.sort_descending))
            if column in SORT_COLUMNS:
                self.model.set_sort(column, descending)
        finally:
            self._loading = False
        self._update_sort_indicators()

    def reset_columns(self) -> None:
        self._loading = True
        try:
            self._apply_order(list(DEFAULT_ORDER))
            self._apply_widths({})
            self._apply_visibility(set(_DEFAULT_HIDDEN))
        finally:
            self._loading = False
        self.save_state()

    # -------------------------------------------------------------- expand

    def _on_row_expanded(
        self, _treeview: Gtk.TreeView, it: Gtk.TreeIter, _path: Gtk.TreePath
    ) -> None:
        self.model.populate(it)

    def _on_test_expand_row(
        self, _treeview: Gtk.TreeView, _it: Gtk.TreeIter, _path: Gtk.TreePath
    ) -> bool:
        return False

    def _on_row_activated(
        self, treeview: Gtk.TreeView, path: Gtk.TreePath, _column: Gtk.TreeViewColumn
    ) -> None:
        it = self.model.store.get_iter(path)
        if self.model.is_file_row(it):
            row = self.model.row_for_iter(it)
            if row is not None and not getattr(row, "is_summary", False):
                self.emit("file-activated", row.path())
            return
        if treeview.row_expanded(path):
            treeview.collapse_row(path)
        else:
            treeview.expand_row(path, False)

    def refresh(self) -> None:
        self.treeview.queue_draw()

    # ------------------------------------------------------------ selection

    def get_selected_node(self) -> FsNode | None:
        _model, it = self.selection.get_selected()
        if it is None:
            return None
        return self.model.node_for_iter(it)

    def get_selected_row(self) -> object | None:
        """The selected folder or file row (FsNode | FileRow | None)."""
        selection = self.treeview.get_selection()
        model, it = selection.get_selected()
        if it is None:
            return None
        return self.model.row_for_iter(it)

    def _on_selection_changed(self, _selection: Gtk.TreeSelection) -> None:
        row = self.get_selected_row()
        is_file = isinstance(row, FileRow)
        self.emit("file-selected", row if is_file else None)
        self.emit("node-selected", self.get_selected_node())

    def select_node(self, node: FsNode) -> None:
        it = self.model.reveal(node)
        if it is None:
            return
        path = self.model.store.get_path(it)
        self.treeview.expand_to_path(path)
        self.selection.select_iter(it)
        self.treeview.scroll_to_cell(path, None, True, 0.5, 0.0)

    # -------------------------------------------------------------- context

    def _on_button_press(self, treeview: Gtk.TreeView, event: Gdk.EventButton) -> bool:
        if event.button != 3:
            return False
        result = treeview.get_path_at_pos(int(event.x), int(event.y))
        if result is None:
            return False
        path, column, _cell_x, _cell_y = result
        treeview.set_cursor(path, column, False)
        it = self.model.store.get_iter(path)
        node = self.model.node_for_iter(it)
        self.emit("context-requested", node, int(event.x), int(event.y), event)
        return True


def _col_name_index() -> int:
    from lindrivespace.models.tree_model import Col

    return int(Col.NAME)
