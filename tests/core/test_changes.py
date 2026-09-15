"""Folder + file change reports between two scan snapshots."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lindrivespace.core import changes
from lindrivespace.core.fsnode import FsNode
from lindrivespace.core.snapshot import save_snapshot, snapshot_filename

MB = 1_000_000


def _tree(*, big_video: int, with_new_dir: bool, keep_old: bool) -> FsNode:
    root = FsNode(1, "/data", top_limit=5)
    media = FsNode(2, "media", root)
    media.add_file(big_video, big_video, 1.0, "movie.mkv")
    media.add_file(2 * MB, 2 * MB, 1.0, "song.flac")
    docs = FsNode(3, "docs", root)
    docs.add_file(1 * MB, 1 * MB, 1.0, "notes.txt")
    if keep_old:
        old = FsNode(4, "old", root)
        old.add_file(30 * MB, 30 * MB, 1.0, "backup.tar")
        old.finalize()
    if with_new_dir:
        fresh = FsNode(5, "downloads", root)
        fresh.add_file(50 * MB, 50 * MB, 1.0, "iso.img")
        fresh.finalize()
    for n in (media, docs, root):
        n.finalize()
    return root


def test_diff_trees_reports_folders_and_files() -> None:
    a = _tree(big_video=100 * MB, with_new_dir=False, keep_old=True)
    b = _tree(big_video=160 * MB, with_new_dir=True, keep_old=False)
    items = changes.diff_trees(a, b, min_delta=MB)
    by_path = {(i.path, i.is_file): i for i in items}

    assert by_path[("media", False)].kind == "grew"
    assert by_path[("media", False)].delta == 60 * MB
    assert by_path[("media/movie.mkv", True)].kind == "grew"
    assert by_path[("downloads", False)].kind == "new"
    assert by_path[("old", False)].kind == "deleted"
    assert by_path[("old", False)].delta == -30 * MB
    # unchanged things stay out
    assert ("docs", False) not in by_path
    assert ("media/song.flac", True) not in by_path
    # largest absolute change first
    assert abs(items[0].delta) >= abs(items[-1].delta)


def test_diff_trees_new_and_deleted_files_inside_matched_dirs() -> None:
    a = FsNode(1, "/x", top_limit=5)
    a.add_file(5 * MB, 5 * MB, 1.0, "gone.bin")
    a.finalize()
    b = FsNode(1, "/x", top_limit=5)
    b.add_file(7 * MB, 7 * MB, 1.0, "fresh.bin")
    b.finalize()
    kinds = {(i.path, i.kind) for i in changes.diff_trees(a, b, min_delta=MB)}
    assert ("gone.bin", "deleted") in kinds
    assert ("fresh.bin", "new") in kinds


def _save(directory: Path, root: FsNode, when: datetime) -> Path:
    target = directory / snapshot_filename(root.path(), when)
    save_snapshot(root, target)
    # save_snapshot stamps saved_at=now; rewrite the meta stamp for the test.
    import gzip
    import json

    with gzip.open(target, "rt", encoding="utf-8") as fh:
        data = json.load(fh)
    data["meta"]["saved_at"] = when.isoformat()
    with gzip.open(target, "wt", encoding="utf-8") as fh:
        json.dump(data, fh)
    return target


def test_pick_snapshots_prefers_oldest_inside_period(tmp_path: Path) -> None:
    now_dt = datetime.now(timezone.utc)
    now = now_dt.timestamp()
    for days_ago, video in ((20, 10), (5, 20), (2, 30), (0, 40)):
        _save(
            tmp_path,
            _tree(big_video=video * MB, with_new_dir=False, keep_old=False),
            now_dt - timedelta(days=days_ago),
        )
    from lindrivespace.core.snapshot import list_snapshots

    metas = list_snapshots(tmp_path)
    picked = changes.pick_snapshots(metas, "/data", "week", now=now)
    assert picked is not None
    older, newest = picked
    assert "day" not in older.saved_at  # sanity: iso stamp
    assert changes._saved_ts(older) == max(
        changes._saved_ts(m) for m in metas if changes._saved_ts(m) <= now - 5 * 86400 + 60
    )
    assert changes._saved_ts(newest) == max(changes._saved_ts(m) for m in metas)

    picked_all = changes.pick_snapshots(metas, "all", "all", now=now)
    assert picked_all is None  # wrong root path -> nothing
    picked_all = changes.pick_snapshots(metas, "/data", "all", now=now)
    assert picked_all is not None and changes._saved_ts(picked_all[0]) == min(
        changes._saved_ts(m) for m in metas
    )


def test_pick_snapshots_falls_back_to_previous_run_when_period_too_short(
    tmp_path: Path,
) -> None:
    now_dt = datetime.now(timezone.utc)
    _save(
        tmp_path,
        _tree(big_video=MB, with_new_dir=False, keep_old=False),
        now_dt - timedelta(days=9),
    )
    _save(tmp_path, _tree(big_video=MB, with_new_dir=False, keep_old=False), now_dt)
    from lindrivespace.core.snapshot import list_snapshots

    picked = changes.pick_snapshots(
        list_snapshots(tmp_path), "/data", "day", now=now_dt.timestamp()
    )
    assert picked is not None and picked[0] is not picked[1]


def test_change_report_end_to_end(tmp_path: Path) -> None:
    now_dt = datetime.now(timezone.utc)
    _save(
        tmp_path,
        _tree(big_video=100 * MB, with_new_dir=False, keep_old=True),
        now_dt - timedelta(days=1),
    )
    _save(tmp_path, _tree(big_video=160 * MB, with_new_dir=True, keep_old=False), now_dt)
    assert changes.snapshot_count(tmp_path, "/data") == 2
    report = changes.change_report(tmp_path, "/data", "week", now=time.time(), min_delta=MB)
    assert report is not None
    assert report.delta == report.after_alloc - report.before_alloc == 80 * MB
    paths = {i.path for i in report.items}
    assert {"media", "media/movie.mkv", "downloads", "old"} <= paths
    assert changes.format_saved_at(report.after_at).count("-") == 2
    assert changes.change_report(tmp_path, "/nowhere", "week") is None
