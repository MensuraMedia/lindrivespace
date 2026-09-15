"""Forked workers: results and errors come back on the main loop; no zombies."""

from __future__ import annotations

import os
import time

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from lindrivespace.services import forkwork  # noqa: E402


def _wait(box: list, timeout: float = 10.0) -> None:  # type: ignore[type-arg]
    ctx = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while not box and time.monotonic() < deadline:
        ctx.iteration(False)
        time.sleep(0.005)


def test_result_is_delivered_from_the_child() -> None:
    got: list = []
    pid = forkwork.run_in_child(
        lambda: {"pid": os.getpid(), "n": sum(range(1000))}, lambda r, e: got.append((r, e))
    )
    _wait(got)
    assert got and got[0][1] is None
    assert got[0][0]["n"] == 499500
    assert got[0][0]["pid"] != os.getpid() and pid == got[0][0]["pid"]
    # reaped: waitpid on the child now raises (no such child)
    try:
        os.waitpid(pid, os.WNOHANG)
        reaped = False
    except ChildProcessError:
        reaped = True
    assert reaped


def test_exception_in_child_becomes_error() -> None:
    got: list = []

    def boom() -> None:
        raise ValueError("nope")

    forkwork.run_in_child(boom, lambda r, e: got.append((r, e)))
    _wait(got)
    assert got[0][0] is None and "nope" in (got[0][1] or "")


def test_parent_memory_is_not_modified_by_the_child() -> None:
    shared = {"value": 1}
    got: list = []

    def mutate() -> int:
        shared["value"] = 99
        return shared["value"]

    forkwork.run_in_child(mutate, lambda r, e: got.append(r))
    _wait(got)
    assert got == [99] and shared["value"] == 1  # copy-on-write: parent unchanged
