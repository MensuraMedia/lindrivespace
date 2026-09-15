"""Scan toolbar: path entry, scan controls, and the primary/hidden/cross-mount
toggles that sit above the Explorer tree-table.

Owns no scan state itself — every toggle just emits a signal (or, for
Cancel/Pause, is exposed as a plain public button) so the page can wire it to
``ScanController`` and persist the choice in ``Settings``.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gtk  # noqa: E402

from lindrivespace.config.settings import Settings  # noqa: E402
from lindrivespace.config.theme import ThemeDefinition  # noqa: E402


class ScanToolbar(Gtk.Box):
    """Horizontal row: path entry + folder chooser, scan controls, view toggles."""

    __gtype_name__ = "LdsScanToolbar"
    __gsignals__ = {
        "scan-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "cancel-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "pause-toggled": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        "primary-changed": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        "hidden-changed": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        "cross-mounts-changed": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        "panel-toggled": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        "columns-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "favorite-toggled": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
    }

    def __init__(self, theme: ThemeDefinition, settings: Settings) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._theme = theme
        self._settings = settings
        self._updating_primary = False
        self._updating_panel = False
        self._paused = False

        self.get_style_context().add_class("scan-toolbar")
        self.set_spacing(6)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self.set_margin_top(8)
        self.set_margin_bottom(4)

        self.path_entry = Gtk.Entry()
        self.path_entry.set_placeholder_text("Path to scan…")
        self.path_entry.set_hexpand(True)
        self.path_entry.connect("activate", self._on_entry_activate)
        self.pack_start(self.path_entry, True, True, 0)

        self.folder_button = Gtk.Button.new_from_icon_name(
            "folder-open-symbolic", Gtk.IconSize.BUTTON
        )
        self.folder_button.set_tooltip_text("Choose a folder…")
        self.folder_button.connect("clicked", self._on_choose_folder)
        self.pack_start(self.folder_button, False, False, 0)

        self.scan_button = Gtk.Button(label="Scan")
        self.scan_button.get_style_context().add_class("primary")
        self.scan_button.connect("clicked", self._on_scan_clicked)
        self.pack_start(self.scan_button, False, False, 0)

        self.cancel_button = Gtk.Button(label="Cancel")
        self.cancel_button.connect("clicked", self._on_cancel_clicked)
        self.cancel_button.set_no_show_all(True)
        self.cancel_button.set_visible(False)
        self.pack_start(self.cancel_button, False, False, 0)

        self.pause_button = Gtk.Button(label="Pause")
        self.pause_button.connect("clicked", self._on_pause_clicked)
        self.pause_button.set_no_show_all(True)
        self.pause_button.set_visible(False)
        self.pack_start(self.pause_button, False, False, 0)

        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.set_margin_start(4)
        sep.set_margin_end(4)
        self.pack_start(sep, False, False, 0)

        primary_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        primary_box.get_style_context().add_class("linked")
        self.allocated_button = Gtk.ToggleButton(label="Allocated")
        self.apparent_button = Gtk.ToggleButton(label="Apparent")
        self.allocated_button.connect("toggled", self._on_primary_toggled, True)
        self.apparent_button.connect("toggled", self._on_primary_toggled, False)
        primary_box.pack_start(self.allocated_button, False, False, 0)
        primary_box.pack_start(self.apparent_button, False, False, 0)
        self.pack_start(primary_box, False, False, 0)

        self.hidden_button = Gtk.ToggleButton(label="Hidden")
        self.hidden_button.set_tooltip_text("Show hidden files and folders")
        self.hidden_button.connect("toggled", self._on_hidden_toggled)
        self.pack_start(self.hidden_button, False, False, 0)

        self.cross_mounts_button = Gtk.ToggleButton(label="Cross mounts")
        self.cross_mounts_button.set_tooltip_text("Descend into other filesystems")
        self.cross_mounts_button.connect("toggled", self._on_cross_mounts_toggled)
        self.pack_start(self.cross_mounts_button, False, False, 0)

        allocated = settings.get("primary_size", "allocated") == "allocated"
        self._set_primary_buttons(allocated)
        self.hidden_button.set_active(bool(settings.get("scan.show_hidden", True)))
        self.cross_mounts_button.set_active(bool(settings.get("scan.cross_mounts", False)))

        panel_icon = "view-sidebar-symbolic"
        if not Gtk.IconTheme.get_default().has_icon(panel_icon):
            panel_icon = "sidebar-show-symbolic"
        self.panel_button = Gtk.ToggleButton()
        self.panel_button.set_image(Gtk.Image.new_from_icon_name(panel_icon, Gtk.IconSize.BUTTON))
        self.panel_button.set_tooltip_text("Show/hide insight panel (F9)")
        self.panel_button.set_active(bool(settings.get("window.panel_visible", True)))
        self.panel_button.connect("toggled", self._on_panel_toggled)
        self.pack_end(self.panel_button, False, False, 0)

        self.columns_button = Gtk.Button(label="Columns")
        self.columns_button.set_tooltip_text("Choose which columns to show")
        self.columns_button.get_accessible().set_name("Columns")
        self.columns_button.connect("clicked", lambda _b: self.emit("columns-requested"))
        self.pack_end(self.columns_button, False, False, 0)

        self._updating_favorite = False
        self.favorite_button = Gtk.ToggleButton()
        self.favorite_button.set_image(
            Gtk.Image.new_from_icon_name("non-starred-symbolic", Gtk.IconSize.BUTTON)
        )
        self.favorite_button.set_tooltip_text("Add the selected folder to Favorites (Ctrl+D)")
        self.favorite_button.get_accessible().set_name("Favorite")
        self.favorite_button.connect("toggled", self._on_favorite_toggled)
        self.pack_end(self.favorite_button, False, False, 0)

    # ---- path -------------------------------------------------------------

    def get_path(self) -> str:
        return self.path_entry.get_text().strip()

    def set_path(self, path: str) -> None:
        self.path_entry.set_text(path)

    def _on_entry_activate(self, entry: Gtk.Entry) -> None:
        path = entry.get_text().strip()
        if path:
            self.emit("scan-requested", path)

    def _on_scan_clicked(self, _button: Gtk.Button) -> None:
        path = self.get_path()
        if path:
            self.emit("scan-requested", path)

    def _on_choose_folder(self, _button: Gtk.Button) -> None:
        toplevel = self.get_toplevel()
        parent = toplevel if isinstance(toplevel, Gtk.Window) else None
        dialog = Gtk.FileChooserDialog(
            title="Select a folder to scan",
            parent=parent,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Open", Gtk.ResponseType.OK)
        try:
            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                path = dialog.get_filename()
                if path:
                    self.set_path(path)
                    self.emit("scan-requested", path)
        finally:
            dialog.destroy()

    # ---- run state ----------------------------------------------------------

    def _on_cancel_clicked(self, _button: Gtk.Button) -> None:
        self.emit("cancel-requested")

    def _on_pause_clicked(self, _button: Gtk.Button) -> None:
        self._paused = not self._paused
        self.pause_button.set_label("Resume" if self._paused else "Pause")
        self.emit("pause-toggled", self._paused)

    def set_running(self, running: bool) -> None:
        self.cancel_button.set_visible(running)
        self.pause_button.set_visible(running)
        self.scan_button.set_sensitive(not running)
        if not running:
            self._paused = False
            self.pause_button.set_label("Pause")

    # ---- view toggles -------------------------------------------------------

    def _set_primary_buttons(self, allocated: bool) -> None:
        self._updating_primary = True
        self.allocated_button.set_active(allocated)
        self.apparent_button.set_active(not allocated)
        self._updating_primary = False

    def _on_primary_toggled(self, button: Gtk.ToggleButton, allocated: bool) -> None:
        if self._updating_primary:
            return
        if not button.get_active():
            # A segmented pair always has exactly one side active.
            button.set_active(True)
            return
        self._set_primary_buttons(allocated)
        self.emit("primary-changed", allocated)

    def _on_hidden_toggled(self, button: Gtk.ToggleButton) -> None:
        self.emit("hidden-changed", button.get_active())

    def _on_cross_mounts_toggled(self, button: Gtk.ToggleButton) -> None:
        self.emit("cross-mounts-changed", button.get_active())

    # ---- insight panel toggle (WP9) ------------------------------------------

    def _on_panel_toggled(self, button: Gtk.ToggleButton) -> None:
        if self._updating_panel:
            return
        self.emit("panel-toggled", button.get_active())

    def _on_favorite_toggled(self, button: Gtk.ToggleButton) -> None:
        if self._updating_favorite:
            return
        self.emit("favorite-toggled", button.get_active())

    def set_favorite_active(self, active: bool) -> None:
        """Reflect whether the current selection is a favourite (no signal)."""
        self._updating_favorite = True
        self.favorite_button.set_active(active)
        icon = "starred-symbolic" if active else "non-starred-symbolic"
        self.favorite_button.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
        self._updating_favorite = False

    def set_panel_active(self, active: bool) -> None:
        """Sync the toggle button without re-emitting ``panel-toggled``."""
        if self.panel_button.get_active() == active:
            return
        self._updating_panel = True
        self.panel_button.set_active(active)
        self._updating_panel = False

    def set_theme(self, theme: ThemeDefinition) -> None:
        """Kept for API parity with the other Explorer widgets."""
        self._theme = theme
