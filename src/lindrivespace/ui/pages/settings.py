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
from gi.repository import Gtk, Pango  # noqa: E402

from lindrivespace import __version__  # noqa: E402
from lindrivespace.config.layout import Layout  # noqa: E402
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
        self._build_scheduler_group()
        self._build_mounts_group()
        self._build_explorer_group()
        self._build_diagnostics_group()
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
        self.auto_scan_switch = self._add_scan_switch(
            group,
            "auto_on_start",
            "Scan all mounts on startup",
            "A few seconds after launch, scan the primary and secondary mountpoints, then the rest",
            default=True,
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

        self.top_min_spin = Gtk.SpinButton.new_with_range(0, 1_048_576, 16)
        self.top_min_spin.set_value(int(self.settings.get("scan.top_min_bytes", 65_536)) // 1024)
        self.top_min_spin.connect("value-changed", self._on_top_min_changed)
        group.add_row(
            PrefRow(
                "Smallest file kept for analysis (KB)",
                self.top_min_spin,
                "Files below this size are counted but not listed in Top files / Types / Age. "
                "64 KB skips 90 % of files for under 3 % of the bytes; 0 keeps every file.",
            )
        )

        self.pack_start(group, False, False, 0)
        self.scanning_group = group

    def _add_scan_switch(
        self, group: PrefGroup, key: str, label: str, description: str, default: bool = False
    ) -> Gtk.Switch:
        switch = Gtk.Switch()
        switch.set_active(bool(self.settings.get(f"scan.{key}", default)))
        switch.connect(
            "notify::active",
            lambda sw, _pspec, k=key: self._persist(f"scan.{k}", sw.get_active()),
        )
        group.add_row(PrefRow(label, switch, description))
        return switch

    def _on_top_files_changed(self, spin: Gtk.SpinButton) -> None:
        self._persist("scan.top_files", spin.get_value_as_int())

    def _on_top_min_changed(self, spin: Gtk.SpinButton) -> None:
        self._persist("scan.top_min_bytes", spin.get_value_as_int() * 1024)

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

    # ---- Background collection (scheduler) ---------------------------------------

    def _build_scheduler_group(self) -> None:
        from lindrivespace.services import scheduler

        group = PrefGroup("Background collection")
        st = scheduler.status()

        self.scheduler_switch = Gtk.Switch()
        self.scheduler_switch.set_active(st.active)
        self.scheduler_switch.set_sensitive(st.available)
        self.scheduler_switch.get_accessible().set_name("Scan scheduler")
        self.scheduler_switch.connect("notify::active", self._on_scheduler_toggled)
        group.add_row(
            PrefRow(
                "Scan scheduler",
                self.scheduler_switch,
                "Run a background service agent that records usage and growth trends on a "
                "schedule, even while the app is closed (systemd user timer).",
            )
        )

        self.scheduler_interval = Gtk.ComboBoxText()
        for key, label, _cal in scheduler.INTERVALS:
            self.scheduler_interval.append(key, label)
        self.scheduler_interval.set_active_id(st.interval)
        self.scheduler_interval.get_accessible().set_name("Collection interval")
        self.scheduler_interval.connect("changed", lambda _c: self._apply_scheduler())
        group.add_row(PrefRow("Interval", self.scheduler_interval, "How often the agent runs."))

        self.scheduler_scan_switch = Gtk.Switch()
        self.scheduler_scan_switch.set_active(st.scan)
        self.scheduler_scan_switch.get_accessible().set_name("Full scan on each run")
        self.scheduler_scan_switch.connect("notify::active", lambda *_a: self._apply_scheduler())
        group.add_row(
            PrefRow(
                "Full scan on each run",
                self.scheduler_scan_switch,
                "Also scan every mount (slower); otherwise only used/free space is sampled.",
            )
        )

        run_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.scheduler_run_button = Gtk.Button(label="Run now")
        self.scheduler_run_button.get_accessible().set_name("Run collection now")
        self.scheduler_run_button.connect("clicked", self._on_scheduler_run_now)
        run_row.pack_start(self.scheduler_run_button, False, False, 0)
        self.scheduler_status_label = Gtk.Label(label="")
        self.scheduler_status_label.set_xalign(0.0)
        self.scheduler_status_label.set_line_wrap(True)
        self.scheduler_status_label.get_style_context().add_class("dim")
        run_row.pack_start(self.scheduler_status_label, True, True, 0)
        group.add_row(run_row)
        self._update_scheduler_status(st)

        self.pack_start(group, False, False, 0)
        self.scheduler_group = group

    def _update_scheduler_status(self, st=None) -> None:  # type: ignore[no-untyped-def]
        from lindrivespace.services import scheduler

        st = st or scheduler.status()
        if not st.available:
            text = f"Scheduler unavailable: {st.detail}"
        elif st.active:
            parts = [st.detail]
            if st.next_run:
                parts.append(f"next run {st.next_run}")
            if st.last_run:
                parts.append(f"last run {st.last_run}")
            text = " · ".join(parts)
        else:
            text = "Not scheduled. Turn on the scheduler or use Run now."
        self.scheduler_status_label.set_text(text)

    def _on_scheduler_toggled(self, switch: Gtk.Switch, _pspec: object) -> None:
        from lindrivespace.services import scheduler

        if switch.get_active():
            ok, msg = scheduler.enable(
                self.scheduler_interval.get_active_id() or "daily",
                scan=self.scheduler_scan_switch.get_active(),
            )
        else:
            ok, msg = scheduler.disable()
        if not ok:
            self.scheduler_status_label.set_text(f"Could not change the scheduler: {msg}")
            return
        self._update_scheduler_status()

    def _apply_scheduler(self) -> None:
        if (
            getattr(self, "scheduler_switch", None) is not None
            and self.scheduler_switch.get_active()
        ):
            self._on_scheduler_toggled(self.scheduler_switch, None)

    def _on_scheduler_run_now(self, _button: Gtk.Button) -> None:
        from lindrivespace.services import scheduler

        ok, msg = scheduler.run_now()
        self.scheduler_status_label.set_text(msg if ok else f"Run failed: {msg}")
        signal = getattr(self.app, "history_signal", None)
        if signal is not None:
            signal.emit("changed")

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

        self.role_combos: dict[str, Gtk.ComboBoxText] = {}
        self._role_guard = False
        for role, desc in (
            ("primary", "Badged and listed first on the Overview (e.g. your system disk)."),
            ("secondary", "Badged second on the Overview (e.g. a data or backup drive)."),
        ):
            combo = Gtk.ComboBoxText()
            combo.set_size_request(220, -1)
            self.role_combos[role] = combo
            self._fill_role_combo(role)
            combo.connect("changed", self._on_role_changed, role)
            group.add_row(PrefRow(f"{role.capitalize()} mountpoint", combo, desc))

        self.pack_start(group, False, False, 0)
        self.mounts_group = group

    def _fill_role_combo(self, role: str) -> None:
        combo = self.role_combos[role]
        current = str(self.settings.get(f"mounts.{role}", "") or "")
        overview = self.window.pages.get("overview")
        known = list(getattr(overview, "known_mountpoints", list)())
        if current and current not in known:
            known.append(current)
        self._role_guard = True
        try:
            combo.remove_all()
            combo.append("", "None")
            for mp in known:
                combo.append(mp, mp)
            if not combo.set_active_id(current):
                combo.set_active(0)
        finally:
            self._role_guard = False

    def _on_role_changed(self, combo: Gtk.ComboBoxText, role: str) -> None:
        if self._role_guard:
            return
        value = combo.get_active_id() or ""
        other = "secondary" if role == "primary" else "primary"
        if value and self.settings.get(f"mounts.{other}", "") == value:
            self._persist(f"mounts.{other}", "")  # a mountpoint has one role
            self._fill_role_combo(other)
        self._persist(f"mounts.{role}", value)
        overview = self.window.pages.get("overview")
        refresh = getattr(overview, "refresh_roles", None)
        if callable(refresh):
            refresh()

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

    # ---- Diagnostics (logging) -------------------------------------------

    def _build_diagnostics_group(self) -> None:
        from lindrivespace import logsetup

        group = PrefGroup("Diagnostics")

        self.log_dir_chooser = Gtk.FileChooserButton(
            title="Choose the log folder", action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        self.log_dir_chooser.set_width_chars(28)
        self.log_dir_chooser.get_accessible().set_name("Log folder")
        self.log_dir_chooser.connect("file-set", self._on_log_dir_set)
        reset_dir = Gtk.Button(label="Default")
        reset_dir.get_accessible().set_name("Reset log folder to default")
        reset_dir.connect("clicked", lambda _b: self._set_log_dir(""))
        dir_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=Layout.spacing.XS)
        dir_box.pack_start(self.log_dir_chooser, True, True, 0)
        dir_box.pack_start(reset_dir, False, False, 0)
        group.add_row(
            PrefRow(
                "Log folder",
                dir_box,
                f"Default: {logsetup.log_dir()} — rotating file, 1 MB × 5. Applied immediately.",
            )
        )

        self.log_level_combo = Gtk.ComboBoxText()
        for key, label, _value in logsetup.LEVELS:
            self.log_level_combo.append(key, label)
        self.log_level_combo.get_accessible().set_name("Log level")
        self.log_level_combo.connect("changed", self._on_log_level_changed)
        group.add_row(
            PrefRow(
                "Log level",
                self.log_level_combo,
                "Debug records every scan step and GTK message; Warnings keeps only problems.",
            )
        )

        self.log_path_label = Gtk.Label(label="")
        self.log_path_label.set_xalign(0.0)
        self.log_path_label.set_selectable(True)
        self.log_path_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        ctx = self.log_path_label.get_style_context()
        ctx.add_class("mono")
        ctx.add_class("dim")
        open_log = Gtk.Button(label="Open log folder")
        open_log.get_accessible().set_name("Open log folder")
        open_log.connect("clicked", lambda _b: self.window.open_log_folder())
        group.add_row(PrefRow("Current log file", open_log))
        group.add_row(self.log_path_label)

        self.pack_start(group, False, False, 0)
        self._reload_diagnostics()

    def _reload_diagnostics(self) -> None:
        from lindrivespace import logsetup

        folder = str(self.settings.get("logging.dir") or "")
        self._guard = True
        try:
            target = folder or str(logsetup.log_dir())
            if os.path.isdir(target):
                self.log_dir_chooser.set_current_folder(target)
            level = str(self.settings.get("logging.level") or "info")
            self.log_level_combo.set_active_id(
                level if level in {k for k, _l, _v in logsetup.LEVELS} else "info"
            )
        finally:
            self._guard = False
        path = logsetup.log_path()
        self.log_path_label.set_text(str(path) if path else "log file unavailable (stderr only)")

    def _set_log_dir(self, folder: str) -> None:
        self._persist("logging.dir", folder)
        self.app.apply_logging_settings()
        self._reload_diagnostics()

    def _on_log_dir_set(self, chooser: Gtk.FileChooserButton) -> None:
        if getattr(self, "_guard", False):
            return
        folder = chooser.get_filename() or ""
        self._set_log_dir(folder)

    def _on_log_level_changed(self, combo: Gtk.ComboBoxText) -> None:
        if getattr(self, "_guard", False):
            return
        level = combo.get_active_id() or "info"
        self._persist("logging.level", level)
        self.app.apply_logging_settings()
        self._reload_diagnostics()

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

        group.add_row(
            PrefRow(
                "Diagnostics",
                Gtk.Label(label="see the Diagnostics card above"),
                "Errors and GTK warnings are written to a rotating log (1 MB × 5); "
                "run with --debug for verbose output.",
            )
        )

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
        self.top_min_spin.set_value(int(self.settings.get("scan.top_min_bytes", 65_536)) // 1024)

        self._rebuild_excludes_list()

        self.mounts_hidden_switch.set_active(bool(self.settings.get("mounts.show_hidden", False)))
        for role in ("primary", "secondary"):
            self._fill_role_combo(role)
        self.hidden_fstypes_entry.set_text(
            ", ".join(self.settings.get("mounts.hidden_fstypes", []) or [])
        )

        self.top_n_bold_spin.set_value(int(self.settings.get("explorer.top_n_bold", 3)))
