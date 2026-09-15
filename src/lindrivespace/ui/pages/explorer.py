"""Explorer page — the TreeSize-style tree-table (WP8).

Layout: ScanToolbar, Breadcrumb, a Gtk.Paned (tree | optional insight panel
slot for WP9), and a status bar. Owns the scan lifecycle end to end: builds
the model/controller, starts scans, and reflects controller signals into the
header progress pill, the tree and the status bar.
"""

from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk, Pango  # noqa: E402

from lindrivespace.config.layout import Layout  # noqa: E402
from lindrivespace.core.fsnode import FsNode  # noqa: E402
from lindrivespace.models.tree_model import ScanTreeModel  # noqa: E402
from lindrivespace.services.favorites import get_store  # noqa: E402
from lindrivespace.services.scan_controller import ScanController  # noqa: E402
from lindrivespace.services.scan_registry import STATE_DONE, ScanEntry, ScanRegistry  # noqa: E402
from lindrivespace.ui.pages.base import BasePage  # noqa: E402
from lindrivespace.ui.widgets.breadcrumb import Breadcrumb  # noqa: E402
from lindrivespace.ui.widgets.explorer_tree import ExplorerTree  # noqa: E402
from lindrivespace.ui.widgets.insight_panel import InsightPanel  # noqa: E402
from lindrivespace.ui.widgets.scan_toolbar import ScanToolbar  # noqa: E402
from lindrivespace.ui.widgets.tree_context_menu import TreeContextMenu  # noqa: E402

_DIMS = Layout.dimensions


