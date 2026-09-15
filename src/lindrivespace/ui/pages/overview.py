"""Mounted filesystems page (Direction B): KPI strip, hidden/refresh controls,
one section per physical disk with a wrapping row of MountCards.

See ``docs/mockups/images/direction-b-overview-dashboard.png`` and
``.claude/memory/changes/2026-09-14-wp5-widgets.md`` for the widgets this page
wires together (``KpiTile``, ``MountCard``/``MountCardData``).
"""

from __future__ import annotations

import time
from dataclasses import replace

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from lindrivespace.config.layout import Layout  # noqa: E402
from lindrivespace.core.mounts import DiskInfo, MountInfo  # noqa: E402
from lindrivespace.core.units import format_bytes  # noqa: E402
from lindrivespace.models.mounts_model import MountsModel  # noqa: E402
from lindrivespace.services.mounts_service import MountsService  # noqa: E402
from lindrivespace.ui.pages.base import BasePage  # noqa: E402

_DIMS = Layout.dimensions
from lindrivespace.ui.widgets import KpiTile, MountCard, MountCardData  # noqa: E402

_STALE_SECONDS = 30.0


def _split_value_unit(text: str) -> tuple[str, str]:
    """Split a ``format_bytes`` result ("1.62 TB") into (value, unit)."""
    if " " not in text:
        return text, ""
    value, unit = text.rsplit(" ", 1)
    return value, unit


