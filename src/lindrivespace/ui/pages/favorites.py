"""Favorites page: starred folders/files, one click from their space view.

A flat list of "card" rows (Direction B visual language: flat surfaces, a
mono dim path line, a light-weight metadata line) over
``services.favorites.FavoritesStore``. Activating a row asks the window to
scan the favorite (its own path for a folder, its parent for a file) --
that reopens the Explorer, which shows the treemap for whatever was scanned
in its insight panel. The store is shared with the Explorer's star action
(``services.favorites.get_store``), so a star toggled there is reflected
here via the store's ``changed`` signal, and vice versa.
"""

from __future__ import annotations

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from lindrivespace.config.layout import Layout  # noqa: E402
from lindrivespace.services.favorites import Favorite, get_store  # noqa: E402
from lindrivespace.ui.pages.base import BasePage  # noqa: E402

_EMPTY_TEXT = (
    "No favorites yet. In the Explorer, right-click a folder and choose "
    "Add to favorites, or press Ctrl+D."
)


def _open_in_file_manager(path: str) -> None:
    """Open ``path`` via ``services.actions`` when available, else fall back to
    ``Gio.AppInfo.launch_default_for_uri`` directly.

    ``services.actions`` is owned by another work package and may be mid-edit,
    so it's imported defensively -- a missing module or function must never
    break this button.
    """
    open_fn = None
    try:
        from lindrivespace.services import actions

        open_fn = getattr(actions, "open_in_file_manager", None)
    except ImportError:
        open_fn = None
    if callable(open_fn):
        if open_fn(path):
            return
    try:
        uri = GLib.filename_to_uri(str(path), None)
        Gio.AppInfo.launch_default_for_uri(uri, None)
    except (GLib.Error, ValueError, TypeError) as exc:
        print(f"favorites: could not open {path}: {exc}", file=sys.stderr)


