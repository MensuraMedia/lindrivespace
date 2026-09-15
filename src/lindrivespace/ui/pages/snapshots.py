"""Snapshots page: save/browse scans and diff two of them (concept doc §3.4).

Quiet, table-driven page (Direction B/D): a toolbar, a sortable list of saved
snapshots, and a compare section producing a coloured diff table. All heavy
lifting (save/load/diff) lives in ``core.snapshot``; this module is the GTK
glue plus the two small pieces of state it needs (the selected snapshot list
row, the two "compare" picks).
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk, Pango  # noqa: E402

from lindrivespace.config.layout import Layout  # noqa: E402
from lindrivespace.core.fsnode import FsNode  # noqa: E402
from lindrivespace.core.snapshot import (  # noqa: E402
    DiffEntry,
    SnapshotMeta,
    default_snapshot_dir,
    diff_snapshots,
    list_snapshots,
    load_snapshot,
    save_snapshot,
    snapshot_filename,
)
from lindrivespace.core.units import format_bytes, format_count  # noqa: E402
from lindrivespace.ui.pages.base import BasePage  # noqa: E402

# Snapshot list store columns
_L_META, _L_ROOT, _L_SAVED, _L_ENTRIES, _L_ALLOC, _L_FILE, _L_ENTRIES_RAW, _L_ALLOC_RAW = range(8)

# Diff result store columns
_D_PATH, _D_KIND, _D_BEFORE, _D_AFTER, _D_DELTA, _D_DELTA_RAW = range(6)


def _format_saved_at(iso_text: str) -> str:
    """``meta.saved_at`` (a full ISO 8601 UTC timestamp) as "YYYY-MM-DD HH:MM".

    Falls back to the raw text if it doesn't parse (forward-compat with a
    format this version doesn't know about).
    """
    try:
        return datetime.fromisoformat(iso_text).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso_text


class SnapshotsPage(BasePage):
    title = "Snapshots"

    def build_content(self) -> None:
        self.add_title(self.title, "Saved scans and diffs between them")

        self._snapshot_metas: list[SnapshotMeta] = []
        self._kind_colors: dict[str, tuple[float, float, float]] = {
            "grew": self.theme.rgb("accent"),
            "shrank": self.theme.rgb("aubergine"),
            "new": self.theme.rgb("warn"),
            "deleted": self.theme.rgb("fg_dim"),
        }

        self._build_toolbar()
        self._build_snapshot_list()
        self.add_separator()
        self._build_compare_section()

        self.reload()

    # ---- toolbar ------------------------------------------------------

    def _build_toolbar(self) -> None:
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=Layout.spacing.SM)
        self.save_button = Gtk.Button(label="Save current scan")
        self.save_button.connect("clicked", self._on_save_clicked)
        open_button = Gtk.Button(label="Open snapshot…")
        open_button.connect("clicked", self._on_open_clicked)
        self.delete_button = Gtk.Button(label="Delete")
        self.delete_button.set_sensitive(False)
        self.delete_button.connect("clicked", lambda _b: self.delete())
        toolbar.pack_start(self.save_button, False, False, 0)
        toolbar.pack_start(open_button, False, False, 0)
        toolbar.pack_start(self.delete_button, False, False, 0)
        self.pack_start(toolbar, False, False, 0)

    # ---- snapshot list --------------------------------------------------

    def _build_snapshot_list(self) -> None:
        self.add_section("SAVED SNAPSHOTS")
        self.list_store = Gtk.ListStore(object, str, str, str, str, str, int, int)
        self.list_view = Gtk.TreeView(model=self.list_store)
        self.list_view.set_fixed_height_mode(True)
        self.list_view.get_selection().connect("changed", self._on_selection_changed)

        specs = (
            ("Root path", _L_ROOT, _L_ROOT, 320),
            ("Saved at", _L_SAVED, _L_SAVED, 160),
            ("Entries", _L_ENTRIES, _L_ENTRIES_RAW, 90),
            ("Allocated", _L_ALLOC, _L_ALLOC_RAW, 110),
            ("File", _L_FILE, _L_FILE, 200),
        )
        for title, display_col, sort_col, width in specs:
            renderer = Gtk.CellRendererText()
            renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
            column = Gtk.TreeViewColumn(title, renderer, text=display_col)
            column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            column.set_resizable(True)
            column.set_sort_column_id(sort_col)
            column.set_fixed_width(width)
            self.list_view.append_column(column)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_min_content_height(160)
        scroller.add(self.list_view)
        self.pack_start(scroller, False, False, 0)

    # ---- compare section --------------------------------------------------

    def _build_compare_section(self) -> None:
        self.add_section("COMPARE SNAPSHOTS")

        # Row 1: the two snapshot pickers -- these can be as wide as the page,
        # so they get their own row and share the space evenly.
        pickers_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=Layout.spacing.SM)
        pickers_row.pack_start(Gtk.Label(label="Compare A"), False, False, 0)
        self.combo_a = Gtk.ComboBoxText()
        pickers_row.pack_start(self.combo_a, True, True, 0)
        pickers_row.pack_start(Gtk.Label(label="Compare B"), False, False, 0)
        self.combo_b = Gtk.ComboBoxText()
        pickers_row.pack_start(self.combo_b, True, True, 0)
        self.pack_start(pickers_row, False, False, 0)

        # Row 2: threshold + the action button -- fixed-size controls that must
        # never compete with the pickers' expand above for horizontal space.
        controls_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=Layout.spacing.SM)
        controls_row.pack_start(Gtk.Label(label="Δ min (MB)"), False, False, 0)
        adjustment = Gtk.Adjustment(
            value=1, lower=0, upper=1_000_000, step_increment=1, page_increment=10
        )
        self.threshold_spin = Gtk.SpinButton(adjustment=adjustment, climb_rate=1.0, digits=0)
        self.threshold_spin.set_numeric(True)
        controls_row.pack_start(self.threshold_spin, False, False, 0)
        compare_button = Gtk.Button(label="Compare")
        compare_button.connect("clicked", self._on_compare_clicked)
        controls_row.pack_start(compare_button, False, False, 0)
        self.pack_start(controls_row, False, False, 0)

        self.diff_store = Gtk.ListStore(str, str, str, str, str, int)
        self.diff_view = Gtk.TreeView(model=self.diff_store)
        self.diff_view.set_fixed_height_mode(True)

        specs = (
            ("Path", _D_PATH, _D_PATH, 360),
            ("Change", _D_KIND, _D_KIND, 90),
            ("Before", _D_BEFORE, _D_BEFORE, 110),
            ("After", _D_AFTER, _D_AFTER, 110),
            ("Delta", _D_DELTA, _D_DELTA_RAW, 110),
        )
        for title, display_col, sort_col, width in specs:
            renderer = Gtk.CellRendererText()
            renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
            column = Gtk.TreeViewColumn(title, renderer, text=display_col)
            column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            column.set_resizable(True)
            column.set_sort_column_id(sort_col)
            column.set_fixed_width(width)
            column.set_cell_data_func(renderer, self._color_diff_cell)
            self.diff_view.append_column(column)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_min_content_height(220)
        scroller.add(self.diff_view)
        self.pack_start(scroller, True, True, 0)

    def _color_diff_cell(
        self,
        _column: Gtk.TreeViewColumn,
        cell: Gtk.CellRenderer,
        model: Gtk.TreeModel,
        it: Gtk.TreeIter,
        _data: object,
    ) -> None:
        kind = model.get_value(it, _D_KIND)
        rgb = self._kind_colors.get(kind)
        if rgb is None:
            cell.set_property("foreground-set", False)
            return
        cell.set_property("foreground-rgba", Gdk.RGBA(*rgb, 1.0))

    # ---- lifecycle ------------------------------------------------------

    def on_shown(self) -> None:
        self.reload()

    # ---- public API -------------------------------------------------------

    def save_current(self, root: FsNode, root_path: str) -> Path | None:
        """Save ``root`` (a finished scan) as a new snapshot; returns its path."""
        try:
            dest = default_snapshot_dir() / snapshot_filename(root_path)
            save_snapshot(root, dest)
        except OSError as exc:
            print(f"snapshots: save failed: {exc}", file=sys.stderr)
            return None
        self.reload()
        return dest

    def reload(self) -> None:
        """Refresh the snapshot list, the compare combos, and button sensitivity."""
        self._refresh_save_sensitivity()

        metas = list_snapshots(default_snapshot_dir())
        self._snapshot_metas = metas

        self.list_store.clear()
        for meta in metas:
            self.list_store.append(
                [
                    meta,
                    meta.root_path,
                    _format_saved_at(meta.saved_at),
                    format_count(meta.entries),
                    format_bytes(meta.alloc),
                    meta.path.name,
                    meta.entries,
                    meta.alloc,
                ]
            )

        self.combo_a.remove_all()
        self.combo_b.remove_all()
        for meta in metas:
            label = f"{meta.root_path} — {_format_saved_at(meta.saved_at)}"
            self.combo_a.append_text(label)
            self.combo_b.append_text(label)
        if metas:
            self.combo_a.set_active(0)
            self.combo_b.set_active(min(1, len(metas) - 1))

        self.delete_button.set_sensitive(
            self.list_view.get_selection().get_selected()[1] is not None
        )

    def delete(self, confirm: bool = True) -> bool:
        """Delete the selected snapshot; asks first unless ``confirm`` is False."""
        selection = self.list_view.get_selection()
        model, it = selection.get_selected()
        if it is None:
            return False
        meta: SnapshotMeta = model.get_value(it, _L_META)
        if confirm:
            dialog = Gtk.MessageDialog(
                transient_for=self.window,
                modal=True,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.OK_CANCEL,
                text=f"Delete snapshot {meta.path.name}?",
            )
            try:
                response = dialog.run()
            finally:
                dialog.destroy()
            if response != Gtk.ResponseType.OK:
                return False
        try:
            meta.path.unlink()
        except OSError as exc:
            print(f"snapshots: delete failed for {meta.path}: {exc}", file=sys.stderr)
            return False
        self.reload()
        return True

    # ---- handlers -----------------------------------------------------

    def _refresh_save_sensitivity(self) -> None:
        explorer = self.window.pages.get("explorer")
        model = getattr(explorer, "model", None)
        root = getattr(model, "root", None)
        self.save_button.set_sensitive(root is not None)

    def _on_save_clicked(self, _button: Gtk.Button) -> None:
        explorer = self.window.pages.get("explorer")
        model = getattr(explorer, "model", None)
        root = getattr(model, "root", None)
        if root is None:
            return
        self.save_current(root, root.path())

    def _on_open_clicked(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileChooserDialog(
            title="Open Snapshot",
            transient_for=self.window,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN,
            Gtk.ResponseType.OK,
        )
        file_filter = Gtk.FileFilter()
        file_filter.set_name("Snapshots (*.json.gz)")
        file_filter.add_pattern("*.json.gz")
        dialog.add_filter(file_filter)
        directory = default_snapshot_dir()
        if directory.exists():
            dialog.set_current_folder(str(directory))
        try:
            if dialog.run() == Gtk.ResponseType.OK:
                filename = dialog.get_filename()
                if filename:
                    self._import_snapshot(Path(filename))
        finally:
            dialog.destroy()

    def _import_snapshot(self, chosen: Path) -> None:
        """Copy an externally-picked snapshot into the managed directory."""
        directory = default_snapshot_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
            if chosen.resolve().parent != directory.resolve():
                dest = directory / chosen.name
                if dest.resolve() != chosen.resolve():
                    shutil.copy2(chosen, dest)
        except OSError as exc:
            print(f"snapshots: could not import {chosen}: {exc}", file=sys.stderr)
        self.reload()

    def _on_selection_changed(self, selection: Gtk.TreeSelection) -> None:
        _model, it = selection.get_selected()
        self.delete_button.set_sensitive(it is not None)

    def _combo_meta(self, combo: Gtk.ComboBoxText) -> SnapshotMeta | None:
        idx = combo.get_active()
        if idx < 0 or idx >= len(self._snapshot_metas):
            return None
        return self._snapshot_metas[idx]

    def _on_compare_clicked(self, _button: Gtk.Button) -> None:
        meta_a = self._combo_meta(self.combo_a)
        meta_b = self._combo_meta(self.combo_b)
        if meta_a is None or meta_b is None:
            return
        try:
            root_a, _meta_a = load_snapshot(meta_a.path)
            root_b, _meta_b = load_snapshot(meta_b.path)
        except (OSError, ValueError) as exc:
            print(f"snapshots: compare failed to load: {exc}", file=sys.stderr)
            return
        min_delta = max(0, int(self.threshold_spin.get_value())) * 1_000_000
        entries = diff_snapshots(root_a, root_b, min_delta=min_delta)
        self._populate_diff(entries)

    def _populate_diff(self, entries: list[DiffEntry]) -> None:
        self.diff_store.clear()
        for entry in entries:
            sign = "+" if entry.delta >= 0 else "-"
            delta_text = f"{sign}{format_bytes(abs(entry.delta))}"
            self.diff_store.append(
                [
                    entry.path,
                    entry.kind,
                    format_bytes(entry.before),
                    format_bytes(entry.after),
                    delta_text,
                    entry.delta,
                ]
            )
