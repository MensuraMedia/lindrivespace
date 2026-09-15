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
from lindrivespace.core import units  # noqa: E402
from lindrivespace.core.fsnode import FsNode  # noqa: E402
from lindrivespace.core.options import DEFAULT_EXCLUDES, ScanOptions  # noqa: E402
from lindrivespace.models.tree_model import ScanTreeModel  # noqa: E402
from lindrivespace.services.scan_controller import ScanController  # noqa: E402
from lindrivespace.ui.pages.base import BasePage  # noqa: E402
from lindrivespace.ui.widgets.breadcrumb import Breadcrumb  # noqa: E402
from lindrivespace.ui.widgets.explorer_tree import ExplorerTree  # noqa: E402
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
        self.set_margin_start(0)
        self.set_margin_end(0)
        self.set_margin_top(0)
        self.set_margin_bottom(0)
        self.set_spacing(0)

        self._pill: Gtk.Box | None = None
        self._pill_label: Gtk.Label | None = None
        self._pill_progress: Gtk.ProgressBar | None = None
        self._error_count = 0
        self._has_side_panel = False

        self.model = ScanTreeModel(
            fmt_bytes=self._format_bytes,
            allocated_primary=self.settings.get("primary_size", "allocated") == "allocated",
            top_n_bold=self.settings.get("explorer.top_n_bold", 3),
        )
        self.controller = ScanController(self.model)
        self._root_expanded = False
        self.controller.connect("batch-applied", self._on_batch_applied)
        self.controller.connect("progress", self._on_progress)
        self.controller.connect("scan-finished", self._on_scan_finished)
        self.controller.connect("scan-error", self._on_scan_error)

        self.toolbar = ScanToolbar(self.theme, self.settings)
        self.toolbar.connect("scan-requested", lambda _t, path: self.start_scan(path))
        self.toolbar.connect("cancel-requested", lambda _t: self.controller.cancel())
        self.toolbar.connect("pause-toggled", self._on_pause_toggled)
        self.toolbar.connect("primary-changed", self._on_primary_changed)
        self.toolbar.connect("hidden-changed", self._on_hidden_changed)
        self.toolbar.connect("cross-mounts-changed", self._on_cross_mounts_changed)
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
        self.tree.connect("node-selected", self._on_node_selected)
        self.tree.connect("context-requested", self._on_context_requested)
        self.paned.pack1(self.tree, True, True)

        self._panel_slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._panel_slot.set_no_show_all(True)
        self._panel_slot.set_visible(False)
        self.paned.pack2(self._panel_slot, False, True)

        self.pack_start(self.paned, True, True, 0)

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

    # ---- formatting ---------------------------------------------------------

    def _format_bytes(self, n: int) -> int | str:
        binary = self.settings.get("units", "decimal") == "binary"
        return units.format_bytes(n, binary=binary)

    # ---- scan lifecycle -------------------------------------------------

    def start_scan(self, path: str) -> None:
        """Start scanning ``path``. Called by the window (request_scan) and the toolbar."""
        self._root_expanded = False
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            self.status_left.set_text(f"Not a folder: {path}")
            return

        scan_settings = self.settings.get("scan", {}) or {}
        options = ScanOptions(
            follow_symlinks=bool(scan_settings.get("follow_symlinks", False)),
            cross_mounts=bool(scan_settings.get("cross_mounts", False)),
            count_hardlinks_once=bool(scan_settings.get("count_hardlinks_once", True)),
            show_hidden=bool(scan_settings.get("show_hidden", True)),
            excludes=tuple(scan_settings.get("excludes", DEFAULT_EXCLUDES)),
            top_files=int(scan_settings.get("top_files", 50)),
        )

        self._error_count = 0
        self.toolbar.set_path(path)
        self.toolbar.set_running(True)
        self._ensure_pill()
        if self._pill_label is not None:
            self._pill_label.set_text(f"Scanning {path} · 0 entries · 0 s")
        self.window.set_header_widget(self._pill)
        self.controller.start(path, options)
        self._update_status()

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

    def _on_cross_mounts_changed(self, _toolbar: ScanToolbar, cross_mounts: bool) -> None:
        self.settings.set("scan.cross_mounts", cross_mounts)

    # ---- header progress pill --------------------------------------------

    def _ensure_pill(self) -> None:
        if self._pill is not None:
            return
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.get_style_context().add_class("pill")

        stop_button = Gtk.Button()
        stop_button.set_relief(Gtk.ReliefStyle.NONE)
        stop_icon = Gtk.Image.new_from_icon_name("process-stop-symbolic", Gtk.IconSize.MENU)
        provider = Gtk.CssProvider()
        provider.load_from_data(f"image {{ color: {self.theme.danger}; }}".encode())
        stop_icon.get_style_context().add_provider(
            provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        stop_button.add(stop_icon)
        stop_button.set_tooltip_text("Cancel scan")
        stop_button.connect("clicked", lambda _b: self.controller.cancel())
        box.pack_start(stop_button, False, False, 0)

        label = Gtk.Label(label="")
        label.get_style_context().add_class("mono")
        box.pack_start(label, False, False, 0)

        progress = Gtk.ProgressBar()
        progress.set_show_text(False)
        progress.set_size_request(120, -1)
        box.pack_start(progress, False, False, 0)

        self._pill = box
        self._pill_label = label
        self._pill_progress = progress

    def _update_pill(self) -> None:
        if self._pill_label is None or self._pill_progress is None:
            return
        path = self.controller.path or ""
        entries = self.controller.entries
        elapsed = int(self.controller.elapsed)
        self._pill_label.set_text(f"Scanning {path} · {entries:,} entries · {elapsed} s")
        self._pill_progress.pulse()

    # ---- controller signals -----------------------------------------------

    def _on_batch_applied(self, _controller: ScanController) -> None:
        self.tree.refresh()
        # Show the first level as soon as it exists: the root row is populated by
        # the model, but GTK keeps it collapsed until we expand it once per scan.
        if not self._root_expanded and self.model.root is not None:
            root_it = self.model.iter_for_node(self.model.root)
            if root_it is not None and self.model.store.iter_has_child(root_it):
                self.tree.treeview.expand_row(self.model.store.get_path(root_it), False)
                self._root_expanded = True
        node = self.tree.get_selected_node()
        if node is not None:
            self.breadcrumb.set_node(node, self.model)
        elif self.model.root is not None:
            self.breadcrumb.set_node(self.model.root, self.model)
        self._update_pill()
        self._update_status()

    def _on_progress(
        self, _controller: ScanController, _entries: int, _alloc: int, _current_path: str
    ) -> None:
        self._update_pill()
        self._update_status()

    def _on_scan_finished(self, _controller: ScanController, cancelled: bool) -> None:
        path = self.controller.path or ""
        elapsed = self.controller.elapsed
        self.toolbar.set_running(False)
        self.window.set_header_widget(None)
        if not cancelled:
            self.window.record_scan(path)
        state = "cancelled" if cancelled else "finished"
        self.tree.refresh()
        if self.model.root is not None:
            self.tree.select_node(self.model.root)
        self._update_status(extra=f"{state} in {elapsed:.1f} s")

    def _on_scan_error(self, _controller: ScanController, _path: str, _message: str) -> None:
        self._error_count += 1
        self._update_status()

    # ---- tree / breadcrumb / status -----------------------------------------

    def _on_node_selected(self, _tree: ExplorerTree, node: FsNode | None) -> None:
        self.breadcrumb.set_node(node, self.model)
        self._update_status()
        self.emit("node-selected", node)

    def _update_status(self, extra: str | None = None) -> None:
        entries = self.controller.entries or self.model.entries
        elapsed = self.controller.elapsed
        state = extra or ("scanning" if self.controller.running else "idle")
        left = f"entries {entries:,} · {elapsed:.0f} s · {state}"
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
        menu = TreeContextMenu(node, has_side_panel=self.has_side_panel)
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
            self.start_scan(path)
        elif name == "exclude" and path:
            excludes = list(self.settings.get("scan.excludes", []) or [])
            if path not in excludes:
                excludes.append(path)
                self.settings.set("scan.excludes", excludes)
            print(f"excluded from scan: {path}")
        elif name in ("scan-as-admin", "show-in-treemap"):
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

    def add_side_panel(self, widget: Gtk.Widget) -> None:
        for child in list(self._panel_slot.get_children()):
            self._panel_slot.remove(child)
        self._panel_slot.pack_start(widget, True, True, 0)
        self._panel_slot.set_visible(True)
        widget.show()
        self._has_side_panel = True
        width = self.get_allocated_width() or int(self.settings.get("window.width", 1200))
        self.paned.set_position(max(0, width - _DIMS.PANEL_WIDTH))
        self.settings.set("window.panel_visible", True)

    def remove_side_panel(self) -> None:
        for child in list(self._panel_slot.get_children()):
            self._panel_slot.remove(child)
        self._panel_slot.set_visible(False)
        self._has_side_panel = False
        self.settings.set("window.panel_visible", False)

    # ---- page lifecycle -----------------------------------------------------

    def on_hidden(self) -> None:
        # The scan keeps running in the background; the header pill stays put.
        self.tree.save_state()

    def on_shown(self) -> None:
        if self.controller.running and self._pill is not None:
            self.window.set_header_widget(self._pill)
