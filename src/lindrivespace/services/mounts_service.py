"""MountsService: background mount/disk discovery + hotplug watch for the Overview page.

Mirrors the shape of ``services/scan_controller.py`` (a ``GObject.GObject`` that
does its I/O off the main thread and hands results back with ``GLib.idle_add``),
but the producer here is one-shot (``core.mounts.list_mounts`` + ``group_by_disk``)
rather than a streaming queue: every refresh is a full re-scan of ``lsblk`` +
``/proc/self/mountinfo`` + ``statvfs``, cheap enough to just re-run.

The default data source always asks ``core.mounts.list_mounts`` for *every*
mount (``include_hidden=True``) so the snapshot's ``MountInfo.hidden`` flags are
always accurate -- ``MountsModel.totals()``/``hidden_count()`` need that even
when the "Show hidden" checkbox is off. ``show_hidden`` therefore only changes
*display* (which mounts the Overview page turns into cards), not what this
service fetches; the setter still triggers a refresh so a future change to
``mounts.hidden_fstypes`` (edited elsewhere) is picked up promptly too.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib, GObject  # noqa: E402

from lindrivespace.config.settings import Settings  # noqa: E402
from lindrivespace.core.mounts import (  # noqa: E402
    DiskInfo,
    MountInfo,
    MountMonitor,
    group_by_disk,
    list_mounts,
)

Lister = Callable[[], "tuple[list[DiskInfo], list[MountInfo]]"]

_USAGE_REFRESH_SECONDS = 30
_HOTPLUG_DEBOUNCE_MS = 300


class MountsService(GObject.GObject):
    """Owns the current (disks, mounts) snapshot; refreshes off the main thread."""

    __gtype_name__ = "LdsMountsService"
    __gsignals__ = {
        "mounts-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "refreshing": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
    }

    def __init__(self, settings: Settings, lister: Lister | None = None) -> None:
        super().__init__()
        self._settings = settings
        # Public (not name-mangled) so tests/pages can swap it out, e.g.
        # ``page.service.lister = fake_lister``.
        self.lister: Lister = lister or self._default_lister

        self.disks: list[DiskInfo] = []
        self.mounts: list[MountInfo] = []
        self.last_refresh_monotonic: float | None = None

        self._refresh_lock = threading.Lock()
        self._refresh_in_progress = False
        self._refresh_pending = False

        self._monitor: MountMonitor | None = None
        self._io_watch_id: int | None = None
        self._debounce_id: int | None = None
        self._periodic_id: int | None = None

    # ---- settings-backed properties ---------------------------------------

    @property
    def show_hidden(self) -> bool:
        return bool(self._settings.get("mounts.show_hidden", False))

    @show_hidden.setter
    def show_hidden(self, value: bool) -> None:
        self._settings.set("mounts.show_hidden", bool(value))
        self.refresh()

    @property
    def monitor_available(self) -> bool:
        return self._monitor is not None and self._monitor.available

    # ---- default data source ----------------------------------------------

    def _default_lister(self) -> tuple[list[DiskInfo], list[MountInfo]]:
        hidden_fstypes = self._settings.get("mounts.hidden_fstypes", [])
        # Read for parity with the "reads hidden_fstypes/show_hidden from
        # settings each refresh" contract, even though the default lister
        # always fetches every mount (see module docstring).
        _ = self.show_hidden
        mounts = list_mounts(hidden_fstypes=hidden_fstypes, include_hidden=True)
        disks = group_by_disk(mounts)
        return disks, mounts

    # ---- refresh (coalesced) -----------------------------------------------

    def refresh(self) -> None:
        """Request a refresh. A refresh requested while one runs is coalesced
        into exactly one more run once the in-flight one completes."""
        with self._refresh_lock:
            if self._refresh_in_progress:
                self._refresh_pending = True
                return
            self._refresh_in_progress = True
        self.emit("refreshing", True)
        threading.Thread(target=self._run_refresh, daemon=True).start()

    def _run_refresh(self) -> None:
        try:
            disks, mounts = self.lister()
        except Exception:  # noqa: BLE001 - never crash the worker thread
            disks, mounts = [], []
        GLib.idle_add(self._apply_result, disks, mounts)

    def _apply_result(self, disks: list[DiskInfo], mounts: list[MountInfo]) -> bool:
        self.disks = disks
        self.mounts = mounts
        self.last_refresh_monotonic = time.monotonic()
        self.emit("mounts-changed")
        with self._refresh_lock:
            self._refresh_in_progress = False
            pending = self._refresh_pending
            self._refresh_pending = False
        self.emit("refreshing", False)
        if pending:
            self.refresh()
        return False  # one-shot GLib.idle_add source

    # ---- hotplug + periodic lifecycle --------------------------------------

    def start(self) -> None:
        """Start the udev hotplug watch (if available) and periodic refresh, and
        kick off the first refresh."""
        self._monitor = MountMonitor()
        self._monitor.start()
        if self._monitor.available:
            self._io_watch_id = GLib.io_add_watch(
                self._monitor.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN, self._on_udev_event
            )
        self._periodic_id = GLib.timeout_add_seconds(_USAGE_REFRESH_SECONDS, self._on_periodic)
        self.refresh()

    def stop(self) -> None:
        """Remove every GLib source and stop the udev monitor."""
        if self._io_watch_id is not None:
            GLib.source_remove(self._io_watch_id)
            self._io_watch_id = None
        if self._debounce_id is not None:
            GLib.source_remove(self._debounce_id)
            self._debounce_id = None
        if self._periodic_id is not None:
            GLib.source_remove(self._periodic_id)
            self._periodic_id = None
        if self._monitor is not None:
            self._monitor.stop()
            self._monitor = None

    def _on_udev_event(self, _fd: int, _condition: int) -> bool:
        if self._monitor is not None:
            self._monitor.poll()
        if self._debounce_id is None:
            self._debounce_id = GLib.timeout_add(_HOTPLUG_DEBOUNCE_MS, self._on_debounced_refresh)
        return True  # keep watching the fd

    def _on_debounced_refresh(self) -> bool:
        self._debounce_id = None
        self.refresh()
        return False  # one-shot

    def _on_periodic(self) -> bool:
        self.refresh()
        return True  # keep the periodic timer running
