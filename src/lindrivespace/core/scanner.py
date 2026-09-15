"""The directory-tree walker.

Pure stdlib, no GTK. Iterative DFS over an explicit stack so there is no
recursion limit and no ``os.walk`` overhead. Emits pre-order ``DirStarted``
then, once a directory's contents are exhausted, ``DirDone`` with recursive
totals (see ``docs/CONCEPT-AND-TECHNICAL-DESIGN.md`` §5.1 and its §16 errata).

This module also runs, unmodified, as the payload of ``scanner_cli.py`` under
``pkexec`` with a clean environment, so it must not import anything outside
the standard library.
"""

from __future__ import annotations

import os
import stat
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from lindrivespace.core.events import (
    DirDone,
    DirStarted,
    Finished,
    Progress,
    ScanError,
    ScanEvent,
)
from lindrivespace.core.fsnode import DENIED, EXCLUDED, MOUNTPOINT, PARTIAL, ROOT, FsNode
from lindrivespace.core.options import ScanOptions

if TYPE_CHECKING:
    import queue

    # os.scandir's return type has no public name in typeshed; alias the
    # private one purely for annotations (never instantiated directly, and
    # never evaluated at runtime thanks to ``from __future__ import annotations``).
    _ScandirIter = os._ScandirIterator[str]
    _StackEntry = tuple[FsNode, _ScandirIter]

MAX_SCAN_ERRORS = 100
PAUSE_POLL_SECONDS = 0.05


class Scanner:
    """Walks one directory tree, emitting :mod:`core.events` as it goes."""

    def scan(
        self,
        root: str,
        options: ScanOptions,
        emit: Callable[[ScanEvent], None],
        cancel: threading.Event | None = None,
        pause: threading.Event | None = None,
    ) -> FsNode:
        start = time.monotonic()
        abs_root = os.path.abspath(root)
        root_stat = os.lstat(abs_root)
        root_dev = root_stat.st_dev

        root_node = FsNode(
            1,
            abs_root,
            parent=None,
            mtime=root_stat.st_mtime,
            flags=ROOT,
            top_limit=options.top_files,
        )
        emit(DirStarted(id=1, parent_id=None, name=abs_root, mtime=root_stat.st_mtime, flags=ROOT))

        next_id = 2
        entries_count = 0
        alloc_total = 0
        error_count = 0
        cancelled = False
        seen_inodes: set[tuple[int, int]] = set()
        show_hidden = options.show_hidden
        count_hardlinks_once = options.count_hardlinks_once
        top_min = max(0, int(options.top_min_bytes))
        cross_mounts = options.cross_mounts
        is_excluded = options.is_excluded
        batch_size = options.batch_size
        progress_interval = options.progress_interval

        stack: list[_StackEntry] = []
        try:
            root_it: _ScandirIter = os.scandir(abs_root)
        except OSError as exc:
            error_count = self._report_error(emit, error_count, abs_root, str(exc))
            root_node.flags |= DENIED
            root_node.finalize()
            emit(self._dir_done(root_node))
            elapsed = time.monotonic() - start
            emit(
                Finished(
                    root_id=root_node.id, entries=entries_count, elapsed=elapsed, cancelled=False
                )
            )
            return root_node

        stack.append((root_node, root_it))
        last_progress_time = time.monotonic()
        last_progress_entries = 0

        while stack:
            # Checked every iteration (cheap) rather than every 1000 entries:
            # this satisfies "at least once per directory" for small
            # directories too, not just the "every 1000 entries" minimum.
            if cancel is not None and cancel.is_set():
                cancelled = True
                break
            if pause is not None:
                while pause.is_set():
                    if cancel is not None and cancel.is_set():
                        cancelled = True
                        break
                    time.sleep(PAUSE_POLL_SECONDS)
                if cancelled:
                    break

            node, it = stack[-1]
            try:
                entry = next(it)
            except StopIteration:
                it.close()
                stack.pop()
                node.finalize()
                emit(self._dir_done(node))
                continue
            except PermissionError:
                node.flags |= DENIED
                it.close()
                stack.pop()
                node.finalize()
                emit(self._dir_done(node))
                continue
            except OSError as exc:
                error_count = self._report_error(emit, error_count, node.path(), str(exc))
                it.close()
                stack.pop()
                node.finalize()
                emit(self._dir_done(node))
                continue

            name = entry.name
            if not show_hidden and name[0] == ".":
                continue

            entries_count += 1

            try:
                is_dir = entry.is_dir(follow_symlinks=False)
                st = entry.stat(follow_symlinks=False)
            except OSError as exc:
                error_count = self._report_error(emit, error_count, entry.path, str(exc))
                continue

            if is_dir:
                child_flags = 0
                crosses_mount = st.st_dev != root_dev
                if crosses_mount:
                    child_flags |= MOUNTPOINT
                excluded = is_excluded(entry.path)
                if excluded:
                    child_flags |= EXCLUDED

                child = FsNode(next_id, name, node, mtime=st.st_mtime, flags=child_flags)
                next_id += 1
                emit(
                    DirStarted(
                        id=child.id,
                        parent_id=node.id,
                        name=name,
                        mtime=st.st_mtime,
                        flags=child_flags,
                    )
                )

                descend = not excluded and (not crosses_mount or cross_mounts)
                child_it: _ScandirIter | None = None
                if descend:
                    try:
                        child_it = os.scandir(entry.path)
                    except PermissionError:
                        child.flags |= DENIED
                        descend = False
                    except OSError as exc:
                        error_count = self._report_error(emit, error_count, entry.path, str(exc))
                        descend = False

                if descend and child_it is not None:
                    stack.append((child, child_it))
                else:
                    child.finalize()
                    emit(self._dir_done(child))
            else:
                is_symlink = entry.is_symlink()
                if is_symlink or stat.S_ISREG(st.st_mode):
                    size = st.st_size
                    alloc = st.st_blocks * 512
                else:
                    # fifo, socket, block/char device, other special files
                    size = 0
                    alloc = 0

                add_it = True
                if st.st_nlink > 1 and count_hardlinks_once:
                    key = (st.st_dev, st.st_ino)
                    if key in seen_inodes:
                        add_it = False
                    else:
                        seen_inodes.add(key)

                if add_it:
                    node.add_file(size, alloc, st.st_mtime, name, alloc >= top_min)
                    alloc_total += alloc

            now = time.monotonic()
            if (
                entries_count - last_progress_entries >= batch_size
                or now - last_progress_time >= progress_interval
            ):
                emit(Progress(entries_count, alloc_total, entry.path))
                last_progress_entries = entries_count
                last_progress_time = now

        if cancelled:
            for _open_node, open_it in stack:
                open_it.close()
            for open_node, _open_it in reversed(stack):
                open_node.flags |= PARTIAL
                open_node.finalize()
                emit(self._dir_done(open_node))

        elapsed = time.monotonic() - start
        emit(
            Finished(
                root_id=root_node.id, entries=entries_count, elapsed=elapsed, cancelled=cancelled
            )
        )
        return root_node

    @staticmethod
    def _dir_done(node: FsNode) -> DirDone:
        return DirDone(
            id=node.id,
            size=node.size,
            alloc=node.alloc,
            files=node.files,
            dirs=node.dirs,
            mtime_max=node.mtime_max,
            flags=node.flags,
            top_files=tuple(node.top_files),
        )

    @staticmethod
    def _report_error(
        emit: Callable[[ScanEvent], None], error_count: int, path: str, message: str
    ) -> int:
        error_count += 1
        if error_count <= MAX_SCAN_ERRORS:
            emit(ScanError(path=path, message=message))
        return error_count


