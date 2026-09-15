from __future__ import annotations

from pathlib import Path

from lindrivespace.core.fsnode import DENIED, FsNode
from lindrivespace.core.snapshot import (
    default_snapshot_dir,
    diff_snapshots,
    list_snapshots,
    load_snapshot,
    save_snapshot,
    snapshot_filename,
)


def _build_three_level_tree() -> FsNode:
    root = FsNode(1, "/home/user", top_limit=3, mtime=100.0, flags=0)
    docs = FsNode(2, "docs", root, mtime=50.0)
    cache = FsNode(3, ".cache", root, mtime=60.0, flags=DENIED)
    photos = FsNode(4, "photos", docs, mtime=70.0)

    root.add_file(1000, 4096, 10.0, "readme.txt")
    docs.add_file(2000, 8192, 20.0, "report.pdf")
    docs.add_file(3000, 8192, 21.0, "notes.txt")
    docs.add_file(4000, 8192, 22.0, "extra.txt")  # ring is bounded to top_limit=3
    cache.add_file(500, 4096, 5.0, "tmp.bin")
    photos.add_file(6000, 12288, 30.0, "beach.jpg")

    for node in (photos, docs, cache, root):
        node.finalize()
    return root


def test_round_trip_preserves_fields(tmp_path: Path) -> None:
    root = _build_three_level_tree()
    path = tmp_path / "snap.json.gz"
    save_snapshot(root, path, meta={"note": "hello"})

    loaded, meta = load_snapshot(path)

    assert meta["note"] == "hello"
    assert meta["root_path"] == root.path()
    assert meta["entries"] == root.dirs + 1
    assert "saved_at" in meta

    assert loaded.name == root.name
    assert loaded.size == root.size
    assert loaded.alloc == root.alloc
    assert loaded.files == root.files
    assert loaded.dirs == root.dirs
    assert loaded.mtime == root.mtime
    assert loaded.mtime_max == root.mtime_max
    assert loaded.flags == root.flags

    orig_by_name = {c.name: c for c in root.children}
    loaded_by_name = {c.name: c for c in loaded.children}
    assert set(orig_by_name) == set(loaded_by_name)

    orig_cache = orig_by_name[".cache"]
    loaded_cache = loaded_by_name[".cache"]
    assert loaded_cache.flags == orig_cache.flags
    assert loaded_cache.denied == orig_cache.denied

    orig_docs = orig_by_name["docs"]
    loaded_docs = loaded_by_name["docs"]
    assert {t.name for t in loaded_docs.top_files} == {t.name for t in orig_docs.top_files}
    assert [t for t in sorted(loaded_docs.top_files)] == [t for t in sorted(orig_docs.top_files)]

    orig_photos = next(c for c in orig_docs.children if c.name == "photos")
    loaded_photos = next(c for c in loaded_docs.children if c.name == "photos")
    assert loaded_photos.alloc == orig_photos.alloc
    assert [t.name for t in loaded_photos.top_files] == [t.name for t in orig_photos.top_files]

    # Fresh pre-order ids, starting at 1, no duplicates.
    ids = [n.id for n in loaded.walk()]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
    assert ids[0] == 1


def test_deep_chain_round_trip_without_recursion_error(tmp_path: Path) -> None:
    # A 5000-deep single-child chain (stresses JSON nesting depth), padded
    # with sibling leaves under the deepest node to reach ~20k total nodes
    # (stresses breadth without adding depth).
    depth = 5000
    root = FsNode(1, "/root", top_limit=1)
    cur = root
    next_id = 2
    for _ in range(depth - 1):
        cur = FsNode(next_id, f"d{next_id}", cur, mtime=float(next_id))
        next_id += 1
    chain_tail = cur
    assert chain_tail.depth() == depth - 1

    leaf_count = 0
    while next_id < 20_000:
        FsNode(next_id, f"leaf{next_id}", chain_tail, mtime=float(next_id))
        next_id += 1
        leaf_count += 1
    chain_tail.add_file(10, 10, 1.0, "leaf.txt")

    # Bottom-up finalize, iterative (matches FsNode.walk's own pre-order stack).
    for node in reversed(list(root.walk())):
        node.finalize()

    path = tmp_path / "deep.json.gz"
    save_snapshot(root, path)
    loaded, _meta = load_snapshot(path)

    # Walk the single-child spine without calling depth() per node (that
    # would be O(depth) each, i.e. quadratic over the whole chain).
    hops = 0
    node = loaded
    while len(node.children) == 1:
        node = node.children[0]
        hops += 1
    assert hops == depth - 1
    assert len(node.children) == leaf_count

    assert loaded.alloc == root.alloc
    assert loaded.name == root.name


def test_snapshot_filename_and_default_dir() -> None:
    name = snapshot_filename("/home/user", when=None)
    assert name.startswith("home-user-")
    assert name.endswith(".json.gz")

    from datetime import datetime

    fixed = datetime(2026, 9, 14, 18, 41, 5)
    assert snapshot_filename("/home", when=fixed) == "home-2026-09-14T18-41-05.json.gz"
    assert snapshot_filename("/", when=fixed) == "root-2026-09-14T18-41-05.json.gz"

    d = default_snapshot_dir()
    assert d.name == "scans"


