"""ScanRegistry — one scan (model + controller) per root path, run one at a time.

Why: the app scans every mount shortly after launch ("all sizes populate"),
and the user can switch the Explorer between mounts without losing results.
Each root path keeps its own :class:`ScanTreeModel`; scans run sequentially
through a queue so only one scanner thread is alive at a time.

Signals:
* ``entry-changed(path)`` — state, progress or totals of that entry changed.
* ``active-changed(path)`` — a scan started ("" when the queue went idle).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GObject  # noqa: E402

from lindrivespace import logsetup  # noqa: E402
from lindrivespace.core.options import ScanOptions  # noqa: E402
from lindrivespace.models.tree_model import ScanTreeModel  # noqa: E402
from lindrivespace.services.scan_controller import ScanController  # noqa: E402

log = logsetup.get_logger("registry")

STATE_IDLE = "idle"
STATE_QUEUED = "queued"
STATE_SCANNING = "scanning"
STATE_DONE = "done"
STATE_CANCELLED = "cancelled"


@dataclass
class ScanEntry:
    path: str
    model: ScanTreeModel
    controller: ScanController
    state: str = STATE_IDLE
    entries: int = 0
    alloc: int = 0
    current_path: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    finished_text: str = ""  # "YYYY-MM-DD HH:MM" once done
    errors: int = 0
    handlers: list[int] = field(default_factory=list)

    @property
    def running(self) -> bool:
        return self.state == STATE_SCANNING

    @property
    def elapsed(self) -> float:
        if not self.started_at:
            return 0.0
        end = self.finished_at or time.monotonic()
        return end - self.started_at


class ScanRegistry(GObject.GObject):
    __gtype_name__ = "LdsScanRegistry"
    __gsignals__ = {
        "entry-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "active-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(
        self,
        model_factory: Callable[[], ScanTreeModel],
        options_factory: Callable[[], ScanOptions],
    ) -> None:
        super().__init__()
        self._model_factory = model_factory
        self._options_factory = options_factory
        self.entries: dict[str, ScanEntry] = {}
        self.queue: list[str] = []
        self.active: str | None = None

    # ---- lookup -------------------------------------------------------------

    def get(self, path: str) -> ScanEntry | None:
        return self.entries.get(path)

    def get_or_create(self, path: str) -> ScanEntry:
        entry = self.entries.get(path)
        if entry is not None:
            return entry
        model = self._model_factory()
        controller = ScanController(model)
        entry = ScanEntry(path, model, controller)
        entry.handlers = [
            controller.connect("scan-started", self._on_started, path),
            controller.connect("progress", self._on_progress, path),
            controller.connect("scan-finished", self._on_finished, path),
            controller.connect("scan-error", self._on_error, path),
        ]
        self.entries[path] = entry
        return entry

    @property
    def active_entry(self) -> ScanEntry | None:
        return self.entries.get(self.active) if self.active else None

    def done_paths(self) -> list[str]:
        return [p for p, e in self.entries.items() if e.state == STATE_DONE]

    # ---- scheduling ---------------------------------------------------------

    def request(self, path: str, *, force: bool = False, front: bool = True) -> ScanEntry:
        """Scan ``path`` (now or next). A finished scan is reused unless ``force``."""
        entry = self.get_or_create(path)
        if entry.state == STATE_DONE and not force:
            self.emit("entry-changed", path)
            return entry
        if entry.state == STATE_SCANNING:
            return entry
        if path in self.queue:
            self.queue.remove(path)
        if front:
            self.queue.insert(0, path)
        else:
            self.queue.append(path)
        entry.state = STATE_QUEUED
        self.emit("entry-changed", path)
        self._start_next()
        return entry

    def enqueue(self, paths: list[str]) -> None:
        """Queue several paths (startup auto-scan); already finished ones are skipped."""
        for path in paths:
            entry = self.get_or_create(path)
            if entry.state in (STATE_DONE, STATE_SCANNING) or path in self.queue:
                continue
            self.queue.append(path)
            entry.state = STATE_QUEUED
            self.emit("entry-changed", path)
        self._start_next()

    def cancel(self, path: str) -> None:
        entry = self.entries.get(path)
        if entry is None:
            return
        if path in self.queue:
            self.queue.remove(path)
            entry.state = STATE_IDLE
            self.emit("entry-changed", path)
        elif entry.state == STATE_SCANNING:
            entry.controller.cancel()

    def cancel_all(self) -> None:
        for path in list(self.queue):
            self.cancel(path)
        if self.active:
            self.cancel(self.active)

    def _start_next(self) -> None:
        if self.active is not None or not self.queue:
            return
        path = self.queue.pop(0)
        entry = self.entries[path]
        self.active = path
        entry.state = STATE_SCANNING
        entry.started_at = time.monotonic()
        entry.finished_at = 0.0
        entry.errors = 0
        log.info("scan starting: %s", path)
        try:
            entry.controller.start(path, self._options_factory())
        except Exception as exc:  # noqa: BLE001 - a bad path must not stall the queue
            log.error("scan could not start for %s: %s", path, exc)
            entry.state = STATE_IDLE
            self.active = None
            self.emit("entry-changed", path)
            self._start_next()
            return
        self.emit("entry-changed", path)
        self.emit("active-changed", path)

    # ---- controller signals ---------------------------------------------------

    def _on_started(self, _c: ScanController, _p: str, path: str) -> None:
        self.emit("entry-changed", path)

    def _on_progress(
        self, _c: ScanController, entries: int, alloc: int, current: str, path: str
    ) -> None:
        entry = self.entries[path]
        entry.entries, entry.alloc, entry.current_path = entries, alloc, current
        self.emit("entry-changed", path)

    def _on_error(self, _c: ScanController, _epath: str, _msg: str, path: str) -> None:
        self.entries[path].errors += 1

    def _on_finished(self, controller: ScanController, cancelled: bool, path: str) -> None:
        entry = self.entries[path]
        entry.finished_at = time.monotonic()
        entry.entries = controller.entries
        root = entry.model.root
        entry.alloc = root.alloc if root is not None else entry.alloc
        entry.state = STATE_CANCELLED if cancelled else STATE_DONE
        entry.finished_text = time.strftime("%Y-%m-%d %H:%M")
        log.info(
            "scan %s: %s (%d entries, %.1f s)",
            entry.state,
            path,
            entry.entries,
            entry.elapsed,
        )
        if self.active == path:
            self.active = None
        self.emit("entry-changed", path)
        self.emit("active-changed", "")
        self._start_next()
