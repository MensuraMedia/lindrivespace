"""Settings page (WP12) — a quiet, form-like preferences screen.

Six ``PrefGroup`` cards (Appearance, Scanning defaults, Exclusions, Mounts,
Explorer, About), each holding ``PrefRow``s (see
``ui/widgets/settings_rows.py``). There is no Apply button: every control
persists to :class:`~lindrivespace.config.settings.Settings` immediately, and
``reload_from_settings`` re-reads every widget's state (used when the page is
shown again, in case another page changed a shared setting).

The light theme ("Gray Temperature (Light)") only has its colour *tokens*
defined so far — the CSS pass ships in v1.1 (see
``.claude/memory/decisions.md``, 2026-09-14 #5) — so its combo entry is
labelled " — preview" and switching to it must never touch the dark theme's
behaviour.
"""

from __future__ import annotations

import os
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from lindrivespace import __version__  # noqa: E402
from lindrivespace.config.settings import DEFAULTS  # noqa: E402
from lindrivespace.config.theme import THEMES, get_theme  # noqa: E402
from lindrivespace.core.options import DEFAULT_EXCLUDES  # noqa: E402
from lindrivespace.ui.pages.base import BasePage  # noqa: E402
from lindrivespace.ui.widgets.settings_rows import PrefGroup, PrefRow  # noqa: E402

_REPO_URL = "https://github.com/mensuramedia/lindrivespace"
_LIGHT_THEME_ID = "gray-temperature-light"


