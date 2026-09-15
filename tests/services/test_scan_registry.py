"""ScanRegistry: one model per root, sequential queue, reuse of finished scans."""

from __future__ import annotations

import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib  # noqa: E402

from lindrivespace.core.options import ScanOptions  # noqa: E402
from lindrivespace.models.tree_model import ScanTreeModel  # noqa: E402
from lindrivespace.services.scan_registry import (  # noqa: E402
    STATE_DONE,
    STATE_QUEUED,
    STATE_SCANNING,
    ScanRegistry,
)


def _pump(cond, timeout: float = 30.0) -> None:  # type: ignore[no-untyped-def]
    ctx = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while not cond() and time.monotonic() < deadline:
        ctx.iteration(False)
        time.sleep(0.002)


def _make_registry() -> ScanRegistry:
    return ScanRegistry(lambda: ScanTreeModel(show_files=False), lambda: ScanOptions())


def _tree(base: Path, name: str, size: int) -> Path:
    root = base / name
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "f.bin").write_bytes(b"x" * size)
    return root


def test_queue_runs_sequentially_and_reuses(tmp_path: Path) -> None:
    a = _tree(tmp_path, "a", 20_000)
    b = _tree(tmp_path, "b", 40_000)
    reg = _make_registry()
    events: list[tuple[str, str]] = []
    reg.connect("entry-changed", lambda _r, p: events.append(("entry", p)))
    reg.connect("active-changed", lambda _r, p: events.append(("active", p)))

    reg.enqueue([str(a), str(b)])
    assert reg.active == str(a)
    assert reg.get(str(b)) is not None and reg.get(str(b)).state == STATE_QUEUED
    assert reg.get(str(a)).state == STATE_SCANNING
    _pump(lambda: reg.get(str(b)).state == STATE_DONE)

    ea, eb = reg.get(str(a)), reg.get(str(b))
    assert ea.state == STATE_DONE and eb.state == STATE_DONE
    assert ea.model.root is not None and ea.model.root.files == 1
    assert eb.alloc >= 40_000 and ea.alloc < eb.alloc
    assert ea.finished_text and ea.elapsed >= 0
    assert reg.active is None and not reg.queue
    actives = [p for kind, p in events if kind == "active"]
    assert actives == [str(a), "", str(b), ""]

    # a finished scan is reused unless forced
    model_before = ea.model
    reg.request(str(a))
    assert reg.get(str(a)).model is model_before and reg.get(str(a)).state == STATE_DONE
    reg.request(str(a), force=True)
    assert reg.get(str(a)).state == STATE_SCANNING
    _pump(lambda: reg.get(str(a)).state == STATE_DONE)
    assert reg.get(str(a)).model is model_before  # same model object, rescanned


def test_request_jumps_the_queue_and_cancel(tmp_path: Path) -> None:
    roots = [_tree(tmp_path, f"r{i}", 1_000 * (i + 1)) for i in range(3)]
    reg = _make_registry()
    reg.enqueue([str(r) for r in roots])
    # the third path is requested explicitly → it goes to the front of the queue
    reg.request(str(roots[2]))
    assert reg.queue[0] == str(roots[2])
    reg.cancel(str(roots[1]))
    assert str(roots[1]) not in reg.queue and reg.get(str(roots[1])).state == "idle"
    _pump(lambda: reg.active is None and not reg.queue)
    assert reg.get(str(roots[0])).state == STATE_DONE
    assert reg.get(str(roots[2])).state == STATE_DONE
    assert reg.done_paths() == [str(roots[0]), str(roots[2])]


def test_missing_path_does_not_stall_queue(tmp_path: Path) -> None:
    good = _tree(tmp_path, "good", 500)
    reg = _make_registry()
    reg.enqueue([str(tmp_path / "does-not-exist"), str(good)])
    _pump(lambda: reg.get(str(good)) is not None and reg.get(str(good)).state == STATE_DONE)
    assert reg.get(str(good)).state == STATE_DONE
