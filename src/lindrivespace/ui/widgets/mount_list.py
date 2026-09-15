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
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GObject, Gtk, Pango, PangoCairo  # noqa: E402

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


class BadgeButtonRenderer(Gtk.CellRendererText):
    """Text renderer that draws an outlined "PRIMARY"-style badge after the name."""

    badge = GObject.Property(type=str, default="")

    def __init__(self, theme: ThemeDefinition) -> None:
        super().__init__()
        self.theme = theme

    def do_render(self, cr, widget, background_area, cell_area, flags) -> None:  # type: ignore[no-untyped-def]
        Gtk.CellRendererText.do_render(self, cr, widget, background_area, cell_area, flags)
        badge = self.get_property("badge")
        if not badge:
            return
        layout = widget.create_pango_layout(self.get_property("text") or "")
        layout.set_font_description(Pango.FontDescription("Ubuntu Bold 10.5"))
        text_w, _h = layout.get_pixel_size()
        blayout = widget.create_pango_layout(badge)
        blayout.set_font_description(Pango.FontDescription("Ubuntu Mono 7.5"))
        bw, bh = blayout.get_pixel_size()
        x = cell_area.x + self.get_property("xpad") + text_w + 10
        h = bh + 4
        y = cell_area.y + (cell_area.height - h) / 2
        w = bw + 12
        cr.save()
        cr.set_source_rgb(*self.theme.rgb("accent"))
        cr.set_line_width(1)
        cr.rectangle(x + 0.5, y + 0.5, w - 1, h - 1)
        cr.stroke()
        cr.move_to(x + 6, y + 2)
        PangoCairo.show_layout(cr, blayout)
        cr.restore()


class ButtonCellRenderer(Gtk.CellRenderer):
    """A button-looking cell ("Rescan" / "Scan"); clicks are resolved by the view."""

    label = GObject.Property(type=str, default="Scan")
    visible_button = GObject.Property(type=bool, default=True)

    def __init__(self, theme: ThemeDefinition) -> None:
        super().__init__()
        self.theme = theme
        self.set_property("xpad", 4)

    def do_get_preferred_width(self, _widget):  # type: ignore[no-untyped-def]
        return (72, 72)

    def do_get_preferred_height(self, _widget):  # type: ignore[no-untyped-def]
        return (28, 28)

    def do_render(self, cr, widget, _background_area, cell_area, _flags) -> None:  # type: ignore[no-untyped-def]
        if not self.get_property("visible_button"):
            return
        layout = widget.create_pango_layout(self.get_property("label"))
        layout.set_font_description(Pango.FontDescription("Ubuntu 9.5"))
        tw, th = layout.get_pixel_size()
        w = min(cell_area.width - 8, max(64, tw + 20))
        h = 24
        x = cell_area.x + 4
        y = cell_area.y + (cell_area.height - h) / 2
        cr.save()
        cr.set_source_rgb(*self.theme.rgb("bg_surface_2"))
        cr.rectangle(x, y, w, h)
        cr.fill()
        cr.set_source_rgb(*self.theme.rgb("line_soft"))
        cr.set_line_width(1)
        cr.rectangle(x + 0.5, y + 0.5, w - 1, h - 1)
        cr.stroke()
        cr.set_source_rgb(*self.theme.rgb("fg"))
        cr.move_to(x + (w - tw) / 2, y + (h - th) / 2)
        PangoCairo.show_layout(cr, layout)
        cr.restore()