class SettingsPage(BasePage):
    title = "Settings"

    def build_content(self) -> None:
        self.add_title(self.title, "Theme, units, scan defaults, exclusions and mounts.")
        self._build_appearance_group()
        self._build_scanning_group()
        self._build_exclusions_group()
        self._build_mounts_group()
        self._build_explorer_group()
        self._build_about_group()

    def on_shown(self) -> None:
        self.reload_from_settings()

    # ---- persistence helper -------------------------------------------------

    def _persist(self, key: str, value: Any) -> None:
        self.settings.set(key, value)
        try:
            self.settings.save()
        except OSError as exc:
            print(f"could not save settings: {exc}")

    # ---- Appearance -----------------------------------------------------

    def _build_appearance_group(self) -> None:
        group = PrefGroup("Appearance")

        self.theme_combo = Gtk.ComboBoxText()
        for theme_id, theme in THEMES.items():
            display = f"{theme.name} — preview" if theme_id == _LIGHT_THEME_ID else theme.name
            self.theme_combo.append(theme_id, display)
        self.theme_combo.set_active_id(self.settings.get("theme", self.app.theme.id))
        self.theme_combo.connect("changed", self._on_theme_changed)
        group.add_row(PrefRow("Theme", self.theme_combo, "Colour palette used across the app."))

        self.units_decimal_radio = Gtk.RadioButton.new_with_label_from_widget(None, "Decimal (GB)")
        self.units_binary_radio = Gtk.RadioButton.new_with_label_from_widget(
            self.units_decimal_radio, "Binary (GiB)"
        )
        self.units_decimal_radio.get_accessible().set_name("Units: Decimal (GB)")
        self.units_binary_radio.get_accessible().set_name("Units: Binary (GiB)")
        self.units_decimal_radio.connect("toggled", self._on_units_toggled, "decimal")
        self.units_binary_radio.connect("toggled", self._on_units_toggled, "binary")
        units_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        units_box.pack_start(self.units_decimal_radio, False, False, 0)
        units_box.pack_start(self.units_binary_radio, False, False, 0)
        group.add_row(PrefRow("Units", units_box, "Decimal (base 10) or binary (base 2) sizes."))

        self.primary_allocated_radio = Gtk.RadioButton.new_with_label_from_widget(None, "Allocated")
        self.primary_apparent_radio = Gtk.RadioButton.new_with_label_from_widget(
            self.primary_allocated_radio, "Apparent"
        )
        self.primary_allocated_radio.get_accessible().set_name("Primary size: Allocated")
        self.primary_apparent_radio.get_accessible().set_name("Primary size: Apparent")
        self.primary_allocated_radio.connect("toggled", self._on_primary_toggled, "allocated")
        self.primary_apparent_radio.connect("toggled", self._on_primary_toggled, "apparent")
        primary_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        primary_box.pack_start(self.primary_allocated_radio, False, False, 0)
        primary_box.pack_start(self.primary_apparent_radio, False, False, 0)
        group.add_row(
            PrefRow(
                "Primary size",
                primary_box,
                "Disk usage in allocated blocks, or the exact apparent byte count.",
            )
        )

        self._set_units_radio_active(self.settings.get("units", "decimal"))
        self._set_primary_radio_active(self.settings.get("primary_size", "allocated"))

        self.pack_start(group, False, False, 0)
        self.appearance_group = group

    def _set_units_radio_active(self, value: str) -> None:
        (self.units_binary_radio if value == "binary" else self.units_decimal_radio).set_active(
            True
        )

    def _set_primary_radio_active(self, value: str) -> None:
        (
            self.primary_apparent_radio if value == "apparent" else self.primary_allocated_radio
        ).set_active(True)

    def _on_theme_changed(self, combo: Gtk.ComboBoxText) -> None:
        theme_id = combo.get_active_id()
        if not theme_id:
            return
        theme = get_theme(theme_id)
        self.app.theme_loader.apply(theme)
        self.app.theme = theme
        self._persist("theme", theme_id)

    def _on_units_toggled(self, radio: Gtk.RadioButton, value: str) -> None:
        if not radio.get_active():
            return
        self._persist("units", value)
        explorer = self.window.pages.get("explorer")
        setter = getattr(explorer, "set_units", None)
        if callable(setter):
            setter(value)

    def _on_primary_toggled(self, radio: Gtk.RadioButton, value: str) -> None:
        if not radio.get_active():
            return
        self._persist("primary_size", value)
        explorer = self.window.pages.get("explorer")
        setter = getattr(explorer, "set_primary", None)
        if callable(setter):
            setter(value)

    # ---- Scanning defaults ------------------------------------------------

    def _build_scanning_group(self) -> None:
        group = PrefGroup("Scanning defaults")

        self.follow_symlinks_switch = self._add_scan_switch(
            group,
            "follow_symlinks",
            "Follow symlinks",
            "Descend into symlinked directories instead of counting the link itself.",
        )
        self.cross_mounts_switch = self._add_scan_switch(
            group,
            "cross_mounts",
            "Cross mount boundaries",
            "Continue scanning across other filesystems mounted below the root.",
        )
        self.count_hardlinks_once_switch = self._add_scan_switch(
            group,
            "count_hardlinks_once",
            "Count hard links once",
            "Do not double-count space shared by multiple hard links.",
        )
        self.show_hidden_switch = self._add_scan_switch(
            group,
            "show_hidden",
            "Show hidden files",
            "Include dotfiles and dot-directories in the scan.",
        )

        self.top_files_spin = Gtk.SpinButton.new_with_range(0, 500, 1)
        self.top_files_spin.set_value(int(self.settings.get("scan.top_files", 50)))
        self.top_files_spin.connect("value-changed", self._on_top_files_changed)
        group.add_row(
            PrefRow(
                "Top files per folder",
                self.top_files_spin,
                "How many of a folder's largest files are kept for the insight panel.",
            )
        )

        self.pack_start(group, False, False, 0)
        self.scanning_group = group

    def _add_scan_switch(
        self, group: PrefGroup, key: str, label: str, description: str
    ) -> Gtk.Switch:
        switch = Gtk.Switch()
        switch.set_active(bool(self.settings.get(f"scan.{key}", False)))
        switch.connect(
            "notify::active",
            lambda sw, _pspec, k=key: self._persist(f"scan.{k}", sw.get_active()),
        )
        group.add_row(PrefRow(label, switch, description))
        return switch

    def _on_top_files_changed(self, spin: Gtk.SpinButton) -> None:
        self._persist("scan.top_files", spin.get_value_as_int())

    # ---- Exclusions ---------------------------------------------------------

    def _build_exclusions_group(self) -> None:
        group = PrefGroup("Exclusions")

        self.excludes_listbox = Gtk.ListBox()
        self.excludes_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.excludes_listbox.get_accessible().set_name("Excluded paths")
        group.add_row(self.excludes_listbox)
        self._rebuild_excludes_list()

        add_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.exclude_entry = Gtk.Entry()
        self.exclude_entry.set_placeholder_text("/absolute/path/to/exclude")
        self.exclude_entry.set_hexpand(True)
        self.exclude_entry.get_accessible().set_name("New exclusion path")
        self.exclude_entry.connect("activate", self._on_add_exclude)
        add_row.pack_start(self.exclude_entry, True, True, 0)

        add_button = Gtk.Button(label="Add")
        add_button.get_accessible().set_name("Add exclusion")
        add_button.connect("clicked", self._on_add_exclude)
        add_row.pack_start(add_button, False, False, 0)
        group.add_row(add_row)

        self.exclude_error_label = Gtk.Label(label="")
        self.exclude_error_label.set_xalign(0.0)
        self.exclude_error_label.set_no_show_all(True)
        self.exclude_error_label.set_visible(False)
        self._style_danger_label(self.exclude_error_label)
        group.add_row(self.exclude_error_label)

        reset_button = Gtk.Button(label="Reset to defaults")
        reset_button.set_halign(Gtk.Align.START)
        reset_button.get_accessible().set_name("Reset exclusions to defaults")
        reset_button.connect("clicked", self._on_reset_excludes)
        group.add_row(reset_button)

        self.pack_start(group, False, False, 0)
        self.exclusions_group = group

    def _style_danger_label(self, label: Gtk.Label) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(f"label {{ color: {self.theme.danger}; }}".encode())
        label.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _rebuild_excludes_list(self) -> None:
        for child in list(self.excludes_listbox.get_children()):
            self.excludes_listbox.remove(child)
        excludes = list(self.settings.get("scan.excludes", list(DEFAULT_EXCLUDES)) or [])
        for path in excludes:
            row = Gtk.ListBoxRow()
            row.set_selectable(False)
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            box.set_margin_top(2)
            box.set_margin_bottom(2)

            label = Gtk.Label(label=path)
            label.set_xalign(0.0)
            label.set_hexpand(True)
            label.get_style_context().add_class("mono")
            box.pack_start(label, True, True, 0)

            remove_button = Gtk.Button()
            remove_button.set_relief(Gtk.ReliefStyle.NONE)
            remove_button.add(
                Gtk.Image.new_from_icon_name("list-remove-symbolic", Gtk.IconSize.MENU)
            )
            remove_button.get_accessible().set_name(f"Remove exclusion {path}")
            remove_button.connect("clicked", self._on_remove_exclude, path)
            box.pack_end(remove_button, False, False, 0)

            row.add(box)
            self.excludes_listbox.add(row)
        self.excludes_listbox.show_all()

    def _on_add_exclude(self, _widget: Gtk.Widget) -> None:
        path = self.exclude_entry.get_text().strip()
        if not path or not os.path.isabs(path):
            self.exclude_error_label.set_text('Enter an absolute path (starting with "/").')
            self.exclude_error_label.set_visible(True)
            return
        excludes = list(self.settings.get("scan.excludes", list(DEFAULT_EXCLUDES)) or [])
        if path not in excludes:
            excludes.append(path)
            self._persist("scan.excludes", excludes)
            self._rebuild_excludes_list()
        self.exclude_entry.set_text("")
        self.exclude_error_label.set_visible(False)

    def _on_remove_exclude(self, _button: Gtk.Button, path: str) -> None:
        excludes = [p for p in (self.settings.get("scan.excludes", []) or []) if p != path]
        self._persist("scan.excludes", excludes)
        self._rebuild_excludes_list()

    def _on_reset_excludes(self, _button: Gtk.Button) -> None:
        self._persist("scan.excludes", list(DEFAULT_EXCLUDES))
        self._rebuild_excludes_list()
        self.exclude_error_label.set_visible(False)

    # ---- Mounts ---------------------------------------------------------

    def _build_mounts_group(self) -> None:
        group = PrefGroup("Mounts")

        self.mounts_hidden_switch = Gtk.Switch()
        self.mounts_hidden_switch.set_active(bool(self.settings.get("mounts.show_hidden", False)))
        self.mounts_hidden_switch.connect(
            "notify::active",
            lambda sw, _pspec: self._persist("mounts.show_hidden", sw.get_active()),
        )
        group.add_row(
            PrefRow(
                "Show hidden filesystems",
                self.mounts_hidden_switch,
                "Include pseudo and virtual filesystems in the Overview page.",
            )
        )

        self.hidden_fstypes_entry = Gtk.Entry()
        self.hidden_fstypes_entry.set_width_chars(32)
        self.hidden_fstypes_entry.set_text(
            ", ".join(self.settings.get("mounts.hidden_fstypes", []) or [])
        )
        self.hidden_fstypes_entry.connect("activate", self._on_hidden_fstypes_committed)
        self.hidden_fstypes_entry.connect("focus-out-event", self._on_hidden_fstypes_committed)
        group.add_row(
            PrefRow(
                "Hidden filesystem types",
                self.hidden_fstypes_entry,
                "Comma-separated fstypes (e.g. squashfs, tmpfs) hidden by default.",
            )
        )

        self.pack_start(group, False, False, 0)
        self.mounts_group = group

    def _on_hidden_fstypes_committed(self, entry: Gtk.Entry, *_args: object) -> bool:
        values = [t.strip() for t in entry.get_text().split(",") if t.strip()]
        self._persist("mounts.hidden_fstypes", values)
        return False

    # ---- Explorer ---------------------------------------------------------

    def _build_explorer_group(self) -> None:
        group = PrefGroup("Explorer")

        self.top_n_bold_spin = Gtk.SpinButton.new_with_range(0, 10, 1)
        self.top_n_bold_spin.set_value(int(self.settings.get("explorer.top_n_bold", 3)))
        self.top_n_bold_spin.connect("value-changed", self._on_top_n_bold_changed)
        group.add_row(
            PrefRow(
                "Bold the largest N children",
                self.top_n_bold_spin,
                "Highlight the N largest items directly under a selected folder.",
            )
        )

        reset_columns_button = Gtk.Button(label="Reset column layout")
        reset_columns_button.set_halign(Gtk.Align.START)
        reset_columns_button.get_accessible().set_name("Reset column layout")
        reset_columns_button.connect("clicked", self._on_reset_columns)
        group.add_row(reset_columns_button)

        self.pack_start(group, False, False, 0)
        self.explorer_group = group

    def _on_top_n_bold_changed(self, spin: Gtk.SpinButton) -> None:
        value = spin.get_value_as_int()
        self._persist("explorer.top_n_bold", value)
        explorer = self.window.pages.get("explorer")
        setter = getattr(explorer, "set_top_n_bold", None)
        if callable(setter):
            setter(value)

    def _on_reset_columns(self, _button: Gtk.Button) -> None:
        defaults = DEFAULTS["explorer"]
        self.settings.set("explorer.columns", list(defaults["columns"]))
        self.settings.set("explorer.widths", {})
        self.settings.set("explorer.hidden_columns", list(defaults["hidden_columns"]))
        self.settings.set("explorer.sort", {"column": "alloc", "descending": True})
        try:
            self.settings.save()
        except OSError as exc:
            print(f"could not save settings: {exc}")
        explorer = self.window.pages.get("explorer")
        tree = getattr(explorer, "tree", None)
        restore = getattr(tree, "restore_state", None)
        if callable(restore):
            restore()

    # ---- About ---------------------------------------------------------

    def _build_about_group(self) -> None:
        group = PrefGroup("About")

        version_label = Gtk.Label(label=__version__)
        version_label.get_style_context().add_class("mono")
        group.add_row(PrefRow("Version", version_label))

        link = Gtk.LinkButton.new_with_label(_REPO_URL, "Project repository")
        group.add_row(PrefRow("Source", link))

        config_path_label = Gtk.Label(label=f"Config file: {self.settings.path}")
        config_path_label.set_xalign(0.0)
        config_path_label.set_selectable(True)
        ctx = config_path_label.get_style_context()
        ctx.add_class("mono")
        ctx.add_class("dim")
        group.add_row(config_path_label)

        self.pack_start(group, False, False, 0)
        self.about_group = group

    # ---- public API ---------------------------------------------------------

    def reload_from_settings(self) -> None:
        """Re-read every control's state from ``self.settings``.

        Called on ``on_shown`` so a setting changed elsewhere (e.g. the
        Explorer toolbar's "show hidden" toggle) is reflected here too.
        """
        self.theme_combo.set_active_id(self.settings.get("theme", self.app.theme.id))
        self._set_units_radio_active(self.settings.get("units", "decimal"))
        self._set_primary_radio_active(self.settings.get("primary_size", "allocated"))

        self.follow_symlinks_switch.set_active(
            bool(self.settings.get("scan.follow_symlinks", False))
        )
        self.cross_mounts_switch.set_active(bool(self.settings.get("scan.cross_mounts", False)))
        self.count_hardlinks_once_switch.set_active(
            bool(self.settings.get("scan.count_hardlinks_once", True))
        )
        self.show_hidden_switch.set_active(bool(self.settings.get("scan.show_hidden", True)))
        self.top_files_spin.set_value(int(self.settings.get("scan.top_files", 50)))

        self._rebuild_excludes_list()

        self.mounts_hidden_switch.set_active(bool(self.settings.get("mounts.show_hidden", False)))
        self.hidden_fstypes_entry.set_text(
            ", ".join(self.settings.get("mounts.hidden_fstypes", []) or [])
        )

        self.top_n_bold_spin.set_value(int(self.settings.get("explorer.top_n_bold", 3)))
