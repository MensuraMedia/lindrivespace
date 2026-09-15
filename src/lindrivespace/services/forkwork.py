"""Run CPU-heavy work in a forked child so it never holds the GIL of the UI process.

Threads looked like the obvious tool for snapshot saving and History diffs, but
gzip, the JSON codec and the node-rebuild loops hold the interpreter lock for
hundreds of milliseconds at a time, which froze the main loop (measured 0.3-1.8 s
stalls; docs/BACKLOG.md E1). A forked child inherits the process memory
copy-on-write -- no pickling of a million-node tree -- and runs on its own
interpreter, so the parent's main loop is untouched (measured max 30 ms).

Rules for the callable: pure Python + file I/O only; never touch GTK, GLib or
logging (the child exits with ``os._exit`` and only its pickled return value
comes back over a pipe). Linux only, which is all LinDriveSpace targets.
"""

from __future__ import annotations

import os
import pickle
import warnings
from collections.abc import Callable
from typing import Any

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from lindrivespace import logsetup  # noqa: E402

log = logsetup.get_logger("forkwork")

DoneCallback = Callable[[Any, str | None], None]


def run_in_child(work: Callable[[], Any], on_done: DoneCallback) -> int:
    """Fork, run ``work()`` in the child, deliver its result to ``on_done(result, error)``
    on the main loop. Returns the child's pid (0 if forking failed and the work
    ran inline instead)."""
    read_fd, write_fd = os.pipe()
    try:
        with warnings.catch_warnings():
            # Python 3.12 warns about fork() in a threaded process; the child runs
            # only pure-Python work and exits with os._exit, which is the safe subset.
            warnings.simplefilter("ignore", DeprecationWarning)
            pid = os.fork()
    except OSError as exc:  # out of processes: do it inline rather than not at all
        os.close(read_fd)
        os.close(write_fd)
        log.warning("fork failed (%s); running inline", exc)
        try:
            on_done(work(), None)
        except Exception as inline_exc:  # noqa: BLE001
            on_done(None, repr(inline_exc))
        return 0

    if pid == 0:  # ---- child
        os.close(read_fd)
        try:
            payload = pickle.dumps(("ok", work()), protocol=pickle.HIGHEST_PROTOCOL)
        except BaseException as exc:  # noqa: BLE001 - report anything, then exit
            try:
                payload = pickle.dumps(("err", repr(exc)))
            except BaseException:  # noqa: BLE001
                payload = pickle.dumps(("err", "unpicklable error in child"))
        try:
            written = 0
            while written < len(payload):
                written += os.write(write_fd, payload[written:])
        finally:
            os._exit(0)

    # ---- parent
    os.close(write_fd)
    chunks: list[bytes] = []

    def on_readable(fd: int, condition: GLib.IOCondition) -> bool:
        try:
            data = os.read(fd, 1 << 16)
        except OSError:
            data = b""
        if data:
            chunks.append(data)
            return True
        os.close(fd)
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass
        result: Any = None
        error: str | None = None
        try:
            status, value = pickle.loads(b"".join(chunks))
            if status == "ok":
                result = value
            else:
                error = str(value)
        except Exception as exc:  # noqa: BLE001 - child died before writing
            error = f"child produced no result: {exc}"
        on_done(result, error)
        return False

    GLib.io_add_watch(
        read_fd,
        GLib.PRIORITY_DEFAULT,
        GLib.IOCondition.IN | GLib.IOCondition.HUP | GLib.IOCondition.ERR,
        on_readable,
    )
    return pid
