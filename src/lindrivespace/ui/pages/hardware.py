"""Hardware page (WP16) — what the kernel knows about this machine.

Six-ish ``PrefGroup`` cards (System, Motherboard & firmware, Processor &
memory, Storage controllers, Supported drive types, Disks, I/O activity,
Filesystems supported, Notes) built from a single :class:`~lindrivespace.core
.hardware.HardwareReport`. Collection (``core.hardware.collect``) runs in a
background thread on first show and hands the report back through
``GLib.idle_add`` — the same one-shot worker-thread shape
``services/mounts_service.py`` uses for the Overview page, just kept local to
this page rather than promoted to a service (WP16 owns only this file and
``core/hardware.py``).

The I/O activity table samples ``/proc/diskstats`` every two seconds while the
page is visible (``GLib.timeout_add_seconds``, started in ``on_shown``,
stopped in ``on_hidden``) and turns two samples into per-device throughput via
``core.hardware.io_rates``.
"""

from __future__ import annotations

import threading
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from lindrivespace.core import hardware as hw  # noqa: E402
from lindrivespace.core.units import format_bytes  # noqa: E402
from lindrivespace.ui.pages.base import BasePage  # noqa: E402
from lindrivespace.ui.widgets.settings_rows import PrefGroup, PrefRow  # noqa: E402

_IO_REFRESH_SECONDS = 2
_VALUE_MAX_CHARS = 46

# Disks table: (title, fixed width px, xalign)
_DISK_COLUMNS: tuple[tuple[str, int, float], ...] = (
    ("Device", 132, 0.0),
    ("Model", 220, 0.0),
    ("Size", 90, 1.0),
    ("Type", 104, 0.0),
    ("Link", 136, 0.0),
    ("Scheduler", 110, 0.0),
    ("TRIM", 64, 0.5),
    ("Parts", 70, 1.0),
)
_DISK_EXPAND_COLUMN = "Model"
# Columns whose text should ellipsize instead of clipping abruptly when a
# value (a long device path, model string, or link description) overflows.
_DISK_ELLIPSIZE_COLUMNS = frozenset({"Device", "Model", "Link"})
# I/O activity table
_IO_COLUMNS: tuple[tuple[str, int, float], ...] = (
    ("Device", 132, 0.0),
    ("Read MB/s", 110, 1.0),
    ("Write MB/s", 110, 1.0),
    ("IOPS (r/w)", 140, 1.0),
    ("Util %", 90, 1.0),
)
_IO_EXPAND_COLUMN = "Device"


def _disk_type_label(disk: hw.DiskHardware) -> str:
    transport = (disk.transport or "").lower()
    if transport == "nvme":
        return "NVMe SSD"
    if transport == "usb":
        return "USB"
    if transport == "mmc":
        return "SD/MMC"
    if transport == "virtio":
        return "Virtio"
    if transport in ("sata", "ata", "scsi", ""):
        return "HDD" if disk.rotational else "SATA SSD"
    return transport.upper()


# core.hardware.chassis_type_name() returns lowercase, hyphenated slugs (see
# _CHASSIS_TYPES there); title-casing those naively turns "pc" into "Pc", so
# spell out the acronym-bearing ones by hand.
_CHASSIS_TYPE_LABELS: dict[str, str] = {
    "mini-pc": "Mini PC",
    "stick-pc": "Stick PC",
    "embedded-pc": "Embedded PC",
    "iot-gateway": "IoT Gateway",
    "all-in-one": "All-in-One",
}


def _format_chassis_type(chassis_type: str) -> str:
    return _CHASSIS_TYPE_LABELS.get(chassis_type, chassis_type.replace("-", " ").title())


def _format_uptime(seconds: float) -> str:
    total = int(seconds)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def _copyable(group: PrefGroup) -> PrefGroup:
    group.enable_copy()
    return group