def test_list_snapshots(tmp_path: Path) -> None:
    root_a = _build_three_level_tree()
    dir_ = tmp_path / "scans"
    path_a = dir_ / "a.json.gz"
    save_snapshot(root_a, path_a, meta={"tag": "a"})

    root_b = FsNode(1, "/other", top_limit=1)
    root_b.add_file(1, 1, 1.0, "x")
    root_b.finalize()
    path_b = dir_ / "b.json.gz"
    save_snapshot(root_b, path_b, meta={"tag": "b"})

    metas = list_snapshots(dir_)
    assert len(metas) == 2
    paths = {m.path for m in metas}
    assert paths == {path_a, path_b}
    for m in metas:
        assert m.entries > 0
        assert m.saved_at

    assert list_snapshots(tmp_path / "does-not-exist") == []


def test_diff_snapshots_grew_shrank_new_deleted() -> None:
    a = FsNode(1, "/root", top_limit=1)
    a_keep = FsNode(2, "keep", a)
    a_shrink = FsNode(3, "shrink", a)
    a_delete = FsNode(4, "deleted-dir", a)
    a_keep.add_file(1, 5_000_000, 1.0, "f")
    a_shrink.add_file(1, 10_000_000, 1.0, "f")
    a_delete.add_file(1, 8_000_000, 1.0, "f")
    for n in (a_keep, a_shrink, a_delete, a):
        n.finalize()

    b = FsNode(1, "/root", top_limit=1)
    b_keep = FsNode(2, "keep", b)
    b_shrink = FsNode(3, "shrink", b)
    b_new = FsNode(4, "new-dir", b)
    b_keep.add_file(1, 5_000_100, 1.0, "f")  # tiny change, below min_delta
    b_shrink.add_file(1, 2_000_000, 1.0, "f")  # shrank by 8,000,000
    b_new.add_file(1, 9_000_000, 1.0, "f")
    for n in (b_keep, b_shrink, b_new, b):
        n.finalize()

    entries = diff_snapshots(a, b, min_delta=1_000_000)
    by_path = {e.path: e for e in entries}

    assert "keep" not in by_path  # below min_delta, filtered out
    assert by_path["shrink"].kind == "shrank"
    assert by_path["shrink"].before == 10_000_000
    assert by_path["shrink"].after == 2_000_000
    assert by_path["shrink"].delta == -8_000_000

    assert by_path["deleted-dir"].kind == "deleted"
    assert by_path["deleted-dir"].before == 8_000_000
    assert by_path["deleted-dir"].after == 0
    assert by_path["deleted-dir"].delta == -8_000_000

    assert by_path["new-dir"].kind == "new"
    assert by_path["new-dir"].before == 0
    assert by_path["new-dir"].after == 9_000_000
    assert by_path["new-dir"].delta == 9_000_000

    # Sorted by |delta| descending.
    deltas = [abs(e.delta) for e in entries]
    assert deltas == sorted(deltas, reverse=True)


def test_diff_snapshots_respects_max_depth() -> None:
    a = FsNode(1, "/root", top_limit=1)
    a_sub = FsNode(2, "sub", a)
    a_deep = FsNode(3, "deep", a_sub)
    a_deep.add_file(1, 10_000_000, 1.0, "f")
    for n in (a_deep, a_sub, a):
        n.finalize()

    b = FsNode(1, "/root", top_limit=1)
    b_sub = FsNode(2, "sub", b)
    b_deep = FsNode(3, "deep", b_sub)
    b_deep.add_file(1, 1_000_000, 1.0, "f")
    for n in (b_deep, b_sub, b):
        n.finalize()

    entries_shallow = diff_snapshots(a, b, min_delta=1_000, max_depth=1)
    assert not any(e.path == "sub/deep" for e in entries_shallow)

    entries_deep = diff_snapshots(a, b, min_delta=1_000, max_depth=2)
    assert any(e.path == "sub/deep" for e in entries_deep)


def test_list_snapshots_reads_only_the_header(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from lindrivespace.core import snapshot as snap

    root = _build_three_level_tree()
    target = tmp_path / "a.json.gz"
    save_snapshot(root, target)
    calls: list[str] = []
    real = snap._parse_json_text

    def spy(text: str):  # type: ignore[no-untyped-def]
        calls.append("full")
        return real(text)

    monkeypatch.setattr(snap, "_parse_json_text", spy)
    metas = list_snapshots(tmp_path)
    assert calls == []  # header path only
    assert metas[0].alloc == root.alloc and metas[0].root_path == root.path()
    assert metas[0].entries == root.dirs + 1


def test_list_snapshots_falls_back_for_files_without_alloc_in_meta(tmp_path: Path) -> None:
    import gzip
    import json

    root = _build_three_level_tree()
    target = tmp_path / "old.json.gz"
    save_snapshot(root, target)
    with gzip.open(target, "rt", encoding="utf-8") as fh:
        data = json.load(fh)
    del data["meta"]["alloc"]
    with gzip.open(target, "wt", encoding="utf-8") as fh:
        json.dump(data, fh)  # json.dump spacing differs from the writer's: header regex fails
    metas = list_snapshots(tmp_path)
    assert metas[0].alloc == root.alloc