class MountList(Gtk.ScrolledWindow):
    __gtype_name__ = "LdsMountList"
    __gsignals__ = {
        "scan-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "favorite-toggled": (GObject.SignalFlags.RUN_FIRST, None, (str, bool)),
        "mount-selected": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "open-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "role-requested": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),  # mountpoint, role
    }

    COLUMN_IDS = (
        "mount",
        "device",
        "fstype",
        "used",
        "free",
        "total",
        "percent",
        "scanned",
        "actions",
    )
    HIDEABLE = ("device", "fstype", "used", "free", "total", "percent", "scanned")

    def __init__(
        self,
        theme: ThemeDefinition,
        fmt_bytes: Callable[[int], str],
        settings: object | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self._columns: dict[str, Gtk.TreeViewColumn] = {}
        self._loading = False
        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.set_shadow_type(Gtk.ShadowType.IN)  # the cell border colour runs around the table
        self.get_style_context().add_class("mount-list-frame")
        self.theme = theme
        self.fmt_bytes = fmt_bytes
        self.store = Gtk.TreeStore(*COLUMN_TYPES)
        self.view = Gtk.TreeView(model=self.store)
        self.view.set_headers_clickable(True)
        self.view.set_enable_tree_lines(False)
        self.view.set_show_expanders(False)
        self.view.set_level_indentation(0)
        self.view.get_style_context().add_class("mount-list")
        self.view.set_grid_lines(Gtk.TreeViewGridLines.BOTH)
        self.view.set_search_column(int(Col.TITLE))
        self._iters: dict[str, Gtk.TreeIter] = {}
        self._build_columns()
        self._make_columns_user_configurable()
        self.restore_state()
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
        renderer.set_property("ypad", 7)
        renderer.set_property("xpad", 6)  # ~4 px extra side margin in every cell
        renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        if kind in ("device", "fstype"):
            renderer.set_property("family", self.theme.font_mono.split(",")[0])
        column.pack_start(renderer, True)
        column.set_cell_data_func(renderer, self._cell_func, kind)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column.set_fixed_width(width)
        column.set_expand(expand)
        column.set_resizable(True)
        column.set_alignment(xalign)
        return column

    def _build_columns(self) -> None:
        mount_col = Gtk.TreeViewColumn(title="Mount")
        self.title_renderer = BadgeButtonRenderer(self.theme)
        self.title_renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        self.title_renderer.set_property("ypad", 7)
        self.title_renderer.set_property("xpad", 6)
        mount_col.pack_start(self.title_renderer, True)
        mount_col.set_cell_data_func(self.title_renderer, self._cell_func, "title")
        mount_col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        mount_col.set_fixed_width(214)
        mount_col.set_expand(True)
        mount_col.set_resizable(True)
        mount_col.set_sort_column_id(int(Col.TITLE))
        self.view.append_column(mount_col)
        self.view.set_expander_column(mount_col)
        self._columns["mount"] = mount_col

        for title, kind, col_id, xalign, width in (
            ("Device", "device", Col.DEVICE, 0.0, 96),
            ("Type", "fstype", Col.FSTYPE, 0.0, 58),
            ("Used", "used", Col.USED, 1.0, 78),
            ("Free", "free", Col.FREE, 1.0, 78),
            ("Total", "total", Col.TOTAL, 1.0, 78),
        ):
            column = self._text_col(title, kind, xalign=xalign, width=width)
            column.set_sort_column_id(int(col_id))
            self.view.append_column(column)
            self._columns[kind] = column

        bar_col = Gtk.TreeViewColumn(title="Used %")
        self.bar_renderer = PercentBarRenderer(self.theme)
        self.bar_renderer.set_property("xpad", 6)
        bar_col.pack_start(self.bar_renderer, True)
        bar_col.set_cell_data_func(self.bar_renderer, self._bar_func)
        bar_col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        bar_col.set_fixed_width(136)
        bar_col.set_resizable(True)
        bar_col.set_sort_column_id(int(Col.PERCENT))
        self.view.append_column(bar_col)
        self._columns["percent"] = bar_col

        scanned_col = self._text_col("Scanned", "scanned", width=126)
        scanned_col.set_sort_column_id(int(Col.SCANNED))
        self.view.append_column(scanned_col)
        self._columns["scanned"] = scanned_col

        star_col = Gtk.TreeViewColumn(title="")
        self.star_renderer = Gtk.CellRendererPixbuf()
        self.star_renderer.set_property("xpad", 6)
        star_col.pack_start(self.star_renderer, False)
        star_col.set_cell_data_func(self.star_renderer, self._star_func)
        self.button_renderer = ButtonCellRenderer(self.theme)
        star_col.pack_start(self.button_renderer, False)
        star_col.set_cell_data_func(self.button_renderer, self._button_func)
        star_col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        star_col.set_fixed_width(104)
        self.view.append_column(star_col)
        self.star_column = star_col
        self._columns["actions"] = star_col

        # Default order is the registry's (primary, secondary, then the rest);
        # clicking a header sorts within each disk.

    # ---- user-configurable columns (same behaviour as the Explorer) ---------------

    _TITLES = {
        "mount": "Mount",
        "device": "Device",
        "fstype": "Type",
        "used": "Used",
        "free": "Free",
        "total": "Total",
        "percent": "Used %",
        "scanned": "Scanned",
        "actions": "Actions",
    }

    def _make_columns_user_configurable(self) -> None:
        for cid, column in self._columns.items():
            column.set_reorderable(True)
            column.set_resizable(cid != "actions")
            button = column.get_button()
            if button is not None:
                button.connect("button-press-event", self._on_header_button_press)
            column.connect("notify::width", self._on_column_width_changed, cid)
        self.view.connect("columns-changed", self._on_columns_changed)

    def _setting(self, key: str, default: object) -> object:
        get = getattr(self.settings, "get", None)
        return get(f"overview.{key}", default) if callable(get) else default

    def _persist(self, key: str, value: object) -> None:
        if self._loading or self.settings is None:
            return
        setter = getattr(self.settings, "set", None)
        if callable(setter):
            setter(f"overview.{key}", value)
            save = getattr(self.settings, "save", None)
            if callable(save):
                try:
                    save()
                except OSError:
                    pass

    def column_order(self) -> list[str]:
        ids = {column: cid for cid, column in self._columns.items()}
        return [ids[c] for c in self.view.get_columns() if c in ids]

    def move_column_to(self, cid: str, index: int) -> None:
        order = [c for c in self.column_order() if c != cid]
        index = max(0, min(index, len(order)))
        order.insert(index, cid)
        self._apply_order(order)
        self._on_columns_changed(self.view)

    def _apply_order(self, order: list[str]) -> None:
        prev: Gtk.TreeViewColumn | None = None
        for cid in order:
            column = self._columns.get(cid)
            if column is None:
                continue
            self.view.move_column_after(column, prev)
            prev = column

    def set_column_visible(self, cid: str, visible: bool) -> None:
        if cid not in self.HIDEABLE:
            return
        self._columns[cid].set_visible(visible)
        hidden = [c for c in self.HIDEABLE if not self._columns[c].get_visible()]
        self._persist("hidden_columns", hidden)

    def reset_columns(self) -> None:
        self._loading = True
        try:
            self._apply_order(list(self.COLUMN_IDS))
            for cid in self.HIDEABLE:
                self._columns[cid].set_visible(True)
        finally:
            self._loading = False
        self._persist("columns", list(self.COLUMN_IDS))
        self._persist("hidden_columns", [])
        self._persist("widths", {})

    def restore_state(self) -> None:
        self._loading = True
        try:
            order = self._setting("columns", list(self.COLUMN_IDS))
            if isinstance(order, list) and set(order) <= set(self.COLUMN_IDS):
                self._apply_order([c for c in order if c in self._columns])
            hidden = self._setting("hidden_columns", [])
            if isinstance(hidden, list):
                for cid in self.HIDEABLE:
                    self._columns[cid].set_visible(cid not in hidden)
            widths = self._setting("widths", {})
            if isinstance(widths, dict):
                for cid, width in widths.items():
                    if cid in self._columns and isinstance(width, int) and width >= 40:
                        self._columns[cid].set_fixed_width(width)
        finally:
            self._loading = False

    def _on_columns_changed(self, _view: Gtk.TreeView) -> None:
        if not self._loading and len(self.view.get_columns()) == len(self._columns):
            self._persist("columns", self.column_order())

    def _on_column_width_changed(
        self, column: Gtk.TreeViewColumn, _pspec: object, cid: str
    ) -> None:
        if self._loading:
            return
        widths = self._setting("widths", {})
        widths = dict(widths) if isinstance(widths, dict) else {}
        widths[cid] = int(column.get_width())
        self._persist("widths", widths)

    def _on_header_button_press(self, _button: Gtk.Widget, event: Gdk.EventButton) -> bool:
        if event.button != 3:
            return False
        menu = Gtk.Menu()
        for cid in self.HIDEABLE:
            item = Gtk.CheckMenuItem(label=self._TITLES[cid])
            item.set_active(self._columns[cid].get_visible())
            item.connect("toggled", lambda i, c=cid: self.set_column_visible(c, i.get_active()))
            menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())
        reset = Gtk.MenuItem(label="Reset columns")
        reset.connect("activate", lambda _i: self.reset_columns())
        menu.append(reset)
        menu.show_all()
        self._header_menu = menu
        menu.popup_at_pointer(event)
        return True

    # ---- cell functions ---------------------------------------------------------

    def _rgba(self, token: str) -> Gdk.RGBA:
        r, g, b, a = self.theme.rgba(token, 1.0)
        return Gdk.RGBA(red=r, green=g, blue=b, alpha=a)

    def _cell_func(self, _col, cell, model, it, kind: str) -> None:  # type: ignore[no-untyped-def]
        is_disk = model.get_value(it, Col.KIND) == "disk"
        cell.set_property("weight", model.get_value(it, Col.WEIGHT))
        cell.set_property("foreground-rgba", None)
        cell.set_property("cell-background-rgba", self._rgba("bg_surface") if is_disk else None)
        if cell.find_property("badge") is not None:
            cell.set_property("badge", "")
        if is_disk:
            if kind == "title":
                detail = model.get_value(it, Col.DEVICE)
                title = model.get_value(it, Col.TITLE)
                text = f"{title} · {detail}" if detail else title
                cell.set_property("text", text.upper())
                cell.set_property("weight", 700)
                cell.set_property("foreground-rgba", self._rgba("fg_muted"))
                cell.set_property("scale", 0.9)
            else:
                cell.set_property("text", "")
            return
        cell.set_property("scale", 1.0)
        if kind == "title":
            role = model.get_value(it, Col.ROLE)
            cell.set_property("text", model.get_value(it, Col.TITLE))
            cell.set_property("weight", 700)
            cell.set_property("badge", role.upper() if role else "")
        elif kind in ("used", "free", "total"):
            col = {"used": Col.USED, "free": Col.FREE, "total": Col.TOTAL}[kind]
            cell.set_property("text", self.fmt_bytes(int(model.get_value(it, col))))
        elif kind == "device":
            cell.set_property("text", model.get_value(it, Col.DEVICE))
        elif kind == "fstype":
            cell.set_property("text", model.get_value(it, Col.FSTYPE))
        elif kind == "scanned":
            cell.set_property("text", model.get_value(it, Col.SCANNED))
            cell.set_property("foreground-rgba", self._rgba("fg_dim"))

    def _bar_func(self, _col, cell, model, it, _data=None) -> None:  # type: ignore[no-untyped-def]
        is_disk = model.get_value(it, Col.KIND) == "disk"
        cell.set_property("cell-background-rgba", self._rgba("bg_surface") if is_disk else None)
        if is_disk:
            cell.set_property("visible", False)
            return
        cell.set_property("visible", True)
        pct = float(model.get_value(it, Col.PERCENT))
        cell.set_property("percent", pct)
        cell.set_property("text", " ")  # bar only, as in the mockup
        cell.set_property("emphasis", pct >= 85.0)

    def _star_func(self, _col, cell, model, it, _data=None) -> None:  # type: ignore[no-untyped-def]
        is_disk = model.get_value(it, Col.KIND) == "disk"
        cell.set_property("cell-background-rgba", self._rgba("bg_surface") if is_disk else None)
        if is_disk:
            cell.set_property("icon-name", "")
            return
        fav = bool(model.get_value(it, Col.FAVORITE))
        cell.set_property("icon-name", "starred-symbolic" if fav else "non-starred-symbolic")

    def _button_func(self, _col, cell, model, it, _data=None) -> None:  # type: ignore[no-untyped-def]
        is_disk = model.get_value(it, Col.KIND) == "disk"
        cell.set_property("cell-background-rgba", self._rgba("bg_surface") if is_disk else None)
        cell.set_property("visible_button", not is_disk)
        scanned = str(model.get_value(it, Col.SCANNED))
        state = str(model.get_value(it, Col.STATE))
        if state in ("scanning", "queued"):
            cell.set_property("label", "…")
        else:
            cell.set_property("label", "Scan" if scanned == "not scanned" else "Rescan")

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
            import time as _time

            stamp = d.scanned_at
            if stamp.startswith(_time.strftime("%Y-%m-%d")):
                stamp = stamp[11:] or stamp  # "06:27" for today's scans
            scanned = stamp + (f" · {d.scan_detail}" if d.scan_detail else "")
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
            found, x_off, width = column.cell_get_position(self.star_renderer)
            # cell_get_position is relative to the column; the cell area gives the column's x.
            rect = view.get_cell_area(path, column)
            local_x = int(event.x) - rect.x
            if found and local_x <= x_off + width:
                new_state = not bool(self.store.get_value(it, Col.FAVORITE))
                self.store.set_value(it, Col.FAVORITE, new_state)
                self.emit("favorite-toggled", mountpoint, new_state)
            else:
                self.emit("scan-requested", mountpoint)
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