class ScanThread(threading.Thread):
    """Runs :class:`Scanner` on a background thread, queueing its events.

    ``root_node`` and ``error`` are populated once the thread has finished;
    ``error`` holds the exception if the scan aborted unexpectedly (a
    ``Finished`` event with ``cancelled=False`` is still queued in that case
    so the drain loop always sees a terminal event).
    """

    def __init__(
        self,
        root: str,
        options: ScanOptions,
        queue: queue.SimpleQueue[ScanEvent],
        cancel: threading.Event | None = None,
        pause: threading.Event | None = None,
    ) -> None:
        super().__init__(daemon=True)
        self._root = root
        self._options = options
        self._queue = queue
        self._cancel = cancel if cancel is not None else threading.Event()
        self._pause = pause if pause is not None else threading.Event()
        self.root_node: FsNode | None = None
        self.error: Exception | None = None

    def run(self) -> None:
        scanner = Scanner()
        try:
            self.root_node = scanner.scan(
                self._root, self._options, self._queue.put, self._cancel, self._pause
            )
        except Exception as exc:  # noqa: BLE001 - must still terminate the queue
            self.error = exc
            self._queue.put(ScanError(path=self._root, message=str(exc)))
            self._queue.put(Finished(root_id=0, entries=0, elapsed=0.0, cancelled=False))

    def cancel(self) -> None:
        self._cancel.set()

    def pause(self) -> None:
        self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    def is_paused(self) -> bool:
        return self._pause.is_set()
