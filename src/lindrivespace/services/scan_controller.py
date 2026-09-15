"""Bridges a scanner thread (or any event producer) to the tree model on the GTK main loop.

Events arrive on a ``queue.SimpleQueue``; a 16 ms ``GLib.timeout_add`` drains
them in slices of at most ``budget_ms`` (8 ms by default, measured with
``GLib.get_monotonic_time``) so scrolling stays smooth during a scan.
The same drain path serves the in-process ``ScanThread`` and the pkexec helper
(WP11), which is why the producer is abstracted as *any* object with
``cancel()`` / ``pause()`` / ``resume()``.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Protocol

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, GObject  # noqa: E402

from lindrivespace.core.events import Finished, Progress, ScanError, ScanEvent  # noqa: E402
from lindrivespace.core.options import ScanOptions  # noqa: E402
from lindrivespace.models.tree_model import ScanTreeModel  # noqa: E402


class Producer(Protocol):
    def cancel(self) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def is_alive(self) -> bool: ...


class ScanController(GObject.GObject):
    __gtype_name__ = "LdsScanController"
    __gsignals__ = {
        "scan-started": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        # int64: entry counts fit in gint, byte totals (6.2 GB) do not.
        "progress": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (GObject.TYPE_INT64, GObject.TYPE_INT64, str),
        ),
        "batch-applied": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "scan-finished": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        "scan-error": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),
    }

    TICK_MS = 16

    def __init__(self, model: ScanTreeModel, *, budget_ms: float = 8.0) -> None:
        super().__init__()
        self.model = model
        self.budget_us = int(budget_ms * 1000)
        self.queue: queue.SimpleQueue[ScanEvent] | None = None
        self.producer: Producer | None = None
        self.path: str | None = None
        self.options: ScanOptions | None = None
        self.running = False
        self.paused = False
        self.started_at = 0.0
        self.entries = 0
        self.alloc = 0
        self.current_path = ""
        self.last_drain_us = 0
        self.max_drain_us = 0
        self._timer_id = 0
        self._pending_progress: Progress | None = None

    # ------------------------------------------------------------- lifecycle

    def start(self, path: str, options: ScanOptions | None = None) -> None:
        """Scan ``path`` in a worker thread (core.scanner.ScanThread)."""
        from lindrivespace.core.scanner import ScanThread

        opts = options or ScanOptions()
        q: queue.SimpleQueue[ScanEvent] = queue.SimpleQueue()
        thread = ScanThread(path, opts, q)
        thread.daemon = True
        self._begin(path, opts, q, thread)
        thread.start()

    def consume(
        self,
        path: str,
        q: queue.SimpleQueue[ScanEvent],
        producer: Producer | None = None,
        options: ScanOptions | None = None,
    ) -> None:
        """Drain an externally produced event stream (tests, pkexec helper)."""
        self._begin(path, options or ScanOptions(), q, producer)

    def _begin(
        self,
        path: str,
        options: ScanOptions,
        q: queue.SimpleQueue[ScanEvent],
        producer: Producer | None,
    ) -> None:
        if self.running:
            self.cancel()
        self.model.reset()
        self.queue = q
        self.producer = producer
        self.path = path
        self.options = options
        self.running = True
        self.paused = False
        self.started_at = time.monotonic()
        self.entries = 0
        self.alloc = 0
        self.current_path = path
        self.max_drain_us = 0
        self._pending_progress = None
        if self._timer_id:
            GLib.source_remove(self._timer_id)
        self._timer_id = GLib.timeout_add(self.TICK_MS, self._drain)
        self.emit("scan-started", path)

    def cancel(self) -> None:
        if self.producer is not None:
            self.producer.cancel()
        if self.paused:
            self.resume()

    def pause(self) -> None:
        if self.producer is not None and self.running and not self.paused:
            self.producer.pause()
            self.paused = True

    def resume(self) -> None:
        if self.producer is not None and self.paused:
            self.producer.resume()
            self.paused = False

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at if self.started_at else 0.0

    # ----------------------------------------------------------------- drain

    def _drain(self) -> bool:
        if self.queue is None:
            self._timer_id = 0
            return False
        start = GLib.get_monotonic_time()
        deadline = start + self.budget_us
        finished: Finished | None = None
        applied = 0
        q = self.queue
        model = self.model
        while True:
            try:
                event = q.get_nowait()
            except queue.Empty:
                break
            applied += 1
            if isinstance(event, Progress):
                self._pending_progress = event
            elif isinstance(event, ScanError):
                model.apply(event)
                self.emit("scan-error", event.path, event.message)
            elif isinstance(event, Finished):
                model.apply(event)
                finished = event
                break
            else:
                model.apply(event)
            if (applied & 0xFF) == 0 and GLib.get_monotonic_time() > deadline:
                break
        if applied:
            model.flush()
            self.emit("batch-applied")
        if self._pending_progress is not None:
            p = self._pending_progress
            self._pending_progress = None
            self.entries, self.alloc, self.current_path = p.entries, p.alloc, p.current_path
            self.emit("progress", p.entries, p.alloc, p.current_path)
        self.last_drain_us = GLib.get_monotonic_time() - start
        if self.last_drain_us > self.max_drain_us:
            self.max_drain_us = self.last_drain_us
        if finished is not None:
            self.entries = finished.entries
            self.running = False
            self.paused = False
            self._timer_id = 0
            self.queue = None
            self.emit("scan-finished", finished.cancelled)
            return False
        return True


class FakeProducer(threading.Thread):
    """Replays a list of events onto a queue from a thread — for tests and demos."""

    def __init__(
        self,
        events: list[ScanEvent],
        q: queue.SimpleQueue[ScanEvent],
        *,
        pace_every: int = 0,
        pace_seconds: float = 0.001,
    ) -> None:
        super().__init__(daemon=True)
        self.events = events
        self.q = q
        self.pace_every = pace_every
        self.pace_seconds = pace_seconds
        self.cancelled = False
        self._cancel = threading.Event()
        self._pause = threading.Event()

    def run(self) -> None:
        for i, event in enumerate(self.events):
            while self._pause.is_set() and not self._cancel.is_set():
                time.sleep(0.005)
            if self._cancel.is_set():
                self.cancelled = True
                # Mirror ScanThread: a cancelled scan still ends with Finished.
                self.q.put(Finished(1, i, 0.0, cancelled=True))
                return
            if self.pace_every and i and i % self.pace_every == 0:
                time.sleep(self.pace_seconds)
            self.q.put(event)

    def cancel(self) -> None:
        self._cancel.set()

    def pause(self) -> None:
        self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    def is_alive(self) -> bool:  # type: ignore[override]
        return super().is_alive()
