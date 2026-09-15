from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from lindrivespace.core.events import DirDone, DirStarted, Finished, Progress, ScanError
from lindrivespace.core.fsnode import DENIED, EXCLUDED, MOUNTPOINT, PARTIAL, ROOT, FsNode
from lindrivespace.core.options import ScanOptions
from lindrivespace.core.scanner import Scanner, ScanThread

SRC = Path(__file__).resolve().parents[2] / "src"
CLI = SRC / "lindrivespace" / "core" / "scanner_cli.py"


# ---------------------------------------------------------------------------
# fixture tree
# ---------------------------------------------------------------------------


def build_fixture(tmp_path: Path) -> Path:
    """A small tree exercising every scanner rule; returns its root."""
    root = tmp_path / "root"
    root.mkdir()

    # plain files
    (root / "a.txt").write_text("hello")
    (root / "b.txt").write_text("world!!")

    # sparse file: apparent 10 MiB, allocated ~0
    with (root / "sparse.bin").open("wb") as f:
        f.truncate(10 * 1024 * 1024)

    # hard-link pair
    (root / "link_a.txt").write_text("linked-content")
    os.link(root / "link_a.txt", root / "link_b.txt")

    # nested dir with its own files
    nested = root / "nested"
    nested.mkdir()
    (nested / "c.txt").write_text("cccc")

    # dotfile/dot-dir hidden by default rules
    (root / ".hidden_file").write_text("secret")
    hidden_dir = root / ".hidden_dir"
    hidden_dir.mkdir()
    (hidden_dir / "inside.txt").write_text("still hidden")

    # excluded directory
    excluded = root / "excluded"
    excluded.mkdir()
    (excluded / "should_not_count.txt").write_text("x" * 100)

    # symlink loop: a directory symlink pointing back to its own parent
    loop_dir = root / "loop"
    loop_dir.mkdir()
    os.symlink(root, loop_dir / "back_to_root", target_is_directory=True)

    if os.geteuid() != 0:
        denied = root / "denied"
        denied.mkdir()
        (denied / "unreadable.txt").write_text("nope")
        os.chmod(denied, 0)

    return root


@pytest.fixture
def fixture_tree(tmp_path: Path) -> Iterator[Path]:
    root = build_fixture(tmp_path)
    yield root
    denied = root / "denied"
    if denied.exists():
        os.chmod(denied, 0o755)  # let pytest's tmp_path cleanup remove it


def scan_tree(
    root: Path, options: ScanOptions | None = None, **kwargs: object
) -> tuple[FsNode, list[object]]:
    events: list[object] = []
    opts = options if options is not None else ScanOptions()
    node = Scanner().scan(str(root), opts, events.append, **kwargs)  # type: ignore[arg-type]
    return node, events


def independent_walk_totals(
    root: Path, count_hardlinks_once: bool = True, show_hidden: bool = True
) -> tuple[int, int, int]:
    """Reference totals computed independently of ``Scanner``.

    Recursive (recursion is fine for a test helper) rather than iterative,
    and written straight from the spec rather than by reading scanner.py, so
    it exercises the same rules -- hidden entries (``show_hidden`` defaults
    to True, matching ``ScanOptions``), symlinks counted as their own lstat
    size but never descended, one mount device, denied dirs contributing
    nothing -- without sharing any code with it.
    """
    import stat as stat_module

    root_dev = os.lstat(root).st_dev
    seen: set[tuple[int, int]] = set()
    totals = [0, 0, 0]  # size, alloc, files

    def walk(path: str) -> None:
        try:
            entries = list(os.scandir(path))
        except OSError:
            return
        for entry in entries:
            if not show_hidden and entry.name.startswith("."):
                continue
            if entry.is_dir(follow_symlinks=False):
                try:
                    dst = os.lstat(entry.path)
                except OSError:
                    continue
                if dst.st_dev != root_dev:
                    continue
                walk(entry.path)
            else:
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if st.st_nlink > 1 and count_hardlinks_once:
                    key = (st.st_dev, st.st_ino)
                    if key in seen:
                        continue
                    seen.add(key)
                if entry.is_symlink() or stat_module.S_ISREG(st.st_mode):
                    size = st.st_size
                    alloc = st.st_blocks * 512
                else:
                    size = 0
                    alloc = 0
                totals[0] += size
                totals[1] += alloc
                totals[2] += 1

    walk(str(root))
    return totals[0], totals[1], totals[2]