class FavoritesPage(BasePage):
    title = "Favorites"

    def build_content(self) -> None:
        self.add_title(
            self.title, "Folders and files you starred. Click one to see its space view."
        )

        self.store = get_store(self.app)
        self.store.connect("changed", self._on_store_changed)
        self._rows_by_path: dict[str, Gtk.ListBoxRow] = {}

        self.empty_label = Gtk.Label(label=_EMPTY_TEXT)
        self.empty_label.get_style_context().add_class("dim")
        self.empty_label.set_line_wrap(True)
        self.empty_label.set_xalign(0.0)
        self.pack_start(self.empty_label, False, False, 0)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list_box.set_activate_on_single_click(True)
        self.list_box.connect("row-activated", self._on_row_activated)
        self.pack_start(self.list_box, True, True, 0)

        self.refresh()

    # ---- lifecycle ----------------------------------------------------------

    def on_shown(self) -> None:
        self.refresh()

    # ---- public API -----------------------------------------------------------

    def refresh(self) -> None:
        """Rebuild the row list from the store; called on ``changed`` and ``on_shown``."""
        favorites = self.store.list()

        for child in list(self.list_box.get_children()):
            self.list_box.remove(child)
        self._rows_by_path = {}

        total = len(favorites)
        for index, fav in enumerate(favorites):
            row = self._build_row(fav, index, total)
            self.list_box.add(row)
            self._rows_by_path[fav.path] = row

        # show_all() first: it recursively shows the (possibly freshly built)
        # list_box and its new rows, which would otherwise stomp the
        # visibility we're about to set on list_box itself when there are no
        # favorites.
        self.list_box.show_all()
        has_favorites = bool(favorites)
        self.empty_label.set_visible(not has_favorites)
        self.list_box.set_visible(has_favorites)

    # ---- row construction -----------------------------------------------------

    def _build_row(self, fav: Favorite, index: int, total: int) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.get_style_context().add_class("card")
        # A gap between rows so each favorite reads as its own flat card
        # (Direction B language) rather than one block with divider lines.
        row.set_margin_bottom(Layout.spacing.SM)
        row.favorite_path = fav.path  # type: ignore[attr-defined]

        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=Layout.spacing.MD)
        outer.set_margin_top(Layout.spacing.SM)
        outer.set_margin_bottom(Layout.spacing.SM)
        outer.set_margin_start(Layout.spacing.SM)
        outer.set_margin_end(Layout.spacing.SM)

        icon = Gtk.Image.new_from_icon_name("starred-symbolic", Gtk.IconSize.MENU)
        icon.set_valign(Gtk.Align.START)
        outer.pack_start(icon, False, False, 0)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.set_hexpand(True)

        label_stack, entry = self._build_label_and_entry(fav)
        row.label_stack = label_stack  # type: ignore[attr-defined]
        row.rename_entry = entry  # type: ignore[attr-defined]
        text_box.pack_start(label_stack, False, False, 0)

        path_label = Gtk.Label(label=fav.path)
        path_label.set_xalign(0.0)
        path_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        path_ctx = path_label.get_style_context()
        path_ctx.add_class("mono")
        path_ctx.add_class("dim")
        text_box.pack_start(path_label, False, False, 0)

        outer.pack_start(text_box, True, True, 0)
        outer.pack_start(self._build_meta_box(fav), False, False, 0)
        outer.pack_start(self._build_buttons_box(fav, index, total), False, False, 0)

        row.add(outer)
        return row

    def _build_label_and_entry(self, fav: Favorite) -> tuple[Gtk.Stack, Gtk.Entry]:
        label = Gtk.Label(label=fav.label)
        label.set_xalign(0.0)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_markup(f"<b>{GLib.markup_escape_text(fav.label)}</b>")

        label_event = Gtk.EventBox()
        label_event.add(label)
        label_event.connect("button-press-event", self._on_label_button_press, fav.path)

        entry = Gtk.Entry()
        entry.set_text(fav.label)
        entry.connect("activate", self._on_rename_entry_activate, fav.path)
        entry.connect("focus-out-event", self._on_rename_entry_focus_out, fav.path)

        stack = Gtk.Stack()
        stack.add_named(label_event, "label")
        stack.add_named(entry, "entry")
        stack.set_visible_child_name("label")
        return stack, entry

    def _build_meta_box(self, fav: Favorite) -> Gtk.Box:
        meta_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        meta_box.set_halign(Gtk.Align.END)

        scanned_at = self.window.scan_history.get(self.store.scan_target(fav))
        scanned_text = f"last scanned {scanned_at}" if scanned_at else "not scanned"
        scanned_label = Gtk.Label(label=scanned_text)
        scanned_label.set_xalign(1.0)
        scanned_label.get_style_context().add_class("dim")
        meta_box.pack_start(scanned_label, False, False, 0)

        # No size is known without scanning, and this page never triggers a
        # scan on its own -- left as an em dash until the Explorer scans it.
        size_label = Gtk.Label(label="—")
        size_label.set_xalign(1.0)
        size_ctx = size_label.get_style_context()
        size_ctx.add_class("mono")
        size_ctx.add_class("dim")
        meta_box.pack_start(size_label, False, False, 0)
        return meta_box

    def _build_buttons_box(self, fav: Favorite, index: int, total: int) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=Layout.spacing.XS)

        if index > 0:
            up = Gtk.Button.new_from_icon_name("go-up-symbolic", Gtk.IconSize.MENU)
            up.get_style_context().add_class("flat")
            up.set_tooltip_text("Move up")
            up.connect("clicked", self._on_move_clicked, fav.path, -1)
            box.pack_start(up, False, False, 0)
        if index < total - 1:
            down = Gtk.Button.new_from_icon_name("go-down-symbolic", Gtk.IconSize.MENU)
            down.get_style_context().add_class("flat")
            down.set_tooltip_text("Move down")
            down.connect("clicked", self._on_move_clicked, fav.path, 1)
            box.pack_start(down, False, False, 0)

        open_button = Gtk.Button(label="Open in file manager")
        open_button.get_style_context().add_class("flat")
        open_button.connect("clicked", self._on_open_clicked, fav.path)
        box.pack_start(open_button, False, False, 0)

        remove_button = Gtk.Button(label="Remove")
        remove_button.get_style_context().add_class("flat")
        remove_button.connect("clicked", self._on_remove_clicked, fav.path)
        box.pack_start(remove_button, False, False, 0)
        return box

    # ---- signal handlers --------------------------------------------------

    def _on_store_changed(self, _store: object) -> None:
        self.refresh()

    def _on_row_activated(self, _list_box: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        path = getattr(row, "favorite_path", None)
        if path is None:
            return
        fav = self.store.get(path)
        if fav is None:
            return
        self.window.request_scan(self.store.scan_target(fav))
        if not fav.is_dir:
            self.window.pending_reveal = fav.path  # type: ignore[attr-defined]

    def _on_open_clicked(self, _button: Gtk.Button, path: str) -> None:
        fav = self.store.get(path)
        target = self.store.scan_target(fav) if fav is not None else str(Path(path).parent)
        _open_in_file_manager(target)

    def _on_remove_clicked(self, _button: Gtk.Button, path: str) -> None:
        self.store.remove(path)

    def _on_move_clicked(self, _button: Gtk.Button, path: str, delta: int) -> None:
        favorites = self.store.list()
        idx = next((i for i, fav in enumerate(favorites) if fav.path == path), None)
        if idx is None:
            return
        self.store.move(path, idx + delta)

    def _on_label_button_press(
        self, _widget: Gtk.Widget, event: Gdk.EventButton, path: str
    ) -> bool:
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            self._enter_rename_mode(path)
            return True
        return False

    def _on_rename_entry_activate(self, entry: Gtk.Entry, path: str) -> None:
        new_label = entry.get_text().strip()
        if new_label:
            self.store.rename(path, new_label)
        self._exit_rename_mode(path)

    def _on_rename_entry_focus_out(
        self, entry: Gtk.Entry, _event: Gdk.EventFocus, path: str
    ) -> bool:
        row = self._rows_by_path.get(path)
        if row is not None and row.label_stack.get_visible_child_name() != "entry":  # type: ignore[attr-defined]
            return False  # already committed via "activate"
        self._on_rename_entry_activate(entry, path)
        return False

    def _enter_rename_mode(self, path: str) -> None:
        row = self._rows_by_path.get(path)
        if row is None:
            return
        row.label_stack.set_visible_child_name("entry")  # type: ignore[attr-defined]
        row.rename_entry.grab_focus()  # type: ignore[attr-defined]
        row.rename_entry.select_region(0, -1)  # type: ignore[attr-defined]

    def _exit_rename_mode(self, path: str) -> None:
        row = self._rows_by_path.get(path)
        if row is not None:
            row.label_stack.set_visible_child_name("label")  # type: ignore[attr-defined]
