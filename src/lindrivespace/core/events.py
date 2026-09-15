"""Events emitted by the scanner (worker side) and consumed by the UI (main loop).

This module is a frozen contract between the core and the tree model: the
scanner puts these on a ``queue.SimpleQueue``; the scan controller drains them
on the GTK main loop. Ids are plain integers assigned by the scanner in
pre-order; no path strings travel on the queue except in ``Progress`` and
``ScanError`` for display.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lindrivespace.core.fsnode import TopFile


@dataclass(slots=True, frozen=True)
class DirStarted:
    """A directory was opened. Emitted before any of its contents."""

    id: int
    parent_id: int | None  # None for the scan root
    name: str  # basename; the root carries its absolute path
    mtime: float
    flags: int = 0


@dataclass(slots=True, frozen=True)
class DirDone:
    """A directory and its whole subtree are complete. Totals are recursive."""

    id: int
    size: int
    alloc: int
    files: int
    dirs: int
    mtime_max: float
    flags: int = 0
    top_files: tuple[TopFile, ...] = field(default_factory=tuple)


@dataclass(slots=True, frozen=True)
class Progress:
    """Periodic heartbeat for the progress pill."""

    entries: int
    alloc: int
    current_path: str


@dataclass(slots=True, frozen=True)
class Finished:
    """The scan ended (normally or by cancellation)."""

    root_id: int
    entries: int
    elapsed: float
    cancelled: bool = False


@dataclass(slots=True, frozen=True)
class ScanError:
    """A non-fatal problem worth telling the user about."""

    path: str
    message: str


ScanEvent = DirStarted | DirDone | Progress | Finished | ScanError
