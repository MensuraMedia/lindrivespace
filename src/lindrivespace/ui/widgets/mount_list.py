"""MountList — the Overview's list view: one sortable row per mount, disks as section rows.

Columns: Mount (with PRIMARY / SECONDARY badge text) · Device · Type · Used · Free ·
Total · Used % (inline bar) · Scanned · ★. Disks are parent rows of a TreeStore so
sorting by a column keeps mounts under their disk. Double-click / Enter or the
context menu scans a mount; clicking the star toggles the favourite.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import IntEnum

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GObject, Gtk, Pango  # noqa: E402

from lindrivespace.config.layout import Layout  # noqa: E402
from lindrivespace.config.theme import ThemeDefinition  # noqa: E402
from lindrivespace.ui.widgets.mount_card import MountCardData  # noqa: E402
from lindrivespace.ui.widgets.percent_bar_renderer import PercentBarRenderer  # noqa: E402

_DIMS = Layout.dimensions


class Col(IntEnum):
    KIND = 0  # "disk" | "mount"
    KEY = 1  # disk kname or mountpoint
    TITLE = 2
    DEVICE = 3
    FSTYPE = 4
    USED = 5
    FREE = 6
    TOTAL = 7
    PERCENT = 8
    SCANNED = 9
    FAVORITE = 10
    ROLE = 11
    STATE = 12  # scan state for mounts
    WEIGHT = 13


COLUMN_TYPES = (
    str,
    str,
    str,
    str,
    str,
    GObject.TYPE_INT64,
    GObject.TYPE_INT64,
    GObject.TYPE_INT64,
    float,
    str,
    bool,
    str,
    str,
    int,
)


class MountList(Gtk.ScrolledWindow):
    __gtype_name__ = "LdsMountList"
    __gsignals__ = {
        "scan-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "favorite-toggled": (GObject.SignalFlags.RUN_FIRST, None, (str, bool)),
        "mount-selected": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "open-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "role-requested": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),  # mountpoint, role
    }

    def __init__(self, theme: ThemeDefinition, fmt_bytes: Callable[[int], str]) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.theme = theme
        self.fmt_bytes = fmt_bytes
        self.store = Gtk.TreeStore(*COLUMN_TYPES)
        self.view = Gtk.TreeView(model=self.store)
        self.view.set_headers_clickable(True)
        self.view.set_enable_tree_lines(False)
        self.view.set_show_expanders(False)
        self.view.set_level_indentation(0)
        self.view.get_style_context().add_class("grid-table")
        self.view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
        self.view.set_search_column(int(Col.TITLE))
        self._iters: dict[str, Gtk.TreeIter] = {}
        self._build_columns()
        self.view.connect("row-activated", self._on_row_activated)
        self.view.connect("button-press-event", self._on_button_press)
        self.view.get_selection().connect("changed", self._on_selection_changed)
        self.add(self.view)
        self.set_size_request(-1, 120)

    # ---- columns ----------------------------------------------------------------

    def _text_col(
        self, title: str, kind: str, *, xalign: float = 0.0, width: int = 90, expand: bool = False
    ) -> Gtk.TreeViewColumn:
        column = Gtk.TreeViewColumn(title=title)
        renderer = Gtk.CellRendererText()
        renderer.set_property("xalign", xalign)
        renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        column.pack_start(renderer, True)
        column.set_cell_data_func(renderer, self._cell_func, kind)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column.set_fixed_width(width)
        column.set_expand(expand)
        column.set_resizable(True)
        column.set_alignment(xalign)
        return column

    def _build_columns(self) -> None:
        mount_col = self._text_col("Mount", "title", width=220, expand=True)
        mount_col.set_sort_column_id(int(Col.TITLE))
        self.view.append_column(mount_col)
        self.view.set_expander_column(mount_col)

        for title, kind, col_id, xalign, width in (
            ("Device", "device", Col.DEVICE, 0.0, 100),
            ("Type", "fstype", Col.FSTYPE, 0.0, 62),
            ("Used", "used", Col.USED, 1.0, 82),
            ("Free", "free", Col.FREE, 1.0, 82),
            ("Total", "total", Col.TOTAL, 1.0, 82),
        ):
            column = self._text_col(title, kind, xalign=xalign, width=width)
            column.set_sort_column_id(int(col_id))
            self.view.append_column(column)

        bar_col = Gtk.TreeViewColumn(title="Used %")
        self.bar_renderer = PercentBarRenderer(self.theme)
        bar_col.pack_start(self.bar_renderer, True)
        bar_col.set_cell_data_func(self.bar_renderer, self._bar_func)
        bar_col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        bar_col.set_fixed_width(150)
        bar_col.set_resizable(True)
        bar_col.set_sort_column_id(int(Col.PERCENT))
        self.view.append_column(bar_col)

        scanned_col = self._text_col("Scanned", "scanned", width=150)
        scanned_col.set_sort_column_id(int(Col.SCANNED))
        self.view.append_column(scanned_col)

        star_col = Gtk.TreeViewColumn(title="")
        self.star_renderer = Gtk.CellRendererPixbuf()
        star_col.pack_start(self.star_renderer, False)
        star_col.set_cell_data_func(self.star_renderer, self._star_func)
        star_col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        star_col.set_fixed_width(32)
        self.view.append_column(star_col)
        self.star_column = star_col

        # Default order is the registry's (primary, secondary, then the rest);
        # clicking a header sorts within each disk.

    # ---- cell functions ---------------------------------------------------------

    def _cell_func(self, _col, cell, model, it, kind: str) -> None:  # type: ignore[no-untyped-def]
        is_disk = model.get_value(it, Col.KIND) == "disk"
        cell.set_property("weight", model.get_value(it, Col.WEIGHT))
        cell.set_property("foreground-rgba", None)
        if is_disk:
            if kind == "title":
                detail = model.get_value(it, Col.DEVICE)
                title = model.get_value(it, Col.TITLE)
                cell.set_property("text", f"{title}   ·   {detail}" if detail else title)
                cell.set_property("weight", 500)
            else:
                cell.set_property("text", "")
            return
        if kind == "title":
            role = model.get_value(it, Col.ROLE)
            text = model.get_value(it, Col.TITLE)
            cell.set_property("text", f"{text}   {role.upper()}" if role else text)
        elif kind in ("used", "free", "total"):
            col = {"used": Col.USED, "free": Col.FREE, "total": Col.TOTAL}[kind]
            cell.set_property("text", self.fmt_bytes(int(model.get_value(it, col))))
        elif kind == "device":
            cell.set_property("text", model.get_value(it, Col.DEVICE))
        elif kind == "fstype":
            cell.set_property("text", model.get_value(it, Col.FSTYPE))
        elif kind == "scanned":
            cell.set_property("text", model.get_value(it, Col.SCANNED))
            r, g, b, a = self.theme.rgba("fg_dim", 1.0)
            cell.set_property("foreground-rgba", Gdk.RGBA(red=r, green=g, blue=b, alpha=a))

    def _bar_func(self, _col, cell, model, it, _data=None) -> None:  # type: ignore[no-untyped-def]
        if model.get_value(it, Col.KIND) == "disk":
            cell.set_property("visible", False)
            return
        cell.set_property("visible", True)
        pct = float(model.get_value(it, Col.PERCENT))
        cell.set_property("percent", pct)
        cell.set_property("text", f"{pct:.0f} %")
        cell.set_property("emphasis", pct >= 85.0)

    def _star_func(self, _col, cell, model, it, _data=None) -> None:  # type: ignore[no-untyped-def]
        if model.get_value(it, Col.KIND) == "disk":
            cell.set_property("icon-name", "")
            return
        fav = bool(model.get_value(it, Col.FAVORITE))
        cell.set_property("icon-name", "starred-symbolic" if fav else "non-starred-symbolic")

    # ---- data -------------------------------------------------------------------

    def set_data(
        self,
        groups: list[tuple[str, str, list[MountCardData]]],
        hidden: list[MountCardData],
    ) -> None:
        """``groups``: (disk kname, disk detail text, mounts); ``hidden``: compact group."""
        self.store.clear()
        self._iters.clear()
        for kname, detail, mounts in groups:
            parent = self.store.append(None, self._disk_row(kname, detail))
            for data in mounts:
                self._iters[data.mountpoint] = self.store.append(parent, self._mount_row(data))
        if hidden:
            parent = self.store.append(
                None,
                self._disk_row(
                    "hidden & virtual",
                    f"{len(hidden)} mounts · snap loops, tmpfs, pseudo filesystems",
                ),
            )
            for data in hidden:
                self._iters[data.mountpoint] = self.store.append(parent, self._mount_row(data))
        self.view.expand_all()

    def update_mount(self, data: MountCardData) -> None:
        it = self._iters.get(data.mountpoint)
        if it is None:
            return
        row = self._mount_row(data)
        self.store.set(it, list(range(len(row))), row)

    @staticmethod
    def _disk_row(kname: str, detail: str) -> list[object]:
        return ["disk", kname, kname, detail, "", 0, 0, 0, 0.0, "", False, "", "", 500]

    @staticmethod
    def _mount_row(d: MountCardData) -> list[object]:
        total = max(0, d.total)
        pct = (d.used * 100.0 / total) if total else 0.0
        if d.scan_state == "scanning":
            scanned = "scanning…"
        elif d.scan_state == "queued":
            scanned = "queued"
        elif d.scanned_at:
            scanned = f"{d.scanned_at}" + (f" · {d.scan_detail}" if d.scan_detail else "")
        else:
            scanned = "not scanned"
        device = f"{d.device}"
        return [
            "mount",
            d.mountpoint,
            d.mountpoint,
            device,
            d.fstype,
            int(d.used),
            int(max(0, total - d.used)),
            int(total),
            pct,
            scanned,
            bool(d.favorite),
            d.role if hasattr(d, "role") else "",
            d.scan_state,
            400,
        ]

    def selected_mountpoint(self) -> str | None:
        _model, it = self.view.get_selection().get_selected()
        if it is None or self.store.get_value(it, Col.KIND) != "mount":
            return None
        return str(self.store.get_value(it, Col.KEY))

    def select_mountpoint(self, mountpoint: str) -> None:
        it = self._iters.get(mountpoint)
        if it is not None:
            self.view.get_selection().select_iter(it)

    # ---- interaction ------------------------------------------------------------

    def _on_row_activated(self, _view: Gtk.TreeView, path: Gtk.TreePath, _column: object) -> None:
        it = self.store.get_iter(path)
        if self.store.get_value(it, Col.KIND) == "mount":
            self.emit("scan-requested", self.store.get_value(it, Col.KEY))

    def _on_selection_changed(self, _selection: Gtk.TreeSelection) -> None:
        mp = self.selected_mountpoint()
        if mp:
            self.emit("mount-selected", mp)

    def _on_button_press(self, view: Gtk.TreeView, event: Gdk.EventButton) -> bool:
        hit = view.get_path_at_pos(int(event.x), int(event.y))
        if hit is None:
            return False
        path, column, _cx, _cy = hit
        it = self.store.get_iter(path)
        if self.store.get_value(it, Col.KIND) != "mount":
            return False
        mountpoint = str(self.store.get_value(it, Col.KEY))
        if event.button == 1 and column is self.star_column:
            new_state = not bool(self.store.get_value(it, Col.FAVORITE))
            self.store.set_value(it, Col.FAVORITE, new_state)
            self.emit("favorite-toggled", mountpoint, new_state)
            return True
        if event.button == 3:
            view.get_selection().select_iter(it)
            self._popup_menu(it, mountpoint, event)
            return True
        return False

    def _popup_menu(self, it: Gtk.TreeIter, mountpoint: str, event: Gdk.EventButton) -> None:
        menu = Gtk.Menu()
        scanned = bool(
            self.store.get_value(it, Col.SCANNED) not in ("not scanned", "queued", "scanning…")
        )
        fav = bool(self.store.get_value(it, Col.FAVORITE))
        role = str(self.store.get_value(it, Col.ROLE))
        items: list[tuple[str, Callable[[], None]]] = [
            ("Rescan" if scanned else "Scan", lambda: self.emit("scan-requested", mountpoint)),
            ("Open in file manager", lambda: self.emit("open-requested", mountpoint)),
            (
                "Remove from Favorites" if fav else "Add to Favorites",
                lambda: self.emit("favorite-toggled", mountpoint, not fav),
            ),
            (
                "Clear primary" if role == "primary" else "Set as primary mountpoint",
                lambda: self.emit(
                    "role-requested", mountpoint, "" if role == "primary" else "primary"
                ),
            ),
            (
                "Clear secondary" if role == "secondary" else "Set as secondary mountpoint",
                lambda: self.emit(
                    "role-requested", mountpoint, "" if role == "secondary" else "secondary"
                ),
            ),
        ]
        for label, handler in items:
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _i, h=handler: h())
            menu.append(item)
        menu.show_all()
        self._menu = menu  # keep alive while open
        menu.popup_at_pointer(event)