def test_totals_match_independent_walk(fixture_tree: Path) -> None:
    root = fixture_tree
    node, _events = scan_tree(root)
    exp_size, exp_alloc, exp_files = independent_walk_totals(root)
    assert node.size == exp_size
    assert node.alloc == exp_alloc
    assert node.files == exp_files


def test_hardlink_dedupe_default_counts_once(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "orig.txt").write_text("x" * 1000)
    os.link(root / "orig.txt", root / "twin.txt")
    node, _events = scan_tree(root)
    assert node.files == 1
    assert node.size == 1000


def test_hardlink_dedupe_disabled_counts_twice(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "orig.txt").write_text("x" * 1000)
    os.link(root / "orig.txt", root / "twin.txt")
    node, _events = scan_tree(root, ScanOptions(count_hardlinks_once=False))
    assert node.files == 2
    assert node.size == 2000


def test_sparse_file_size_vs_alloc(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with (root / "sparse.bin").open("wb") as f:
        f.truncate(10 * 1024 * 1024)
    node, _events = scan_tree(root)
    assert node.size == 10 * 1024 * 1024
    assert node.alloc < node.size


def test_symlink_loop_does_not_recurse(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    loop_dir = root / "loop"
    loop_dir.mkdir()
    os.symlink(root, loop_dir / "back", target_is_directory=True)
    # must terminate at all, and the symlink must be counted as a file, not a dir
    node, events = scan_tree(root)
    dir_started = [e for e in events if isinstance(e, DirStarted)]
    names = {e.name for e in dir_started}
    assert "back" not in names
    loop_node = next(c for c in node.children if c.name == "loop")
    assert loop_node.files == 1
    assert loop_node.dirs == 0


def test_excluded_directory_listed_not_descended(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    excluded = root / "skip_me"
    excluded.mkdir()
    (excluded / "f.txt").write_text("x" * 500)
    opts = ScanOptions(excludes=(str(excluded),))
    node, events = scan_tree(root, opts)
    dir_started = {e.name: e for e in events if isinstance(e, DirStarted)}
    assert "skip_me" in dir_started
    assert dir_started["skip_me"].flags & EXCLUDED
    excluded_node = next(c for c in node.children if c.name == "skip_me")
    assert excluded_node.files == 0
    assert excluded_node.size == 0


def test_hidden_entries_skipped_by_default(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / ".dotfile").write_text("x")
    dotdir = root / ".dotdir"
    dotdir.mkdir()
    (dotdir / "inside.txt").write_text("y" * 50)
    node, events = scan_tree(root, ScanOptions(show_hidden=False))
    dir_started_names = {e.name for e in events if isinstance(e, DirStarted)}
    assert ".dotdir" not in dir_started_names
    assert node.files == 0
    assert node.dirs == 0


def test_hidden_entries_shown_when_enabled(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / ".dotfile").write_text("x")
    node, _events = scan_tree(root, ScanOptions(show_hidden=True))
    assert node.files == 1


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses permission checks")
def test_denied_directory_gets_flag(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    denied = root / "denied"
    denied.mkdir()
    (denied / "secret.txt").write_text("nope")
    os.chmod(denied, 0)
    try:
        node, events = scan_tree(root)
    finally:
        os.chmod(denied, 0o755)
    # DENIED can only be known once scandir() is attempted, so DirStarted
    # (pre-order, before that attempt) does not carry it -- only DirDone does.
    denied_started = next(e for e in events if isinstance(e, DirStarted) and e.name == "denied")
    assert denied_started.flags == 0
    denied_done = next(e for e in events if isinstance(e, DirDone) and e.id == denied_started.id)
    assert denied_done.flags & DENIED
    denied_node = next(c for c in node.children if c.name == "denied")
    assert denied_node.flags & DENIED
    assert denied_node.files == 0


def test_mountpoint_flag_and_no_cross(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Real bind mounts need root, so fake the scan root's own st_dev instead:
    # the scanner only reaches os.lstat() for the root itself (children go
    # through DirEntry.stat(), which os.lstat monkeypatching cannot touch),
    # so this makes every real child directory look like it's on another
    # device relative to the (faked) root -- enough to exercise the
    # MOUNTPOINT / cross_mounts=False path end to end.
    root = tmp_path / "root"
    root.mkdir()
    other = root / "other_fs"
    other.mkdir()
    (other / "f.txt").write_text("x" * 999)

    real_dev = os.lstat(root).st_dev
    real_lstat = os.lstat

    class FakeStat:
        def __init__(self, real: os.stat_result) -> None:
            self._real = real

        def __getattr__(self, name: str) -> object:
            if name == "st_dev":
                return real_dev + 1
            return getattr(self._real, name)

    def fake_lstat(path: object, *a: object, **kw: object) -> object:
        real = real_lstat(path, *a, **kw)  # type: ignore[arg-type]
        if os.path.abspath(str(path)) == str(root):
            return FakeStat(real)
        return real

    monkeypatch.setattr(os, "lstat", fake_lstat)
    node, events = scan_tree(root)
    other_started = next(e for e in events if isinstance(e, DirStarted) and e.name == "other_fs")
    assert other_started.flags & MOUNTPOINT
    other_node = next(c for c in node.children if c.name == "other_fs")
    assert other_node.files == 0
    assert other_node.size == 0

    # cross_mounts=True must descend and count the file normally.
    node2, _events2 = scan_tree(root, ScanOptions(cross_mounts=True))
    other_node2 = next(c for c in node2.children if c.name == "other_fs")
    assert other_node2.files == 1
    assert other_node2.size == 999


def test_event_order_ids_and_parents(fixture_tree: Path) -> None:
    root = fixture_tree
    _node, events = scan_tree(root)
    assert isinstance(events[0], DirStarted)
    assert events[0].parent_id is None
    assert events[0].flags & ROOT
    # root DirDone must be the second-to-last event, immediately before Finished
    assert isinstance(events[-1], Finished)
    assert isinstance(events[-2], DirDone)
    assert events[-2].id == events[0].id

    started_ids = [e.id for e in events if isinstance(e, DirStarted)]
    assert len(started_ids) == len(set(started_ids))  # unique
    seen: set[int] = set()
    for e in events:
        if isinstance(e, DirStarted):
            if e.parent_id is not None:
                assert e.parent_id in seen
            seen.add(e.id)


def test_progress_and_finished_counts(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    for i in range(50):
        (root / f"f{i}.txt").write_text("x")
    opts = ScanOptions(batch_size=10, progress_interval=999.0)
    _node, events = scan_tree(root, opts)
    progress_events = [e for e in events if isinstance(e, Progress)]
    assert len(progress_events) >= 4  # 50 entries / batch_size 10
    finished = next(e for e in events if isinstance(e, Finished))
    assert finished.entries == 50
    assert finished.cancelled is False


def test_cancel_marks_partial_and_stops(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    for i in range(5):
        d = root / f"d{i}"
        d.mkdir()
        for j in range(20):
            (d / f"f{j}.txt").write_text("x" * j)

    cancel = threading.Event()
    seen_dirstarted = 0
    events: list[object] = []

    def emit(event: object) -> None:
        nonlocal seen_dirstarted
        events.append(event)
        if isinstance(event, DirStarted):
            seen_dirstarted += 1
            if seen_dirstarted == 3:
                cancel.set()

    Scanner().scan(str(root), ScanOptions(), emit, cancel=cancel)
    finished = next(e for e in events if isinstance(e, Finished))
    assert finished.cancelled is True
    dir_dones = [e for e in events if isinstance(e, DirDone)]
    assert any(e.flags & PARTIAL for e in dir_dones)


def test_scanthread_runs_and_matches(fixture_tree: Path) -> None:
    root = fixture_tree
    q: queue.SimpleQueue[object] = queue.SimpleQueue()
    thread = ScanThread(str(root), ScanOptions(), q)
    thread.start()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert thread.error is None
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    assert isinstance(events[-1], Finished)
    assert thread.root_node is not None
    exp_size, exp_alloc, exp_files = independent_walk_totals(root)
    assert thread.root_node.size == exp_size
    assert thread.root_node.alloc == exp_alloc
    assert thread.root_node.files == exp_files


def test_scanthread_cancel_and_pause_methods(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "f.txt").write_text("x")
    q: queue.SimpleQueue[object] = queue.SimpleQueue()
    thread = ScanThread(str(root), ScanOptions(), q)
    assert thread.is_paused() is False
    thread.pause()
    assert thread.is_paused() is True
    thread.resume()
    assert thread.is_paused() is False
    thread.cancel()  # just verify it doesn't raise
    thread.start()
    thread.join(timeout=10)


def test_scanthread_reports_error_on_missing_root() -> None:
    q: queue.SimpleQueue[object] = queue.SimpleQueue()
    thread = ScanThread("/no/such/path/hopefully", ScanOptions(), q)
    thread.start()
    thread.join(timeout=10)
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    assert isinstance(events[-1], Finished)
    assert events[-1].cancelled is False
    assert any(isinstance(e, ScanError) for e in events)
    assert thread.error is not None


# ---------------------------------------------------------------------------
# scanner_cli subprocess tests
# ---------------------------------------------------------------------------


def test_cli_json_module_invocation(fixture_tree: Path) -> None:
    root = fixture_tree
    result = subprocess.run(
        [sys.executable, "-m", "lindrivespace.core.scanner_cli", "--json", str(root)],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(SRC)},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    lines = [line_ for line_ in result.stdout.splitlines() if line_]
    events = [json.loads(line_) for line_ in lines]
    assert events, "no events produced"
    assert events[0]["event"] == "DirStarted"
    assert events[-1]["event"] == "Finished"
    dir_done = [e for e in events if e["event"] == "DirDone"]
    assert dir_done
    assert isinstance(dir_done[0]["top_files"], list)


def test_cli_as_plain_script_with_empty_pythonpath(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "f.txt").write_text("hello")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, str(CLI), "--json", str(root)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    lines = [line_ for line_ in result.stdout.splitlines() if line_]
    events = [json.loads(line_) for line_ in lines]
    assert events[0]["event"] == "DirStarted"
    assert events[-1]["event"] == "Finished"


def test_cli_missing_root_exits_1() -> None:
    result = subprocess.run(
        [sys.executable, str(CLI), "/no/such/directory/at/all"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(SRC)},
        check=False,
    )
    assert result.returncode == 1


def test_top_min_bytes_keeps_small_files_out_of_the_ring(tmp_path: Path) -> None:
    from lindrivespace.core.options import ScanOptions
    from lindrivespace.core.scanner import Scanner

    d = tmp_path / "ring"
    d.mkdir()
    (d / "big.bin").write_bytes(b"x" * 200_000)
    (d / "small.txt").write_bytes(b"y" * 10_000)
    root = Scanner().scan(str(d), ScanOptions(top_min_bytes=65_536), lambda e: None)
    assert root.files == 2 and root.size == 210_000  # totals count everything
    assert [t.name for t in root.top_files] == ["big.bin"]
    root_all = Scanner().scan(str(d), ScanOptions(top_min_bytes=0), lambda e: None)
    assert {t.name for t in root_all.top_files} == {"big.bin", "small.txt"}