class HardwarePage(BasePage):
    title = "Hardware"

    def build_content(self) -> None:
        self._report: hw.HardwareReport | None = None
        self._collecting = False
        self._io_timer_id: int | None = None
        self._prev_io: dict[str, hw.IoStats] | None = None
        self._prev_io_time: float | None = None
        self.io_store: Gtk.ListStore | None = None
        self.disks_store: Gtk.ListStore | None = None
        self.io_tree: Gtk.TreeView | None = None
        self.disks_tree: Gtk.TreeView | None = None

        self.add_title(
            self.title,
            "What the kernel knows about this machine — no root required.",
        )
        self._build_toolbar()
        self._build_loading_row()

        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.pack_start(self.content_box, True, True, 0)

    # ---- chrome -----------------------------------------------------------------

    def _build_toolbar(self) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.pack_start(Gtk.Box(), True, True, 0)  # spacer

        self.refresh_button = Gtk.Button(label="Refresh")
        self.refresh_button.get_accessible().set_name("Refresh hardware report")
        self.refresh_button.connect("clicked", lambda _b: self._start_collection())
        row.pack_start(self.refresh_button, False, False, 0)

        self.copy_button = Gtk.Button(label="Copy report")
        self.copy_button.get_accessible().set_name("Copy hardware report")
        self.copy_button.set_sensitive(False)
        self.copy_button.connect("clicked", self._on_copy_clicked)
        row.pack_start(self.copy_button, False, False, 0)

        self.pack_start(row, False, False, 0)

    def _build_loading_row(self) -> None:
        self.loading_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.loading_spinner = Gtk.Spinner()
        self.loading_spinner.set_size_request(16, 16)
        self.loading_box.pack_start(self.loading_spinner, False, False, 0)
        loading_label = Gtk.Label(label="Reading hardware…")
        loading_label.set_xalign(0.0)
        loading_label.get_style_context().add_class("dim")
        self.loading_box.pack_start(loading_label, False, False, 0)
        self.loading_box.set_no_show_all(True)
        self.loading_box.hide()
        self.pack_start(self.loading_box, False, False, 0)

    # ---- lifecycle ----------------------------------------------------------------

    def on_shown(self) -> None:
        if self._report is None and not self._collecting:
            self._start_collection()
        self._start_io_timer()

    def on_hidden(self) -> None:
        self._stop_io_timer()

    # ---- background collection -----------------------------------------------------

    def _start_collection(self) -> None:
        if self._collecting:
            return
        self._collecting = True
        self.refresh_button.set_sensitive(False)
        # show_all() is a no-op on a no-show-all widget: lift it for the call.
        self.loading_box.set_no_show_all(False)
        self.loading_box.show_all()
        self.loading_box.set_no_show_all(True)
        self.loading_spinner.start()

        def worker() -> None:
            try:
                report = hw.collect()
            except Exception:  # noqa: BLE001 - never crash the worker thread
                report = hw.HardwareReport(
                    system=hw.SystemInfo("", "Unknown", "", "", 0.0, "unknown", "none"),
                    board=hw.BoardInfo(None, None, None, None, None, None, None, None, None),
                    cpu=hw.CpuInfo("Unknown", "Unknown", 0, 0, 0, None, ()),
                    memory=hw.MemoryInfo(0, 0, 0, 0),
                    controllers=(),
                    disks=(),
                    filesystems=(),
                    pseudo_filesystems=(),
                    drive_types=(),
                    notes=("Hardware collection failed unexpectedly.",),
                )
            GLib.idle_add(self._on_report_ready, report)

        threading.Thread(target=worker, daemon=True).start()

    def _on_report_ready(self, report: hw.HardwareReport) -> bool:
        self._report = report
        self._collecting = False
        self.loading_spinner.stop()
        self.loading_box.hide()
        self.refresh_button.set_sensitive(True)
        self.copy_button.set_sensitive(True)
        self._rebuild_content(report)
        # Prime the I/O baseline so the first tick after a (re)load shows a
        # rate rather than a jump from a stale previous sample.
        self._prev_io = hw.sample_io()
        self._prev_io_time = time.monotonic()
        return GLib.SOURCE_REMOVE

    def _on_copy_clicked(self, _button: Gtk.Button) -> None:
        if self._report is None:
            return
        text = hw.to_text(self._report)
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)

    # ---- content construction ------------------------------------------------------

    def _rebuild_content(self, report: hw.HardwareReport) -> None:
        for child in self.content_box.get_children():
            self.content_box.remove(child)

        # Disks and live I/O first (user request): the storage facts matter most here.
        self.content_box.pack_start(self._build_disks_group(report.disks), False, False, 0)
        self.content_box.pack_start(self._build_io_group(report.disks), False, False, 0)
        self.content_box.pack_start(self._build_system_group(report.system), False, False, 0)
        self.content_box.pack_start(self._build_board_group(report.board), False, False, 0)
        self.content_box.pack_start(
            self._build_cpu_memory_group(report.cpu, report.memory), False, False, 0
        )
        self.content_box.pack_start(
            self._build_controllers_group(report.controllers), False, False, 0
        )
        self.content_box.pack_start(
            self._build_drive_types_group(report.drive_types), False, False, 0
        )
        self.content_box.pack_start(
            self._build_filesystems_group(report.filesystems, report.pseudo_filesystems),
            False,
            False,
            0,
        )
        self.content_box.pack_start(self._build_notes_group(report.notes), False, False, 0)
        self.content_box.show_all()

    def _value_label(self, text: str, mono: bool = False) -> Gtk.Label:
        label = Gtk.Label(label=text or "—")
        label.set_xalign(1.0)
        label.set_justify(Gtk.Justification.RIGHT)
        label.set_line_wrap(True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_max_width_chars(_VALUE_MAX_CHARS)
        if mono:
            label.get_style_context().add_class("mono")
        return label

    def _info_label(self, text: str) -> Gtk.Label:
        label = Gtk.Label(label=text)
        label.set_xalign(0.0)
        label.set_line_wrap(True)
        label.get_style_context().add_class("dim")
        return label

    # ---- groups -----------------------------------------------------------------

    def _build_system_group(self, system: hw.SystemInfo) -> PrefGroup:
        group = _copyable(PrefGroup("System"))
        group.add_row(PrefRow("Hostname", self._value_label(system.hostname or "—")))
        group.add_row(PrefRow("Distribution", self._value_label(system.distro)))
        group.add_row(PrefRow("Kernel", self._value_label(system.kernel, mono=True)))
        group.add_row(PrefRow("Architecture", self._value_label(system.arch)))
        group.add_row(PrefRow("Type", self._value_label(_format_chassis_type(system.chassis_type))))
        group.add_row(PrefRow("Virtualization", self._value_label(system.virtualization)))
        group.add_row(PrefRow("Uptime", self._value_label(_format_uptime(system.uptime_seconds))))
        return group

    def _build_board_group(self, board: hw.BoardInfo) -> PrefGroup:
        group = _copyable(PrefGroup("Motherboard & firmware"))
        system_line = " ".join(
            p for p in (board.sys_vendor, board.product_name, board.product_version) if p
        )
        board_line = " ".join(
            p for p in (board.board_vendor, board.board_name, board.board_version) if p
        )
        bios_line = " ".join(p for p in (board.bios_vendor, board.bios_version) if p)
        if board.bios_date:
            bios_line = f"{bios_line} ({board.bios_date})" if bios_line else board.bios_date
        group.add_row(PrefRow("System", self._value_label(system_line or "Not available")))
        group.add_row(PrefRow("Board", self._value_label(board_line or "Not available")))
        group.add_row(PrefRow("BIOS/UEFI", self._value_label(bios_line or "Not available")))
        return group

    def _build_cpu_memory_group(self, cpu: hw.CpuInfo, memory: hw.MemoryInfo) -> PrefGroup:
        group = _copyable(PrefGroup("Processor & memory"))
        group.add_row(PrefRow("Model", self._value_label(cpu.model)))
        group.add_row(
            PrefRow(
                "Cores / threads",
                self._value_label(
                    f"{cpu.sockets} socket(s) · {cpu.cores} cores · {cpu.threads} threads"
                ),
            )
        )
        if cpu.max_mhz:
            group.add_row(PrefRow("Max clock", self._value_label(f"{cpu.max_mhz:.0f} MHz")))
        if cpu.flags_of_interest:
            group.add_row(
                PrefRow(
                    "Notable flags",
                    self._value_label(", ".join(cpu.flags_of_interest), mono=True),
                )
            )
        memory_text = (
            f"{format_bytes(memory.total)} total · {format_bytes(memory.available)} available"
        )
        group.add_row(PrefRow("Memory", self._value_label(memory_text)))
        swap_text = (
            f"{format_bytes(memory.swap_total)} total · {format_bytes(memory.swap_free)} free"
            if memory.swap_total
            else "No swap configured"
        )
        group.add_row(PrefRow("Swap", self._value_label(swap_text)))
        return group

    def _build_controllers_group(self, controllers: tuple[hw.StorageController, ...]) -> PrefGroup:
        group = _copyable(PrefGroup("Storage controllers"))
        if not controllers:
            group.add_row(self._info_label("No PCI storage controllers detected."))
            return group
        for controller in controllers:
            group.add_row(
                PrefRow(
                    controller.kind, self._value_label(f"{controller.vendor} {controller.device}")
                )
            )
        return group

    def _build_drive_types_group(self, drive_types: tuple[str, ...]) -> PrefGroup:
        group = _copyable(PrefGroup("Supported drive types"))
        if not drive_types:
            group.add_row(self._info_label("None detected."))
            return group
        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_min_children_per_line(1)
        flow.set_max_children_per_line(8)
        flow.set_row_spacing(6)
        flow.set_column_spacing(6)
        flow.set_homogeneous(False)
        flow.set_valign(Gtk.Align.START)
        for label_text in drive_types:
            chip = Gtk.Label(label=label_text)
            chip.get_style_context().add_class("badge")
            flow.insert(chip, -1)
        group.add_row(flow)
        return group

    def _styled_table(
        self,
        store: Gtk.ListStore,
        columns: tuple[tuple[str, int, float], ...],
        *,
        mono: frozenset[str] = frozenset(),
        ellipsize: frozenset[str] = frozenset(),
        expand: str = "",
    ) -> tuple[Gtk.TreeView, Gtk.ScrolledWindow]:
        """A table that looks like the Overview's mount list: bordered frame, bold muted
        headers, grid lines, 6 px cell padding, mono for device/number columns, sortable."""
        tree = Gtk.TreeView(model=store)
        ctx = tree.get_style_context()
        ctx.add_class("mount-list")
        ctx.add_class("grid-table")
        tree.set_grid_lines(Gtk.TreeViewGridLines.BOTH)
        tree.set_fixed_height_mode(True)
        tree.set_headers_visible(True)
        tree.set_headers_clickable(True)
        tree.set_hexpand(True)
        mono_family = self.theme.font_mono.split(",")[0]
        for index, (title, width, xalign) in enumerate(columns):
            column = Gtk.TreeViewColumn(title)
            column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            column.set_fixed_width(width)
            column.set_resizable(True)
            column.set_sort_column_id(index)
            column.set_alignment(xalign)
            renderer = Gtk.CellRendererText()
            renderer.set_property("xalign", xalign)
            renderer.set_property("xpad", 6)
            if title in mono:
                renderer.set_property("family", mono_family)
            if title in ellipsize:
                renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
            column.pack_start(renderer, True)
            column.add_attribute(renderer, "text", index)
            column.set_expand(title == expand)
            tree.append_column(column)
        frame = Gtk.ScrolledWindow()
        frame.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        frame.set_shadow_type(Gtk.ShadowType.IN)
        frame.get_style_context().add_class("mount-list-frame")
        frame.add(tree)
        return tree, frame

    def _build_disks_group(self, disks: tuple[hw.DiskHardware, ...]) -> PrefGroup:
        group = _copyable(PrefGroup("Disks"))
        if not disks:
            group.add_row(self._info_label("No disks detected."))
            return group

        store = Gtk.ListStore(str, str, str, str, str, str, str, str)
        self.disks_store = store
        for disk in disks:
            store.append(
                [
                    disk.path,
                    disk.model or "Unknown model",
                    format_bytes(disk.size),
                    _disk_type_label(disk),
                    disk.link or "—",
                    disk.scheduler or "—",
                    "Yes" if disk.discard_supported else "No",
                    str(len(disk.partitions)),
                ]
            )
        self.disks_tree, frame = self._styled_table(
            store,
            _DISK_COLUMNS,
            mono=frozenset({"Device", "Size", "Parts"}),
            ellipsize=_DISK_ELLIPSIZE_COLUMNS,
            expand=_DISK_EXPAND_COLUMN,
        )
        group.add_row(frame)

        for disk in disks:
            if not disk.partitions:
                continue
            parts_text = ", ".join(
                f"{name} ({format_bytes(size)}{f', {fstype}' if fstype else ''})"
                for name, size, fstype, _mountpoint in disk.partitions
            )
            part_label = Gtk.Label(label=f"{disk.path} partitions: {parts_text}")
            part_label.set_xalign(0.0)
            part_label.set_line_wrap(True)
            ctx = part_label.get_style_context()
            ctx.add_class("mono")
            ctx.add_class("dim")
            group.add_row(part_label)
        return group

    def _build_io_group(self, disks: tuple[hw.DiskHardware, ...]) -> PrefGroup:
        group = _copyable(PrefGroup("I/O activity"))
        if not disks:
            group.add_row(self._info_label("No disks to monitor."))
            self.io_store = None
            return group

        store = Gtk.ListStore(str, str, str, str, str)
        for disk in disks:
            store.append([disk.kname, "—", "—", "—", "—"])
        self.io_tree, frame = self._styled_table(
            store,
            _IO_COLUMNS,
            mono=frozenset({"Device", "Read MB/s", "Write MB/s", "IOPS (r/w)", "Util %"}),
            expand=_IO_EXPAND_COLUMN,
        )
        group.add_row(frame)
        detail = self._info_label(
            f"Refreshes every {_IO_REFRESH_SECONDS} s while this page is visible."
        )
        group.add_row(detail)

        self.io_store = store
        return group

    def _build_filesystems_group(
        self, filesystems: tuple[str, ...], pseudo: tuple[str, ...]
    ) -> PrefGroup:
        group = _copyable(PrefGroup("Filesystems supported"))
        fs_label = Gtk.Label(label=", ".join(filesystems) if filesystems else "None detected.")
        fs_label.set_xalign(0.0)
        fs_label.set_line_wrap(True)
        group.add_row(fs_label)
        if pseudo:
            pseudo_label = Gtk.Label(label="Pseudo / virtual: " + ", ".join(pseudo))
            pseudo_label.set_xalign(0.0)
            pseudo_label.set_line_wrap(True)
            pseudo_label.get_style_context().add_class("dim")
            group.add_row(pseudo_label)
        return group

    def _build_notes_group(self, notes: tuple[str, ...]) -> PrefGroup:
        group = _copyable(PrefGroup("Notes"))
        if not notes:
            group.add_row(self._info_label("No notes."))
            return group
        for note in notes:
            group.add_row(self._info_label(note))
        return group

    # ---- I/O activity timer -------------------------------------------------------

    def _start_io_timer(self) -> None:
        if self._io_timer_id is not None:
            return
        self._io_timer_id = GLib.timeout_add_seconds(_IO_REFRESH_SECONDS, self._on_io_tick)

    def _stop_io_timer(self) -> None:
        if self._io_timer_id is not None:
            GLib.source_remove(self._io_timer_id)
            self._io_timer_id = None

    def _on_io_tick(self) -> bool:
        if self._report is None or self.io_store is None:
            return GLib.SOURCE_CONTINUE
        now = time.monotonic()
        curr = hw.sample_io()
        if self._prev_io is not None and self._prev_io_time is not None:
            interval = now - self._prev_io_time
            rates = {rate.kname: rate for rate in hw.io_rates(self._prev_io, curr, interval)}
            self._update_io_store(rates)
        self._prev_io = curr
        self._prev_io_time = now
        return GLib.SOURCE_CONTINUE

    def _update_io_store(self, rates: dict[str, hw.IoRate]) -> None:
        store = self.io_store
        if store is None:
            return
        it = store.get_iter_first()
        while it is not None:
            kname = store.get_value(it, 0)
            rate = rates.get(kname)
            if rate is not None:
                store.set_value(it, 1, f"{rate.read_bytes_per_s / 1_000_000:.2f}")
                store.set_value(it, 2, f"{rate.write_bytes_per_s / 1_000_000:.2f}")
                store.set_value(it, 3, f"{rate.iops_r:.0f} / {rate.iops_w:.0f}")
                store.set_value(it, 4, f"{rate.utilization_pct:.0f}")
            it = store.iter_next(it)