class ExplorerPage(BasePage):
    __gtype_name__ = "LdsExplorerPage"
    __gsignals__ = {
        "node-selected": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "action-requested": (GObject.SignalFlags.RUN_FIRST, None, (str, object)),
    }

    title = "Explorer"

    def build_content(self) -> None:
        # This page owns full-bleed chrome (toolbar/tree/status bar touch the
        # window edges in every mockup direction), so drop BasePage's margins.
        self.get_style_context().remove_class("page-padded")  # full-bleed chrome
        self.set_spacing(0)

        self._error_count = 0
        self._has_side_panel = False
        self._selected_file: object | None = None

        # One model + controller per root path live in the registry; the page
        # binds to one entry at a time (the active scan by default).
        self.registry: ScanRegistry = self.app.scan_registry
        self.entry: ScanEntry | None = None
        self.model: ScanTreeModel = self.app.make_model()  # placeholder until bound
        self.controller: ScanController = ScanController(self.model)
        self._controller_handlers: list[int] = []
        self._user_bound = False
        self._root_expanded = False
        self._connect_controller(self.controller)
        self.registry.connect("active-changed", self._on_registry_active_changed)

        self.toolbar = ScanToolbar(self.theme, self.settings)
        self.toolbar.connect("scan-requested", lambda _t, path: self.start_scan(path, force=True))
        self.toolbar.connect("cancel-requested", lambda _t: self.controller.cancel())
        self.toolbar.connect("pause-toggled", self._on_pause_toggled)
        self.toolbar.connect("primary-changed", self._on_primary_changed)
        self.toolbar.connect("hidden-changed", self._on_hidden_changed)
        self.toolbar.connect("cross-mounts-changed", self._on_cross_mounts_changed)
        self.toolbar.connect("panel-toggled", lambda _t, active: self.set_panel_visible(active))
        self.toolbar.connect(
            "columns-requested", lambda t: self.tree.show_column_menu(t.columns_button)
        )
        self.toolbar.connect("favorite-toggled", lambda _t, _a: self.toggle_favorite())
        self.favorites = get_store(self.app)
        self.favorites.connect("changed", lambda _s: self._sync_favorite_button())
        self.pack_start(self.toolbar, False, False, 0)

        self.breadcrumb = Breadcrumb(self.theme)
        self.breadcrumb.connect("segment-activated", lambda _b, node: self.tree.select_node(node))
        self.pack_start(self.breadcrumb, False, False, 0)

        self.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.paned.set_hexpand(True)
        self.paned.set_vexpand(True)

        self.tree = ExplorerTree(self.theme, self.model, self.settings)
        self.tree.set_hexpand(True)
        self.tree.set_vexpand(True)
        # A minimum width keeps GtkPaned from clamping the divider to 0 on its
        # first (tiny) allocation and collapsing the tree behind the panel.
        self.tree.set_size_request(380, -1)
        self.tree.connect("node-selected", self._on_node_selected)
        self.tree.connect("file-selected", self._on_file_selected)
        self.tree.connect("file-activated", self._on_file_activated)
        self.tree.connect("context-requested", self._on_context_requested)
        self.paned.pack1(self.tree, True, False)

        self._panel_slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._panel_slot.set_no_show_all(True)
        self._panel_slot.set_visible(False)
        self.paned.pack2(self._panel_slot, False, False)

        self.pack_start(self.paned, True, True, 0)

        # ---- insight panel (WP9) ---------------------------------------------
        self._auto_hidden = False
        self.panel = InsightPanel(self.theme, self.settings)
        self.panel.connect("node-activated", lambda _p, node: self.tree.select_node(node))
        self.panel.connect("collapse-requested", lambda _p: self.set_panel_visible(False))
        self.connect("node-selected", lambda _page, node: self.panel.set_node(node, self.model))
        if self.settings.get("window.panel_visible", True):
            self.add_side_panel(self.panel, persist=False)
        self.toolbar.set_panel_active(self._has_side_panel)
        self.connect("size-allocate", self._on_page_size_allocate)
        self.window.connect("key-press-event", self._on_key_press)

        self.status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.status_bar.get_style_context().add_class("statusbar")
        self.status_left = Gtk.Label(label="")
        self.status_left.set_xalign(0.0)
        self.status_left.set_ellipsize(Pango.EllipsizeMode.END)
        self.status_bar.pack_start(self.status_left, True, True, 0)
        self.status_right = Gtk.Label(label="")
        self.status_right.set_xalign(1.0)
        self.status_bar.pack_end(self.status_right, False, False, 0)
        self.pack_start(self.status_bar, False, False, 0)

    # ---- scan lifecycle -------------------------------------------------

    def start_scan(self, path: str, force: bool = False) -> None:
        """Show ``path`` in the tree; scan it now unless a finished scan exists (or ``force``)."""
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            self.status_left.set_text(f"Not a folder: {path}")
            return
        entry = self.registry.get_or_create(path)
        self._bind_entry(entry, user=True)
        if entry.state == STATE_DONE and not force:
            self._show_finished(entry)
            return
        self._error_count = 0
        self.registry.request(path, force=force)
        self._update_status()

    # ---- registry binding ---------------------------------------------------

    def _connect_controller(self, controller: ScanController) -> None:
        self._controller_handlers = [
            controller.connect("batch-applied", self._on_batch_applied),
            controller.connect("progress", self._on_progress),
            controller.connect("scan-started", self._on_scan_started),
            controller.connect("scan-finished", self._on_scan_finished),
            controller.connect("scan-error", self._on_scan_error),
        ]

    def _bind_entry(self, entry: ScanEntry, *, user: bool) -> None:
        """Point the tree, breadcrumb, panel and status at ``entry``."""
        if user:
            self._user_bound = True
        if entry is self.entry:
            return
        for handler in self._controller_handlers:
            self.controller.disconnect(handler)
        self.entry = entry
        self.model = entry.model
        self.controller = entry.controller
        self._connect_controller(self.controller)
        self._root_expanded = False
        self.tree.set_model(self.model)
        self.toolbar.set_path(entry.path)
        self.toolbar.set_running(entry.running)
        self._error_count = entry.errors
        if self.model.root is not None:
            self._expand_root_once()
            self.tree.select_node(self.model.root)
        else:
            self.breadcrumb.set_node(None, self.model)
            self.panel.set_node(None, self.model)
        self._update_status()

    def _on_registry_active_changed(self, _registry: ScanRegistry, path: str) -> None:
        """Follow the startup queue until the user picks a scan themselves."""
        if self._user_bound or not path:
            return
        entry = self.registry.get(path)
        if entry is not None:
            self._bind_entry(entry, user=False)

    def _show_finished(self, entry: ScanEntry) -> None:
        self.toolbar.set_running(False)
        self.tree.refresh()
        if self.model.root is not None:
            self._expand_root_once()
            self.tree.select_node(self.model.root)
        self._honour_pending_reveal()
        self._update_status(extra=f"scanned {entry.finished_text}")

    def _honour_pending_reveal(self) -> None:
        pending = getattr(self.window, "pending_reveal", None)
        if pending:
            self.window.pending_reveal = None
            self.reveal_path(str(pending))

    def _expand_root_once(self) -> None:
        if self._root_expanded or self.model.root is None:
            return
        root_it = self.model.iter_for_node(self.model.root)
        if root_it is not None and self.model.store.iter_has_child(root_it):
            self.tree.treeview.expand_row(self.model.store.get_path(root_it), False)
            self._root_expanded = True

    def _on_pause_toggled(self, _toolbar: ScanToolbar, paused: bool) -> None:
        if paused:
            self.controller.pause()
        else:
            self.controller.resume()

    def _on_primary_changed(self, _toolbar: ScanToolbar, allocated: bool) -> None:
        self.model.set_primary(allocated)
        self.tree.refresh()
        self.settings.set("primary_size", "allocated" if allocated else "apparent")
        node = self.tree.get_selected_node()
        if node is not None:
            self.breadcrumb.set_node(node, self.model)

    def _on_hidden_changed(self, _toolbar: ScanToolbar, show_hidden: bool) -> None:
        self.settings.set("scan.show_hidden", show_hidden)
        self.model.show_hidden = show_hidden  # file rows listed on expand follow the toggle

    def _on_cross_mounts_changed(self, _toolbar: ScanToolbar, cross_mounts: bool) -> None:
        self.settings.set("scan.cross_mounts", cross_mounts)

    # ---- controller signals -----------------------------------------------

    def _on_batch_applied(self, _controller: ScanController) -> None:
        self.tree.refresh()
        self._expand_root_once()
        node = self.tree.get_selected_node()
        if node is not None:
            self.breadcrumb.set_node(node, self.model)
        elif self.model.root is not None:
            self.breadcrumb.set_node(self.model.root, self.model)
        self._update_status()

    def _on_progress(
        self, _controller: ScanController, _entries: int, _alloc: int, _current_path: str
    ) -> None:
        self._update_status()

    def _on_scan_started(self, _controller: ScanController, path: str) -> None:
        self._root_expanded = False
        self._error_count = 0
        self.toolbar.set_path(path)
        self.toolbar.set_running(True)
        self._update_status()

    def _on_scan_finished(self, _controller: ScanController, cancelled: bool) -> None:
        path = self.controller.path or ""
        elapsed = self.controller.elapsed
        self.toolbar.set_running(False)
        if not cancelled:
            self.window.record_scan(path)
        state = "cancelled" if cancelled else "finished"
        self.tree.refresh()
        if self.model.root is not None:
            self._expand_root_once()
            self.tree.select_node(self.model.root)
        self._honour_pending_reveal()
        self._update_status(extra=f"{state} in {elapsed:.1f} s")

    def _on_scan_error(self, _controller: ScanController, _path: str, _message: str) -> None:
        self._error_count += 1
        self._update_status()

    # ---- tree / breadcrumb / status -----------------------------------------

    def _on_node_selected(self, _tree: ExplorerTree, node: FsNode | None) -> None:
        self.breadcrumb.set_node(node, self.model)
        self._update_status()
        self._sync_favorite_button()
        self.emit("node-selected", node)

    # ---- favorites -----------------------------------------------------------

    def selected_path(self) -> str | None:
        """Path of the selected row (file or folder), or None."""
        row = self.tree.get_selected_row()
        if row is None:
            return None
        return row.path()  # type: ignore[attr-defined, no-any-return]

    def _sync_favorite_button(self) -> None:
        path = self.selected_path()
        self.toolbar.set_favorite_active(bool(path) and self.favorites.is_favorite(path or ""))

    def toggle_favorite(self, path: str | None = None) -> bool | None:
        """Star/unstar ``path`` (default: the selection). Returns the new state."""
        path = path or self.selected_path()
        if not path:
            return None
        state = self.favorites.toggle(path)
        self._sync_favorite_button()
        self.status_left.set_text(
            f"Added to Favorites: {path}" if state else f"Removed from Favorites: {path}"
        )
        return state

    def reveal_path(self, path: str) -> bool:
        """Select the row for ``path`` (a folder or file under the scan root)."""
        root = self.model.root
        if root is None:
            return False
        root_path = root.path()
        if path == root_path:
            self.tree.select_node(root)
            return True
        prefix = root_path if root_path.endswith("/") else root_path + "/"
        if not path.startswith(prefix):
            return False
        node: FsNode | None = root
        parts = path[len(prefix) :].split("/")
        for i, part in enumerate(parts):
            assert node is not None
            child = next((c for c in node.children if c.name == part), None)
            if child is None:
                if i == len(parts) - 1:  # a file: select its folder, expand, pick the row
                    self.tree.select_node(node)
                    it = self.model.iter_for_node(node)
                    if it is not None:
                        self.tree.treeview.expand_row(self.model.store.get_path(it), False)
                        child_it = self.model.store.iter_children(it)
                        while child_it is not None:
                            row = self.model.row_for_iter(child_it)
                            if row is not None and row.name == part:
                                self.tree.selection.select_iter(child_it)
                                self.tree.treeview.scroll_to_cell(
                                    self.model.store.get_path(child_it), None, True, 0.3, 0.0
                                )
                                return True
                            child_it = self.model.store.iter_next(child_it)
                    return True
                return False
            node = child
        self.tree.select_node(node)  # type: ignore[arg-type]
        return True

    def _on_file_selected(self, _tree: ExplorerTree, row: object | None) -> None:
        """A file row is selected: show it in the status bar (folder totals stay in the panel)."""
        self._selected_file = row
        if row is not None:
            size = self.model.fmt_bytes(self.model.primary(row))  # type: ignore[arg-type]
            self.status_right.set_text(f"file: {row.path()} {size}")  # type: ignore[attr-defined]

    def _on_file_activated(self, _tree: ExplorerTree, path: str) -> None:
        """Double-click on a file: reveal it in the file manager."""
        from lindrivespace.services import actions

        if not actions.reveal_in_file_manager(path):
            self.status_left.set_text(f"Could not open a file manager for {path}")

    def _update_status(self, extra: str | None = None) -> None:
        entries = self.controller.entries or self.model.entries
        elapsed = self.controller.elapsed
        state = extra or ("scanning" if self.controller.running else "idle")
        left = f"{entries:,} items · {elapsed:.0f} s · {state}"
        if self._error_count:
            left += f" · {self._error_count} denied · re-scan as admin"
        self.status_left.set_text(left)

        node = self.tree.get_selected_node()
        if node is not None:
            total = self.model.fmt_bytes(self.model.primary(node))
            entry_count = node.files + node.dirs
            self.status_right.set_text(
                f"selected: {node.path()} {total} in {entry_count:,} entries"
            )
        else:
            self.status_right.set_text("")

    # ---- context menu -------------------------------------------------------

    def _on_context_requested(
        self,
        _tree: ExplorerTree,
        node: FsNode | None,
        _x: int,
        _y: int,
        event: Gdk.EventButton,
    ) -> None:
        path = self.selected_path()
        menu = TreeContextMenu(
            node,
            has_side_panel=self.has_side_panel,
            is_favorite=bool(path) and self.favorites.is_favorite(path or ""),
        )
        menu.connect("action", self._on_menu_action)
        menu.popup_at_pointer(event)

    def _on_menu_action(self, _menu: TreeContextMenu, name: str, node: FsNode | None) -> None:
        path = node.path() if node is not None else None
        if name == "copy-path" and path:
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(path, -1)
            clipboard.store()
        elif name == "open-file-manager" and path:
            try:
                Gio.AppInfo.launch_default_for_uri(f"file://{path}", None)
            except GLib.Error as exc:
                print(f"could not open file manager: {exc}")
        elif name == "open-terminal" and path:
            self._open_terminal(path)
        elif name == "rescan" and path:
            self.start_scan(path, force=True)
        elif name == "exclude" and path:
            excludes = list(self.settings.get("scan.excludes", []) or [])
            if path not in excludes:
                excludes.append(path)
                self.settings.set("scan.excludes", excludes)
            print(f"excluded from scan: {path}")
        elif name == "toggle-favorite":
            self.toggle_favorite(self.selected_path() or path)
        elif name == "columns":
            self.tree.show_column_menu()
        elif name == "show-in-treemap" and node is not None:
            self.set_panel_visible(True)
            self.panel.current_tab = "treemap"
            self.panel.set_node(node, self.model)
        elif name == "scan-as-admin":
            print(f"TODO (WP11/WP9): {name} for {path}")
            self.emit("action-requested", name, node)

    def _open_terminal(self, path: str) -> None:
        try:
            quoted = GLib.shell_quote(path)
            app_info = Gio.AppInfo.create_from_commandline(
                f"x-terminal-emulator --working-directory={quoted}",
                None,
                Gio.AppInfoCreateFlags.NONE,
            )
            app_info.launch([], None)
        except GLib.Error as exc:
            print(f"could not open terminal: {exc}")

    # ---- side panel (WP9) -----------------------------------------------

    @property
    def has_side_panel(self) -> bool:
        return self._has_side_panel

    def add_side_panel(self, widget: Gtk.Widget, *, persist: bool = True) -> None:
        for child in list(self._panel_slot.get_children()):
            self._panel_slot.remove(child)
        self._panel_slot.pack_start(widget, True, True, 0)
        self._panel_slot.set_visible(True)
        # ``_panel_slot`` is ``no_show_all`` (kept hidden until a panel is
        # attached), so the ambient ``win.show_all()`` cascade never reaches
        # its subtree: the attached widget must be shown explicitly, and
        # ``show_all`` (not just ``show``) so its own children map too.
        widget.show_all()
        self._has_side_panel = True
        # The panel keeps its PANEL_WIDTH size request and pack2(resize=False):
        # GtkPaned then gives the tree everything else, no set_position needed.
        if persist:
            self._save_panel_visible(True)

    def remove_side_panel(self, *, persist: bool = True) -> None:
        for child in list(self._panel_slot.get_children()):
            self._panel_slot.remove(child)
        self._panel_slot.set_visible(False)
        self._has_side_panel = False
        if persist:
            self._save_panel_visible(False)

    def _save_panel_visible(self, visible: bool) -> None:
        self.settings.set("window.panel_visible", visible)
        try:
            self.settings.save()
        except OSError as exc:
            print(f"could not save settings: {exc}")

    def set_panel_visible(self, visible: bool) -> None:
        """Show/hide the insight panel and persist the choice (user action)."""
        if visible == self._has_side_panel:
            self.toolbar.set_panel_active(visible)
            return
        if visible:
            self.add_side_panel(self.panel)
        else:
            self.remove_side_panel()
        self.toolbar.set_panel_active(visible)

    def toggle_panel(self) -> None:
        self.set_panel_visible(not self._has_side_panel)

    def _on_key_press(self, _widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        if self.window.current_page_id != self.page_id:
            return False
        if event.keyval == Gdk.KEY_F9:
            self.toggle_panel()
            return True
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        if ctrl and event.keyval in (Gdk.KEY_d, Gdk.KEY_D):
            self.toggle_favorite()
            return True
        return False

    def _on_page_size_allocate(self, _widget: Gtk.Widget, _allocation: Gdk.Rectangle) -> None:
        # Compare the *window's* width, not this page's content-box width: the
        # page is already narrower than the window by the sidebar's fixed 150 px,
        # so using the page's own allocation would auto-collapse the panel at
        # the default 1200 px window size (1200 - 150 = 1050 < 1100).
        width = self.window.get_allocated_width()
        if width <= 0:
            return
        below_threshold = width < _DIMS.PANEL_COLLAPSE_BELOW
        if below_threshold and self._has_side_panel:
            self._auto_hidden = True
            self.remove_side_panel(persist=False)
            self.toolbar.set_panel_active(False)
        elif not below_threshold and self._auto_hidden and not self._has_side_panel:
            self._auto_hidden = False
            self.add_side_panel(self.panel, persist=False)
            self.toolbar.set_panel_active(True)

    # ---- page lifecycle -----------------------------------------------------

    def on_hidden(self) -> None:
        # The scan keeps running in the background; the header pill stays put.
        self.tree.save_state()

    def on_shown(self) -> None:
        if self.entry is None:
            entry = self.registry.active_entry
            if entry is None:
                done = self.registry.done_paths()
                entry = self.registry.get(done[0]) if done else None
            if entry is not None:
                self._bind_entry(entry, user=False)
                if entry.state == STATE_DONE:
                    self._show_finished(entry)
        self._update_status()
