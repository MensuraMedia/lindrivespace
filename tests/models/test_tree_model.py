"""WP6: lazy tree model + scan controller drain (needs a display)."""

from __future__ import annotations

import queue
import time

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from lindrivespace.core import fsnode as fs  # noqa: E402
from lindrivespace.core.events import (  # noqa: E402
    DirDone,
    DirStarted,
    Finished,
    Progress,
    ScanEvent,
)
from lindrivespace.core.fsnode import TopFile  # noqa: E402
from lindrivespace.models.tree_model import Col, ScanTreeModel  # noqa: E402
from lindrivespace.services.scan_controller import FakeProducer, ScanController  # noqa: E402


def make_events() -> list[ScanEvent]:
    """/home (1) → user (2) → {.cache (3) [mozilla (4)], Videos (5)}, docker (6, denied)."""
    ev: list[ScanEvent] = [
        DirStarted(1, None, "/home", 1.0, fs.ROOT),
        DirStarted(2, 1, "user", 2.0),
        DirStarted(3, 2, ".cache", 3.0),
        DirStarted(4, 3, "mozilla", 4.0),
        DirDone(4, 60, 64, 10, 0, 40.0, 0, (TopFile(64, 60, 40.0, "cache2"),)),
        DirDone(3, 100, 128, 20, 1, 40.0),
        DirStarted(5, 2, "Videos", 5.0),
        DirDone(5, 300, 320, 3, 0, 50.0),
        Progress(40, 448, "/home/user/Videos"),
        DirDone(2, 410, 460, 24, 3, 50.0),
        DirStarted(6, 1, "docker", 6.0, fs.DENIED),
        DirDone(6, 0, 0, 0, 0, 6.0, fs.DENIED),
        DirDone(1, 410, 460, 24, 5, 50.0),
        Finished(1, 40, 0.01),
    ]
    return ev


def rows(model: ScanTreeModel, it: Gtk.TreeIter | None) -> list[tuple[str, str, bool]]:
    """(name, percent text, bold) for each child row, via the draw-time formatters."""
    out = []
    child = model.store.iter_children(it)
    while child is not None:
        node = model.node_for_iter(child)
        if node is None:
            out.append(("…", "", False))
        else:
            out.append((node.name, model.display(node, "percent"), model.is_bold(node)))
        child = model.store.iter_next(child)
    return out


def test_lazy_population_and_totals() -> None:
    m = ScanTreeModel(top_n_bold=1)
    m.apply_many(make_events())
    root_it = m.store.get_iter_first()
    assert root_it is not None
    root = m.node_for_iter(root_it)
    assert root is not None
    assert m.store.get_value(root_it, Col.NAME) == "/home"
    assert m.display(root, "alloc") == "460 Bytes"
    assert m.display(root, "percent") == "100.0 %"
    # root children are populated, sorted by alloc desc: user (460) then docker (0)
    assert [r[0] for r in rows(m, root_it)] == ["user", "docker"]
    user_it = m.store.iter_children(root_it)
    assert user_it is not None
    # user is NOT populated yet: one dummy child gives it an expander
    assert m.store.iter_n_children(user_it) == 1
    dummy = m.store.iter_children(user_it)
    assert dummy is not None and m.is_dummy(dummy)
    # populate on expand
    m.populate(user_it)
    names = [r[0] for r in rows(m, user_it)]
    assert names == ["Videos", ".cache"]
    pcts = [r[1] for r in rows(m, user_it)]
    assert pcts[0] == f"{320 / 460 * 100:.1f} %"
    # top-1 bold
    assert [r[2] for r in rows(m, user_it)] == [True, False]
    # denied row shows dashes for counts and the lock icon
    docker = m.nodes[6]
    assert m.display(docker, "files") == "—"
    assert m.display(docker, "icon") == "changes-prevent-symbolic"
    # top files restored from DirDone
    mozilla = m.nodes[4]
    assert mozilla.top_files[0].name == "cache2"


def test_sort_reorders_and_keeps_population() -> None:
    m = ScanTreeModel()
    m.apply_many(make_events())
    root_it = m.store.get_iter_first()
    assert root_it is not None
    user_it = m.store.iter_children(root_it)
    assert user_it is not None
    m.populate(user_it)
    m.set_sort("name", False)
    assert [r[0] for r in rows(m, root_it)] == ["docker", "user"]
    user_it = m.iter_for_node(m.nodes[2])
    assert user_it is not None
    assert [r[0] for r in rows(m, user_it)] == [".cache", "Videos"]
    assert 2 in m.populated  # still populated after reorder
    m.set_sort("alloc", True)
    assert [r[0] for r in rows(m, user_it)] == ["Videos", ".cache"]
    m.set_primary(False)  # apparent size: Videos 300 vs .cache 100 → same order, new labels
    assert m.display(m.nodes[2], "name_size") == "410 Bytes"


def test_running_totals_before_parent_done() -> None:
    m = ScanTreeModel()
    events = make_events()
    m.apply_many(events[:8])  # up to Videos done; user and root not done yet
    user = m.nodes[2]
    assert user.alloc == 128 + 320  # running total from children
    assert m.display(m.nodes[1], "alloc") == "448 Bytes"
    assert m.nodes[1].dirs == 4  # user, .cache, mozilla, Videos seen so far
    assert m.scanning is True
    m.apply_many(events[8:])
    assert m.scanning is False
    assert m.nodes[1].alloc == 460