class OverviewPage(BasePage):
    title = "Mounted filesystems"

    def build_content(self) -> None:
        self.service = MountsService(self.settings)
        self.model = MountsModel()
        self._cards: dict[str, MountCard] = {}
        self._mounts_by_mountpoint: dict[str, MountInfo] = {}
        self._selected_mountpoint: str | None = None
        self._loaded = False

        self._build_header()
        self._build_kpis()
        self._build_controls()
        self._build_loading_label()
        self._build_groups_container()

        self.service.connect("mounts-changed", self._on_mounts_changed)
        self.service.start()
        self.registry = self.app.scan_registry
        self.registry.connect("entry-changed", self._on_scan_entry_changed)
        from lindrivespace.services.favorites import get_store

        self.favorites = get_store(self.app)
        self.favorites.connect("changed", lambda _s: self.refresh_scan_history())
        self.registry.connect("active-changed", lambda _r, _p: self._update_subtitle())

    # ---- construction -------------------------------------------------------

    def _build_header(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label=self.title)
        title.get_style_context().add_class("page-title")
        title.set_xalign(0.0)
        box.pack_start(title, False, False, 0)

        subtitle_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.header_spinner = Gtk.Spinner()
        self.header_spinner.set_size_request(14, 14)
        self.header_spinner.set_no_show_all(True)
        subtitle_row.pack_start(self.header_spinner, False, False, 0)
        self.subtitle_label = Gtk.Label(label="Reading mounts…")
        self.subtitle_label.get_style_context().add_class("page-subtitle")
        self.subtitle_label.set_xalign(0.0)
        subtitle_row.pack_start(self.subtitle_label, False, False, 0)
        box.pack_start(subtitle_row, False, False, 0)

        self.pack_start(box, False, False, 0)

    def _build_kpis(self) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_homogeneous(True)

        self.kpi_capacity = KpiTile(self.theme, "Total capacity", "0", unit="Bytes")
        self.kpi_used = KpiTile(self.theme, "Used", "0", unit="Bytes")
        self.kpi_free = KpiTile(self.theme, "Free", "0", unit="Bytes")
        self.kpi_scanned = KpiTile(self.theme, "Scanned", "0", unit="of 0", detail="no scans yet")

        for tile in (self.kpi_capacity, self.kpi_used, self.kpi_free, self.kpi_scanned):
            row.pack_start(tile, True, True, 0)
        self.pack_start(row, False, False, 0)

    def _build_controls(self) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.show_hidden_check = Gtk.CheckButton(label="Show hidden")
        self.show_hidden_check.set_active(self.service.show_hidden)
        self.show_hidden_check.connect("toggled", self._on_show_hidden_toggled)
        row.pack_start(self.show_hidden_check, False, False, 0)

        spacer = Gtk.Box()
        row.pack_start(spacer, True, True, 0)

        self.refresh_button = Gtk.Button(label="Refresh")
        self.refresh_button.connect("clicked", lambda _b: self.service.refresh())
        row.pack_start(self.refresh_button, False, False, 0)

        self.pack_start(row, False, False, 0)

    def _build_loading_label(self) -> None:
        self.loading_label = Gtk.Label(label="Reading mounts…")
        self.loading_label.get_style_context().add_class("dim")
        self.loading_label.set_xalign(0.0)
        self.pack_start(self.loading_label, False, False, 0)

    def _build_groups_container(self) -> None:
        self.groups_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.pack_start(self.groups_box, True, True, 0)

    # ---- lifecycle ------------------------------------------------------------

    def on_shown(self) -> None:
        last = self.service.last_refresh_monotonic
        if not self._loaded or last is None or (time.monotonic() - last) > _STALE_SECONDS:
            self.service.refresh()

    # ---- service callbacks ------------------------------------------------

    def _on_mounts_changed(self, _service: MountsService) -> None:
        self.model.set_snapshot(self.service.disks, self.service.mounts)
        if not self._loaded:
            self._loaded = True
            self.loading_label.set_visible(False)
        self._rebuild_groups()
        self._update_kpis()
        self._update_subtitle()

    # ---- disk group / card construction ------------------------------------

    def _rebuild_groups(self) -> None:
        for child in self.groups_box.get_children():
            self.groups_box.remove(child)
        self._cards = {}
        self._mounts_by_mountpoint = {}

        show_hidden = self.show_hidden_check.get_active()
        roles = self.mount_roles()
        rank = {"primary": 0, "secondary": 1}

        def mount_rank(m: MountInfo) -> tuple[int, str]:
            return (rank.get(roles.get(m.mountpoint, ""), 2), m.mountpoint)

        groups: list[tuple[int, DiskInfo, list[MountInfo]]] = []
        hidden_mounts: list[MountInfo] = []
        for disk in self.model.disks:
            physical = self.model.is_visible_disk(disk, show_hidden=False)
            if not physical:
                if show_hidden:
                    hidden_mounts.extend(disk.mounts)
                continue
            mounts = [m for m in disk.mounts if self.model.is_visible(m, show_hidden=False)]
            if show_hidden:
                hidden_mounts.extend(
                    m for m in disk.mounts if not self.model.is_visible(m, show_hidden=False)
                )
            if not mounts:
                continue
            mounts.sort(key=mount_rank)
            groups.append((min(mount_rank(m)[0] for m in mounts), disk, mounts))
        # Disks holding the primary / secondary mountpoint come first; stable otherwise.
        groups.sort(key=lambda g: g[0])
        for _r, disk, mounts in groups:
            self.groups_box.pack_start(self._build_disk_group(disk, mounts), False, False, 0)
        if hidden_mounts:
            hidden_mounts.sort(key=lambda m: m.mountpoint)
            self.groups_box.pack_start(self._build_hidden_group(hidden_mounts), False, False, 0)
        self.groups_box.show_all()

        if self._selected_mountpoint and self._selected_mountpoint in self._cards:
            self._cards[self._selected_mountpoint].set_selected(True)

    def _build_disk_group(self, disk: DiskInfo, mounts: list[MountInfo]) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name_label = Gtk.Label(label=disk.kname or "other")
        name_label.get_style_context().add_class("section-title")
        name_label.set_xalign(0.0)
        header.pack_start(name_label, False, False, 0)

        kind_word = "rotational" if disk.rotational else disk.kind
        detail_parts = [p for p in (disk.model, disk.transport.upper() or None, kind_word) if p]
        detail_label = Gtk.Label(label=" · ".join(detail_parts))
        detail_ctx = detail_label.get_style_context()
        detail_ctx.add_class("mono")
        detail_ctx.add_class("muted")
        detail_label.set_xalign(0.0)
        header.pack_start(detail_label, False, False, 0)

        box.pack_start(header, False, False, 0)

        box.pack_start(self._flow(mounts, compact=False), False, False, 0)
        return box

    def _flow(self, mounts: list[MountInfo], *, compact: bool) -> Gtk.FlowBox:
        """Cards in a wrapping row; every card has the same fixed width so groups line up."""
        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_homogeneous(True)
        flow.set_halign(Gtk.Align.START)
        flow.set_min_children_per_line(1)
        flow.set_max_children_per_line(6 if compact else 3)
        flow.set_column_spacing(12)
        flow.set_row_spacing(12)
        width = _DIMS.CARD_WIDTH_COMPACT if compact else _DIMS.CARD_WIDTH
        for mount in mounts:
            card = self._build_card(mount)
            card.set_size_request(width, -1)
            card.set_hexpand(False)
            child = Gtk.FlowBoxChild()
            child.set_halign(Gtk.Align.START)
            child.add(card)
            flow.insert(child, -1)
        return flow

    def _build_hidden_group(self, mounts: list[MountInfo]) -> Gtk.Box:
        """All hidden / virtual mounts (snap loops, tmpfs, …) in one compact group."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name_label = Gtk.Label(label="hidden & virtual")
        name_label.get_style_context().add_class("section-title")
        name_label.set_xalign(0.0)
        header.pack_start(name_label, False, False, 0)
        detail_label = Gtk.Label(
            label=f"{len(mounts)} mounts · snap loops, tmpfs, pseudo filesystems"
        )
        detail_label.get_style_context().add_class("mono")
        detail_label.get_style_context().add_class("muted")
        header.pack_start(detail_label, False, False, 0)
        box.pack_start(header, False, False, 0)
        box.pack_start(self._flow(mounts, compact=True), False, False, 0)
        return box

    def _card_data(self, mount: MountInfo) -> MountCardData:
        """Card data plus the registry's live scan state for that mountpoint."""
        data = self.model.card_data(mount, self.window.scan_history)
        data = replace(data, favorite=self.favorites.is_favorite(mount.mountpoint))
        entry = self.registry.get(mount.mountpoint)
        if entry is None:
            return data
        if entry.state == "scanning":
            if entry.expected_bytes:
                pct = min(99, int(entry.alloc * 100 / entry.expected_bytes))
                detail = f"{pct} % · {self.app.format_bytes(entry.alloc)}"
            else:
                detail = self.app.format_bytes(entry.alloc) if entry.alloc else ""
        elif entry.state == "done":
            detail = self.app.format_bytes(entry.alloc) if entry.alloc else ""
        else:
            detail = ""
        return replace(
            data,
            scanned_at=entry.finished_text or data.scanned_at,
            scan_state=entry.state,
            scan_detail=detail,
            favorite=self.favorites.is_favorite(mount.mountpoint),
        )

    def _on_scan_entry_changed(self, _registry: object, path: str) -> None:
        card = self._cards.get(path)
        mount = self._mounts_by_mountpoint.get(path)
        if card is not None and mount is not None:
            card.update(self._card_data(mount))
        self._update_subtitle()
        self._update_kpis()

    def _build_card(self, mount: MountInfo) -> MountCard:
        data = self._card_data(mount)
        card = MountCard(self.theme, data)
        # MountCard's usage line wraps (Gtk.Label.set_line_wrap) but a
        # wrapping label's *natural* width request is still its full
        # unwrapped text -- GTK only shrinks it once allocated less than
        # that, which FlowBox's own "how many columns fit" measurement never
        # does. Capping the char width here (a public MountCard attribute,
        # see .claude/memory/changes/2026-09-14-wp5-widgets.md) keeps a
        # card's natural width close to CARD_WIDTH so three fit per row at
        # the default window width, matching the Direction B mockup, instead
        # of FlowBox dropping to two wide columns. Not a mount_card.py edit.
        card.usage_label.set_max_width_chars(20)
        card.set_role(self.mount_roles().get(mount.mountpoint))
        card.connect("scan-requested", self._on_card_scan_requested)
        card.connect(
            "favorite-toggled",
            lambda _c, mp, active: self.favorites.add(mp) if active else self.favorites.remove(mp),
        )
        card.connect("selected", self._on_card_selected)
        self._cards[mount.mountpoint] = card
        self._mounts_by_mountpoint[mount.mountpoint] = mount
        return card

    # ---- mount roles (Settings › Mounts: primary / secondary) ---------------

    def mount_roles(self) -> dict[str, str]:
        """mountpoint -> "primary" | "secondary" from settings (empty values ignored)."""
        roles: dict[str, str] = {}
        for role in ("primary", "secondary"):
            mp = str(self.settings.get(f"mounts.{role}", "") or "")
            if mp and mp not in roles:
                roles[mp] = role
        return roles

    def known_mountpoints(self) -> list[str]:
        """Mountpoints on physical disks (no loops, pseudo-fs or bind mounts), sorted.

        Used by the Settings selectors and by the startup auto-scan queue.
        """
        out: list[str] = []
        for disk in self.model.disks:
            if not self.model.is_visible_disk(disk, show_hidden=False):
                continue
            for m in disk.mounts:
                if not self.model.is_visible(m, show_hidden=False) or m.is_bind:
                    continue
                out.append(m.mountpoint)
        return sorted(set(out))

    def refresh_roles(self) -> None:
        """Re-badge and re-order cards after the Settings page changed the roles."""
        if self._cards:
            self._rebuild_groups()

    # ---- signal handlers ----------------------------------------------------

    def _on_card_scan_requested(self, _card: MountCard, mountpoint: str) -> None:
        self.window.request_scan(mountpoint)

    def _on_card_selected(self, _card: MountCard, mountpoint: str) -> None:
        self._selected_mountpoint = mountpoint
        for mp, card in self._cards.items():
            card.set_selected(mp == mountpoint)

    def _on_show_hidden_toggled(self, checkbox: Gtk.CheckButton) -> None:
        active = checkbox.get_active()
        self.settings.set("mounts.show_hidden", active)
        try:
            self.settings.save()
        except OSError as exc:
            print(f"could not save settings: {exc}")
        # Display-only change: the model already has every mount (with its
        # ``hidden`` flag), so rebuild immediately rather than wait on a
        # round trip through the worker thread.
        self._rebuild_groups()
        self._update_kpis()
        self._update_subtitle()
        self.service.show_hidden = active

    # ---- KPI / subtitle rendering -------------------------------------------

    def _update_kpis(self) -> None:
        capacity, used, free = self.model.totals()
        mount_count = self.model.counted_mount_count()
        percent_used = (used / capacity * 100.0) if capacity > 0 else 0.0

        cap_value, cap_unit = _split_value_unit(format_bytes(capacity))
        self.kpi_capacity.set_value(cap_value, unit=cap_unit, detail=f"across {mount_count} mounts")

        used_value, used_unit = _split_value_unit(format_bytes(used))
        self.kpi_used.set_value(used_value, unit=used_unit, detail=f"{percent_used:.0f} %")

        free_value, free_unit = _split_value_unit(format_bytes(free))
        urgent = self.model.most_urgent()
        free_detail = (
            f"{urgent.mountpoint} at {urgent.percent_used:.0f} % — needs attention"
            if urgent is not None
            else "all mounts below 85 %"
        )
        self.kpi_free.set_value(free_value, unit=free_unit, detail=free_detail)

        scan_history = self.window.scan_history
        scanned = self.model.scanned_count(scan_history)
        if scan_history:
            last_path, last_time = max(scan_history.items(), key=lambda kv: kv[1])
            scanned_detail = f"last: {last_path} · {last_time}"
        else:
            scanned_detail = "no scans yet"
        self.kpi_scanned.set_value(str(scanned), unit=f"of {mount_count}", detail=scanned_detail)

    def _update_subtitle(self) -> None:
        mount_count = self.model.counted_mount_count()
        disk_count = self.model.counted_disk_count()
        hidden_count = self.model.hidden_count()
        hidden_text = (
            f"{hidden_count} hidden (snap loops, tmpfs)" if hidden_count else "no hidden mounts"
        )
        monitor_text = (
            "udev monitor live" if self.service.monitor_available else "udev monitor unavailable"
        )
        base = f"{mount_count} mounts on {disk_count} disks · {hidden_text} · {monitor_text}"
        # The scan banner above the page carries the live scan; keep the subtitle factual.
        self.subtitle_label.set_text(base)
        self.header_spinner.stop()
        self.header_spinner.hide()

    # ---- public API (called by MainWindow.record_scan) ----------------------

    def refresh_scan_history(self) -> None:
        """Refresh every card's scanned-at label and the Scanned KPI."""
        for mountpoint, mount in self._mounts_by_mountpoint.items():
            card = self._cards.get(mountpoint)
            if card is not None:
                card.update(self._card_data(mount))
        self._update_kpis()
