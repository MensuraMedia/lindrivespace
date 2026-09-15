"""History page (WP17) -- automatic historical disk-usage trends.

Replaces the old Snapshots feature (save/diff scans, now dropped). Disk
usage is recorded automatically by the app (``LinDriveSpaceApp.history`` /
``record_usage_samples`` / ``record_scan_sample``); this page is a read-only
window onto that data via ``core.history.HistoryStore``:

- a mount/path picker + period chips (Day/Week/Month/Year/All, remembered in
  ``settings["history.period"]``) driving a :class:`TrendChart`,
- a small stats row (first / latest / change / growth per day) -- the
  **Change** tile is clickable and reveals *where* space changed: a table of
  folders and files diffed between two auto-saved scan snapshots
  (``core.changes``), and
- **Pattern History**: named bookmarks of a particular path/period view,
  saved with an inline entry row (no modal dialog).

The module keeps the historical ``snapshots`` page id (see
``ui/pages/__init__.py``, whose sidebar label is now "History") so the page
registry doesn't need touching; :class:`SnapshotsPage` is kept below as a
thin alias for anything still importing the old name.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, GObject, Gtk, Pango  # noqa: E402

from lindrivespace.config.layout import Layout  # noqa: E402
from lindrivespace.core import changes  # noqa: E402
from lindrivespace.core.history import PERIODS, HistoryStore, Pattern  # noqa: E402
from lindrivespace.core.snapshot import default_snapshot_dir  # noqa: E402
from lindrivespace.core.units import format_bytes  # noqa: E402
from lindrivespace.services import forkwork  # noqa: E402
from lindrivespace.ui.pages.base import BasePage  # noqa: E402
from lindrivespace.ui.widgets.kpi_tile import KpiTile  # noqa: E402
from lindrivespace.ui.widgets.settings_rows import PrefGroup  # noqa: E402
from lindrivespace.ui.widgets.trend_chart import TrendChart  # noqa: E402

_SPACING = Layout.spacing
_DEFAULT_PERIOD = "week"
_CHANGE_ROWS_MAX = 300
_KIND_LABELS: dict[str, str] = {
    "grew": "Grew",
    "shrank": "Shrank",
    "new": "New",
    "deleted": "Deleted",
}
_PERIOD_LABELS: dict[str, str] = {pid: label for pid, label, _span in PERIODS}


def _apply_label_colour(
    label: Gtk.Label, hex_value: str, previous: Gtk.CssProvider | None
) -> Gtk.CssProvider:
    """Scope a foreground colour to one label (see Settings' ``_style_danger_label``)."""
    ctx = label.get_style_context()
    if previous is not None:
        ctx.remove_provider(previous)
    provider = Gtk.CssProvider()
    provider.load_from_data(f"label {{ color: {hex_value}; }}".encode())
    ctx.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    return provider


class HistoryPage(BasePage):
    title = "History"

    def build_content(self) -> None:
        self.store: HistoryStore = getattr(self.app, "history", None) or HistoryStore()

        period = self.settings.get("history.period", _DEFAULT_PERIOD) or _DEFAULT_PERIOD
        self._period: str = period if period in _PERIOD_LABELS else _DEFAULT_PERIOD
        self._current_path: str | None = None
        self._period_guard = False
        self._path_guard = False
        self._change_provider: Gtk.CssProvider | None = None
        self.snapshot_dir: Path = default_snapshot_dir()
        self._change_open = False
        self._change_generation = 0

        self.add_title(
            self.title,
            "Disk usage is recorded automatically every time the app runs; "
            "pick a mount and a period.",
        )

        self._build_controls_row()
        self._build_chart_card()
        self._build_stats_row()
        self._build_change_panel()
        self._build_pattern_history()

        history_signal = getattr(self.app, "history_signal", None)
        if history_signal is not None:
            history_signal.connect("changed", self._on_history_changed)

        self.refresh()

    # ---- lifecycle ------------------------------------------------------------

    def on_shown(self) -> None:
        self.refresh()

    def _on_history_changed(self, _signal: object) -> None:
        self.refresh()

    # ---- construction -----------------------------------------------------

    def _build_controls_row(self) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=_SPACING.SM)

        self.path_combo = Gtk.ComboBoxText()
        self.path_combo.set_hexpand(True)
        self.path_combo.get_accessible().set_name("Mount or folder")
        self.path_combo.connect("changed", self._on_path_changed)
        row.pack_start(self.path_combo, True, True, 0)

        chips = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        chips.get_style_context().add_class("linked")
        self.period_buttons: dict[str, Gtk.ToggleButton] = {}
        for pid, label, _span in PERIODS:
            button = Gtk.ToggleButton(label=label)
            button.get_accessible().set_name(f"Period: {label}")
            button.connect("toggled", self._on_period_toggled, pid)
            chips.pack_start(button, False, False, 0)
            self.period_buttons[pid] = button
        row.pack_start(chips, False, False, 0)

        self.save_pattern_button = Gtk.Button(label="Save to Pattern History")
        self.save_pattern_button.connect("clicked", self._on_save_pattern_clicked)
        row.pack_start(self.save_pattern_button, False, False, 0)

        self.pack_start(row, False, False, 0)

    def _build_chart_card(self) -> None:
        self.chart_card = PrefGroup("Trend")
        self.chart_card.enable_copy()

        self.chart = TrendChart(self.theme)
        self.chart.set_hexpand(True)
        self.chart_card.add_row(self.chart)

        # A hidden text summary so PrefGroup.as_text() (Copy button) carries the
        # chart's numbers -- the chart itself is a drawing, not text.
        self.summary_label = Gtk.Label(label="")
        self.summary_label.set_xalign(0.0)
        self.summary_label.set_no_show_all(True)
        self.summary_label.set_visible(False)
        self.chart_card.add_row(self.summary_label)

        self.pack_start(self.chart_card, False, False, 0)

    def _build_stats_row(self) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=_SPACING.MD)
        row.set_homogeneous(True)

        self.tile_first = KpiTile(self.theme, "First", "—")
        self.tile_latest = KpiTile(self.theme, "Latest", "—")
        self.tile_change = KpiTile(self.theme, "Change", "—", detail="Click to see where")
        self.tile_growth = KpiTile(self.theme, "Growth / day", "—")

        # The Change tile is a button: clicking it reveals the "Where space changed" table.
        self.change_button = Gtk.Button()
        self.change_button.set_relief(Gtk.ReliefStyle.NONE)
        self.change_button.get_style_context().add_class("kpi-button")
        self.change_button.set_tooltip_text("Show which folders and files changed")
        self.change_button.get_accessible().set_name("Change: show where space changed")
        self.change_button.add(self.tile_change)
        self.change_button.connect("clicked", self._on_change_clicked)

        for tile in (self.tile_first, self.tile_latest, self.change_button, self.tile_growth):
            row.pack_start(tile, True, True, 0)

        self.pack_start(row, False, False, 0)

    def _build_change_panel(self) -> None:
        group = PrefGroup("Where space changed")
        group.enable_copy()
        self.change_group = group

        self.change_summary = Gtk.Label(label="")
        self.change_summary.set_xalign(0.0)
        self.change_summary.set_line_wrap(True)
        self.change_summary.get_style_context().add_class("dim")
        group.add_row(self.change_summary)

        # path, kind, before, after, delta (text), |delta| (sort), delta (sign), is_file, icon
        self.change_store = Gtk.ListStore(
            str, str, str, str, str, GObject.TYPE_INT64, GObject.TYPE_INT64, bool, str
        )
        self.change_view = Gtk.TreeView(model=self.change_store)
        self.change_view.set_headers_visible(True)
        self.change_view.set_enable_search(True)
        self.change_view.set_search_column(0)
        self.change_view.set_grid_lines(Gtk.TreeViewGridLines.BOTH)
        self.change_view.get_style_context().add_class("grid-table")
        self.change_view.get_accessible().set_name("Folders and files whose size changed")
        self.change_view.connect("row-activated", self._on_change_row_activated)

        icon = Gtk.CellRendererPixbuf()
        text = Gtk.CellRendererText()
        text.set_property("ellipsize", Pango.EllipsizeMode.MIDDLE)
        col = Gtk.TreeViewColumn("Folder / file")
        col.pack_start(icon, False)
        col.add_attribute(icon, "icon-name", 8)
        col.pack_start(text, True)
        col.add_attribute(text, "text", 0)
        col.set_expand(True)
        col.set_resizable(True)
        col.set_sort_column_id(0)
        self.change_view.append_column(col)

        for title, index, sort_id, align in (
            ("Change", 1, 1, 0.0),
            ("Before", 2, 5, 1.0),
            ("After", 3, 5, 1.0),
            ("Difference", 4, 6, 1.0),
        ):
            renderer = Gtk.CellRendererText()
            renderer.set_property("xalign", align)
            renderer.set_property("xpad", 6)
            if index != 1:
                renderer.set_property("family", "Ubuntu Mono")
            column = Gtk.TreeViewColumn(title, renderer, text=index)
            column.set_resizable(True)
            column.set_sort_column_id(sort_id)
            column.set_alignment(align)
            if title in ("Change", "Difference"):
                # growth (more space used) in the danger colour, reductions in the ok colour
                column.set_cell_data_func(renderer, self._change_colour_func)
            self.change_view.append_column(column)
        self.change_store.set_sort_column_id(5, Gtk.SortType.DESCENDING)

        frame = Gtk.Frame()
        frame.set_shadow_type(Gtk.ShadowType.IN)
        frame.get_style_context().add_class("mount-list-frame")
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_min_content_height(220)
        scroller.set_max_content_height(420)
        scroller.set_propagate_natural_height(True)
        scroller.add(self.change_view)
        frame.add(scroller)
        self.change_frame = frame
        group.add_row(frame)

        hint = Gtk.Label(label="Double-click a row to open it in the Explorer.")
        hint.set_xalign(0.0)
        hint.get_style_context().add_class("dim")
        group.add_row(hint)
        self.change_hint = hint

        group.set_no_show_all(True)
        group.set_visible(False)
        self.pack_start(group, False, False, 0)

    def _build_pattern_history(self) -> None:
        group = PrefGroup("Pattern History")

        self.pattern_save_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=_SPACING.SM)
        self.pattern_name_entry = Gtk.Entry()
        self.pattern_name_entry.set_hexpand(True)
        self.pattern_name_entry.get_accessible().set_name("New pattern name")
        self.pattern_name_entry.connect("activate", self._on_pattern_save_confirm)
        self.pattern_save_row.pack_start(self.pattern_name_entry, True, True, 0)

        confirm_button = Gtk.Button(label="Save")
        confirm_button.get_style_context().add_class("primary")
        confirm_button.connect("clicked", self._on_pattern_save_confirm)
        self.pattern_save_row.pack_start(confirm_button, False, False, 0)

        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.connect("clicked", self._on_pattern_save_cancel)
        self.pattern_save_row.pack_start(cancel_button, False, False, 0)

        self.pattern_save_row.set_no_show_all(True)
        self.pattern_save_row.set_visible(False)
        group.add_row(self.pattern_save_row)

        self.pattern_empty_label = Gtk.Label(label="Save a view to keep it here.")
        self.pattern_empty_label.set_xalign(0.0)
        self.pattern_empty_label.get_style_context().add_class("dim")
        group.add_row(self.pattern_empty_label)

        self.pattern_list = Gtk.ListBox()
        self.pattern_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.pattern_list.get_accessible().set_name("Saved pattern history views")
        group.add_row(self.pattern_list)

        self.pack_start(group, False, False, 0)
        self.pattern_group = group

    # ---- public API -------------------------------------------------------

    def select_path(self, path: str) -> None:
        """Select ``path`` in the picker (rebuilding it first if not yet listed)."""
        model = self.path_combo.get_model()
        if model is not None:
            for i, entry in enumerate(model):
                if entry[0] == path:
                    self._path_guard = True
                    self.path_combo.set_active(i)
                    self._path_guard = False
                    self._current_path = path
                    self._refresh_chart_and_stats()
                    return
        self._current_path = path
        self.refresh()

    def set_period(self, period: str) -> None:
        """Select ``period`` (one of ``core.history.PERIODS``' ids)."""
        if period not in _PERIOD_LABELS:
            return
        self._period = period
        self._persist("history.period", period)
        self._update_period_buttons()
        self._refresh_chart_and_stats()

    def save_current_view(self, name: str | None = None) -> Pattern | None:
        """Save the current path/period as a Pattern History entry."""
        path = self._current_path
        if not path:
            return None
        final_name = name.strip() if name and name.strip() else self._default_pattern_name(path)
        pattern = self.store.add_pattern(final_name, path, self._period)
        self._rebuild_pattern_list()
        return pattern

    def refresh(self) -> None:
        self._rebuild_path_combo()
        self._update_period_buttons()
        self._refresh_chart_and_stats()
        self._rebuild_pattern_list()

    # ---- settings -----------------------------------------------------------

    def _persist(self, key: str, value: object) -> None:
        self.settings.set(key, value)
        try:
            self.settings.save()
        except OSError as exc:
            print(f"history: could not save settings: {exc}")

    # ---- path combo ---------------------------------------------------------

    def _rebuild_path_combo(self) -> None:
        self._path_guard = True
        paths = self.store.paths()
        mounts = [p for p in paths if os.path.ismount(p)]
        others = [p for p in paths if p not in mounts]
        ordered = mounts + others

        previous = self._current_path
        self.path_combo.remove_all()
        for p in ordered:
            self.path_combo.append_text(p)

        if ordered:
            target = previous if previous in ordered else ordered[0]
            self.path_combo.set_active(ordered.index(target))
            self._current_path = target
        else:
            self._current_path = None
        self._path_guard = False

    def _on_path_changed(self, combo: Gtk.ComboBoxText) -> None:
        if self._path_guard:
            return
        self._current_path = combo.get_active_text()
        self._refresh_chart_and_stats()

    # ---- period chips ---------------------------------------------------------

    def _update_period_buttons(self) -> None:
        self._period_guard = True
        for pid, button in self.period_buttons.items():
            button.set_active(pid == self._period)
        self._period_guard = False

    def _on_period_toggled(self, button: Gtk.ToggleButton, pid: str) -> None:
        if self._period_guard:
            return
        if not button.get_active():
            if pid == self._period:  # keep single-selection semantics
                self._period_guard = True
                button.set_active(True)
                self._period_guard = False
            return
        self._period_guard = True
        for other_id, other_button in self.period_buttons.items():
            if other_id != pid:
                other_button.set_active(False)
        self._period_guard = False
        self.set_period(pid)

    # ---- chart + stats ----------------------------------------------------

    def _refresh_chart_and_stats(self) -> None:
        path = self._current_path
        if not path:
            self.chart.set_series([], period=self._period)
            self._set_stats(None)
            self.summary_label.set_text("")
            self.save_pattern_button.set_sensitive(False)
            if self._change_open:
                self._refresh_change_panel()
            return

        buckets = self.store.buckets(path, self._period)
        points = [(ts, used) for ts, used, _total in buckets]
        total = buckets[-1][2] if buckets else 0
        scans = [s.ts for s in self.store.series(path, self._period) if s.source == "scan"]
        self.chart.set_series(points, total=total, scans=scans, period=self._period)

        trend = self.store.trend(path, self._period)
        self._set_stats(trend)
        self.save_pattern_button.set_sensitive(bool(trend["samples"]))
        if self._change_open:
            self._refresh_change_panel()

        if trend["samples"]:
            self.summary_label.set_text(
                f"{path}: {format_bytes(int(trend['first']))} -> "
                f"{format_bytes(int(trend['last']))} over {trend['samples']} samples"
            )
        else:
            self.summary_label.set_text(f"{path}: no samples yet")

    def _set_stats(self, trend: dict[str, Any] | None) -> None:
        if not trend or not trend.get("samples"):
            self.tile_first.set_value("—", "", "")
            self.tile_latest.set_value("—", "", "")
            self.tile_change.set_value("—", "", "")
            self.tile_growth.set_value("—", "", "")
            return

        first = int(trend["first"])
        last = int(trend["last"])
        delta = int(trend["delta"])
        per_day = float(trend["per_day"])
        days_to_full = trend["days_to_full"]

        self.tile_first.set_value(format_bytes(first))
        self.tile_latest.set_value(format_bytes(last))

        sign = "+" if delta >= 0 else "-"
        self.tile_change.set_value(f"{sign}{format_bytes(abs(delta))}")
        if delta > 0:
            colour = self.theme.danger  # using more space -> closer to full
        elif delta < 0:
            colour = self.theme.ok
        else:
            colour = self.theme.fg_muted
        self._change_provider = _apply_label_colour(
            self.tile_change.value_label, colour, self._change_provider
        )

        growth_detail = f"full in ≈ {days_to_full:.0f} days" if days_to_full is not None else ""
        self.tile_growth.set_value(f"{format_bytes(int(abs(per_day)))}/day", detail=growth_detail)

    # ---- Where space changed ------------------------------------------------

    def show_changes(self, visible: bool = True) -> None:
        """Reveal (or hide) the folder/file change table under the stats row."""
        self._change_open = visible
        if visible:
            # show_all() is a no-op on a no-show-all widget: lift it for the call.
            self.change_group.set_no_show_all(False)
            self.change_group.show_all()
            self.change_group.set_no_show_all(True)
            self._refresh_change_panel()
        else:
            self.change_group.set_visible(False)
        self.tile_change.set_value(
            self.tile_change.value_label.get_text(),
            detail="Click to hide" if visible else "Click to see where",
        )

    def _on_change_clicked(self, _button: Gtk.Button) -> None:
        self.show_changes(not self._change_open)

    def _refresh_change_panel(self) -> None:
        """Diff the two chosen snapshots on a worker thread, then fill the table."""
        path = self._current_path
        self._change_generation += 1
        generation = self._change_generation
        self.change_store.clear()
        if not path:
            self.change_summary.set_text("Pick a mount or folder first.")
            self.change_frame.set_visible(False)
            self.change_hint.set_visible(False)
            return
        self.change_summary.set_text("Comparing scans…")
        period = self._period
        directory = self.snapshot_dir

        # Loading two snapshots (gzip + JSON + node rebuild) is pure CPU that held the
        # interpreter lock for up to 1.8 s on a thread; a forked child leaves the UI alone.
        def work() -> tuple[int, changes.ChangeReport | None]:
            count = changes.snapshot_count(directory, path)
            report = changes.change_report(directory, path, period) if count >= 2 else None
            return count, report

        def done(result: object, error: str | None) -> None:
            if error or not isinstance(result, tuple):
                self._fill_change_panel(generation, path, 0, None, error or "no result")
            else:
                count, report = result
                self._fill_change_panel(generation, path, count, report, None)

        forkwork.run_in_child(work, done)

    def _fill_change_panel(
        self,
        generation: int,
        path: str,
        count: int,
        report: changes.ChangeReport | None,
        error: str | None,
    ) -> bool:
        if generation != self._change_generation:
            return False  # a newer request superseded this one
        self.change_store.clear()
        if error:
            self.change_summary.set_text(f"Could not compare scans: {error}")
            self.change_frame.set_visible(False)
            self.change_hint.set_visible(False)
            return False
        if report is None:
            if count == 0:
                text = f"No completed scan of {path} has been kept yet. Scan it once to start."
            else:
                text = (
                    f"Only one scan of {path} has been kept so far. The next scan (or the "
                    "scheduler's next run) will show where space changed."
                )
            self.change_summary.set_text(text)
            self.change_frame.set_visible(False)
            self.change_hint.set_visible(False)
            return False

        sign = "+" if report.delta >= 0 else "-"
        before_text = changes.format_saved_at(report.before_at)
        after_text = changes.format_saved_at(report.after_at)
        window = f"{before_text} → {after_text}"
        shown = min(len(report.items), _CHANGE_ROWS_MAX)
        self.change_summary.set_text(
            f"{path}: {sign}{format_bytes(abs(report.delta))} between scans {window}. "
            f"{len(report.items)} changed folders and files"
            + (f" (largest {shown} shown)." if shown < len(report.items) else ".")
        )
        for item in report.items[:_CHANGE_ROWS_MAX]:
            delta_sign = "+" if item.delta >= 0 else "-"
            self.change_store.append(
                [
                    item.path,
                    _KIND_LABELS.get(item.kind, item.kind),
                    format_bytes(item.before) if item.before else "—",
                    format_bytes(item.after) if item.after else "—",
                    f"{delta_sign}{format_bytes(abs(item.delta))}",
                    abs(item.delta),
                    item.delta,
                    item.is_file,
                    "text-x-generic-symbolic" if item.is_file else "folder-symbolic",
                ]
            )
        self.change_frame.set_visible(bool(report.items))
        self.change_hint.set_visible(bool(report.items))
        if not report.items:
            self.change_summary.set_text(
                self.change_summary.get_text() + " Nothing moved by more than 1 MB."
            )
        return False

    def change_colour_for(self, delta: int) -> str:
        """Hex colour for a signed byte difference: red = grew/new, green = shrank/deleted."""
        if delta > 0:
            return self.theme.danger
        if delta < 0:
            return self.theme.ok
        return self.theme.fg_muted

    def _change_colour_func(
        self,
        _column: Gtk.TreeViewColumn,
        cell: Gtk.CellRendererText,
        model: Gtk.TreeModel,
        it: Gtk.TreeIter,
        _data: object = None,
    ) -> None:
        delta = int(model.get_value(it, 6))
        cell.set_property("foreground", self.change_colour_for(delta))
        cell.set_property("weight", 700 if delta > 0 else 400)

    def _on_change_row_activated(
        self, view: Gtk.TreeView, tree_path: Gtk.TreePath, _column: Gtk.TreeViewColumn
    ) -> None:
        root = self._current_path
        if not root:
            return
        model = view.get_model()
        rel = model[tree_path][0]
        full = os.path.join(root, rel)
        self.window.request_scan(root)
        explorer = self.window.pages.get("explorer")
        if explorer is not None and hasattr(explorer, "reveal_path"):
            if not explorer.reveal_path(full):
                explorer.reveal_path(os.path.dirname(full))

    # ---- Pattern History ----------------------------------------------------

    def _default_pattern_name(self, path: str) -> str:
        label = _PERIOD_LABELS.get(self._period, self._period)
        date_text = datetime.now().strftime("%Y-%m-%d")
        return f"{path} · {label} · {date_text}"

    def _on_save_pattern_clicked(self, _button: Gtk.Button) -> None:
        if not self._current_path:
            return
        self.pattern_name_entry.set_text(self._default_pattern_name(self._current_path))
        self.pattern_save_row.set_no_show_all(False)
        self.pattern_save_row.show_all()
        self.pattern_save_row.set_no_show_all(True)
        self.pattern_name_entry.grab_focus()
        self.pattern_name_entry.select_region(0, -1)

    def _on_pattern_save_confirm(self, _widget: Gtk.Widget) -> None:
        name = self.pattern_name_entry.get_text().strip()
        self.save_current_view(name or None)
        self.pattern_save_row.set_visible(False)

    def _on_pattern_save_cancel(self, _button: Gtk.Button) -> None:
        self.pattern_save_row.set_visible(False)

    def _rebuild_pattern_list(self) -> None:
        for child in list(self.pattern_list.get_children()):
            self.pattern_list.remove(child)

        patterns = self.store.patterns()
        has_patterns = bool(patterns)
        self.pattern_empty_label.set_visible(not has_patterns)
        self.pattern_list.set_visible(has_patterns)

        for pattern in patterns:
            self.pattern_list.add(self._build_pattern_row(pattern))
        self.pattern_list.show_all()

    def _build_pattern_row(self, pattern: Pattern) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.set_selectable(False)

        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=_SPACING.SM)
        outer.set_margin_top(4)
        outer.set_margin_bottom(4)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        name_label = Gtk.Label()
        name_label.set_xalign(0.0)
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        name_label.set_markup(f"<b>{GLib.markup_escape_text(pattern.name)}</b>")
        text_box.pack_start(name_label, False, False, 0)

        period_text = _PERIOD_LABELS.get(pattern.period, pattern.period)
        saved_text = datetime.fromtimestamp(pattern.created).strftime("%Y-%m-%d %H:%M")
        meta_label = Gtk.Label(label=f"{pattern.path} · {period_text} · saved {saved_text}")
        meta_label.set_xalign(0.0)
        meta_label.set_ellipsize(Pango.EllipsizeMode.END)
        meta_ctx = meta_label.get_style_context()
        meta_ctx.add_class("mono")
        meta_ctx.add_class("dim")
        text_box.pack_start(meta_label, False, False, 0)

        summary_label = Gtk.Label(
            label=(
                f"{format_bytes(pattern.first_used)} → {format_bytes(pattern.last_used)} "
                f"({pattern.samples} samples)"
            )
        )
        summary_label.set_xalign(0.0)
        summary_label.get_style_context().add_class("dim")
        text_box.pack_start(summary_label, False, False, 0)

        outer.pack_start(text_box, True, True, 0)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=_SPACING.XS)
        open_button = Gtk.Button(label="Open")
        open_button.get_style_context().add_class("flat")
        open_button.get_accessible().set_name(f"Open pattern {pattern.name}")
        open_button.connect("clicked", self._on_pattern_open, pattern)
        buttons.pack_start(open_button, False, False, 0)

        remove_button = Gtk.Button(label="Remove")
        remove_button.get_style_context().add_class("flat")
        remove_button.get_accessible().set_name(f"Remove pattern {pattern.name}")
        remove_button.connect("clicked", self._on_pattern_remove, pattern.id)
        buttons.pack_start(remove_button, False, False, 0)
        outer.pack_start(buttons, False, False, 0)

        row.add(outer)
        return row

    def _on_pattern_open(self, _button: Gtk.Button, pattern: Pattern) -> None:
        self.select_path(pattern.path)
        self.set_period(pattern.period)

    def _on_pattern_remove(self, _button: Gtk.Button, pattern_id: str) -> None:
        self.store.remove_pattern(pattern_id)
        self._rebuild_pattern_list()


# Thin alias: the page registry (``ui/pages/__init__.py``) still imports
# ``SnapshotsPage`` under the historical "snapshots" page id.
SnapshotsPage = HistoryPage
