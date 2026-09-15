from __future__ import annotations

from lindrivespace.core.fsnode import DENIED, FsNode
from lindrivespace.core.options import ScanOptions


def build_tree() -> FsNode:
    root = FsNode(1, "/home", top_limit=2)
    user = FsNode(2, "user", root, mtime=10.0)
    cache = FsNode(3, ".cache", user, mtime=20.0)
    cache.add_file(100, 4096, 30.0, "a")
    cache.add_file(50, 4096, 5.0, "b")
    cache.add_file(500, 8192, 1.0, "c")
    user.add_file(10, 4096, 2.0, "d")
    docker = FsNode(4, "docker", root, flags=DENIED)
    for node in (cache, user, docker, root):
        node.finalize()
    return root


def test_totals_and_counts() -> None:
    root = build_tree()
    assert root.size == 660
    assert root.alloc == 4096 * 3 + 8192
    assert root.files == 4
    assert root.dirs == 3  # user, .cache, docker
    assert root.mtime_max == 30.0


def test_children_sorted_largest_first_and_percent() -> None:
    root = build_tree()
    assert [c.name for c in root.children] == ["user", "docker"]
    user = root.children[0]
    assert user.children[0].name == ".cache"
    pct = user.children[0].percent_of_parent()
    assert pct == 80.0  # 16384 / 20480
    assert root.percent_of_parent() == 100.0


def test_top_files_ring_is_bounded() -> None:
    root = build_tree()
    cache = root.find(3)
    assert cache is not None
    names = [t.name for t in cache.top_files]
    assert names == ["c", "a"] or names == ["c", "b"]  # a and b tie on alloc
    assert len(cache.top_files) == 2
    assert cache.top_limit == 2  # inherited from the root


def test_path_and_depth() -> None:
    root = build_tree()
    cache = root.find(3)
    assert cache is not None
    assert cache.path() == "/home/user/.cache"
    assert cache.depth() == 2
    assert FsNode(9, "/").path() == "/"
    assert FsNode(10, "x", FsNode(11, "/")).path() == "/x"


def test_denied_flag() -> None:
    root = build_tree()
    docker = root.find(4)
    assert docker is not None and docker.denied


def test_walk_is_preorder() -> None:
    root = build_tree()
    assert [n.id for n in root.walk()] == [1, 2, 3, 4]


def test_exclusion_rules() -> None:
    opts = ScanOptions()
    assert opts.is_excluded("/proc")
    assert opts.is_excluded("/proc/1")
    assert not opts.is_excluded("/process")
    assert not opts.is_excluded("/home")