def test_reveal_populates_ancestors() -> None:
    m = ScanTreeModel()
    m.apply_many(make_events())
    it = m.reveal(m.nodes[4])
    assert it is not None
    assert m.store.get_value(it, Col.NAME) == "mozilla"
    # cell data func fills a text renderer from the node
    cell = Gtk.CellRendererText()
    m.cell_data_func("alloc")(Gtk.TreeViewColumn(), cell, m.store, it, None)
    assert cell.get_property("text") == "64 Bytes"
    assert {1, 2, 3} <= m.populated


def _pump(cond, timeout: float = 5.0) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while not cond() and time.monotonic() < deadline:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        GLib.MainContext.default().iteration(False)
        time.sleep(0.002)


def big_stream(n_dirs: int) -> list[ScanEvent]:
    ev: list[ScanEvent] = [DirStarted(1, None, "/big", 0.0, fs.ROOT)]
    for i in range(2, n_dirs + 2):
        ev.append(DirStarted(i, 1, f"d{i}", float(i)))
        ev.append(DirDone(i, i, i * 2, 1, 0, float(i)))
        if i % 1000 == 0:
            ev.append(Progress(i, i, f"/big/d{i}"))
    ev.append(DirDone(1, 0, 0, 0, n_dirs, 0.0))
    ev.append(Finished(1, n_dirs, 0.1))
    return ev


def test_controller_drains_within_budget() -> None:
    m = ScanTreeModel()
    ctl = ScanController(m, budget_ms=8.0)
    seen = {"started": 0, "finished": None, "progress": 0, "batches": 0}
    ctl.connect("scan-started", lambda _c, _p: seen.__setitem__("started", seen["started"] + 1))
    ctl.connect("scan-finished", lambda _c, cancelled: seen.__setitem__("finished", cancelled))
    ctl.connect("progress", lambda _c, *_a: seen.__setitem__("progress", seen["progress"] + 1))
    ctl.connect("batch-applied", lambda _c: seen.__setitem__("batches", seen["batches"] + 1))

    q: queue.SimpleQueue[ScanEvent] = queue.SimpleQueue()
    producer = FakeProducer(big_stream(10_000), q)
    ctl.consume("/big", q, producer)
    producer.start()
    _pump(lambda: seen["finished"] is not None, timeout=30.0)

    assert seen["started"] == 1
    assert seen["finished"] is False
    assert seen["progress"] >= 1
    assert seen["batches"] >= 2  # drained in slices, not in one go
    assert ctl.running is False
    assert m.entries == 10_000
    root_it = m.store.get_iter_first()
    assert root_it is not None
    assert m.store.iter_n_children(root_it) == 10_000
    # The final flush re-sorts the 10k-wide root once; every other slice stays near budget.
    assert ctl.max_drain_us < 400_000, ctl.max_drain_us


def test_controller_cancel_stops_producer() -> None:
    m = ScanTreeModel()
    ctl = ScanController(m)
    done = {"v": None}
    ctl.connect("scan-finished", lambda _c, cancelled: done.__setitem__("v", cancelled))
    q: queue.SimpleQueue[ScanEvent] = queue.SimpleQueue()
    events = big_stream(20_000)
    producer = FakeProducer(events, q, pace_every=200, pace_seconds=0.002)  # ~0.4 s stream
    ctl.consume("/big", q, producer)
    producer.start()
    _pump(lambda: len(m.nodes) > 500, timeout=10.0)
    assert ctl.running
    ctl.cancel()
    producer.join(timeout=5.0)
    assert not producer.is_alive() and producer.cancelled
    _pump(lambda: done["v"] is not None, timeout=30.0)
    assert done["v"] is True
    assert ctl.running is False
    assert 500 < len(m.nodes) < 20_001


def test_controller_real_scan(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """End to end: ScanThread → queue → controller drain → model rows."""
    root_dir = tmp_path / "scanroot"  # tmp_path itself also holds the XDG fixture dirs
    for d in ("alpha", "beta", "beta/deep"):
        (root_dir / d).mkdir(parents=True)
    (root_dir / "alpha" / "big.bin").write_bytes(b"x" * 200_000)
    (root_dir / "beta" / "deep" / "small.txt").write_bytes(b"y" * 1_000)
    m = ScanTreeModel()
    ctl = ScanController(m)
    done = {"v": None}
    ctl.connect("scan-finished", lambda _c, cancelled: done.__setitem__("v", cancelled))
    ctl.start(str(root_dir))
    _pump(lambda: done["v"] is not None, timeout=30.0)
    assert done["v"] is False
    root = m.root
    assert root is not None and root.finalized
    assert root.files == 2 and root.dirs == 3
    assert sorted(c.name for c in root.children) == ["alpha", "beta"]
    root_it = m.store.get_iter_first()
    assert root_it is not None
    assert [r[0] for r in rows(m, root_it)] == ["alpha", "beta"]  # rows sorted by alloc desc
    assert m.display(root, "files") == "2"
