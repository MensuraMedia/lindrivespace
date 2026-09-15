"""Headless tests for lindrivespace.services.export (no GTK)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from lindrivespace.core.fsnode import FsNode
from lindrivespace.services.export import export_csv, export_json, export_top_files, flatten


def _build_tree() -> FsNode:
    """A 3-level tree: root -> {dirA, dirB}; dirA -> {subA}. Finalized bottom-up."""
    root = FsNode(1, "root", None, mtime=1_700_000_000.0)
    dir_a = FsNode(2, "dirA", root, mtime=1_700_000_100.0)
    dir_a.add_file(500_000, 500_000, 1_700_000_050.0, "fileA1.bin")
    dir_a.add_file(200_000, 200_000, 1_700_000_060.0, "fileA2.bin")
    sub_a = FsNode(3, "subA", dir_a, mtime=1_700_000_200.0)
    sub_a.add_file(100_000, 100_000, 1_700_000_150.0, "fileSub.bin")
    dir_b = FsNode(4, "dirB", root, mtime=1_700_000_300.0)
    dir_b.add_file(900_000, 900_000, 1_700_000_250.0, "fileB1.bin")

    # children before parents -- no recursion needed for a tree this shallow,
    # but the order matters: finalize() assumes child totals are already final.
    sub_a.finalize()
    dir_a.finalize()
    dir_b.finalize()
    root.finalize()
    return root


def test_flatten_visits_every_directory_with_depth_and_relative_path() -> None:
    root = _build_tree()
    by_name = {n.name: (d, r) for d, r, n in flatten(root, None)}
    assert by_name["root"] == (0, ".")
    assert by_name["dirA"] == (1, "dirA")
    assert by_name["dirB"] == (1, "dirB")
    assert by_name["subA"] == (2, "dirA/subA")


def test_export_csv_row_count_and_percent(tmp_path: Path) -> None:
    root = _build_tree()
    out = tmp_path / "tree.csv"
    count = export_csv(root, out)
    assert count == 4

    with out.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 4
    by_name = {r["name"]: r for r in rows}

    # dirA holds fileA1 + fileA2 directly, plus subA's fileSub in its subtree total.
    assert int(by_name["dirA"]["alloc"]) == 500_000 + 200_000 + 100_000
    expected_pct = round((800_000 * 100.0) / root.alloc, 2)
    assert float(by_name["dirA"]["percent_of_parent"]) == expected_pct

    assert by_name["root"]["path"] == "."
    assert by_name["dirA"]["path"] == "dirA"
    assert by_name["subA"]["path"] == "dirA/subA"
    assert by_name["root"]["depth"] == "0"
    assert by_name["subA"]["depth"] == "2"


def test_export_csv_respects_max_depth(tmp_path: Path) -> None:
    root = _build_tree()
    out = tmp_path / "shallow.csv"
    count = export_csv(root, out, max_depth=1)
    assert count == 3  # root, dirA, dirB -- subA (depth 2) is excluded
    with out.open(newline="", encoding="utf-8") as fh:
        names = [r["name"] for r in csv.DictReader(fh)]
    assert "subA" not in names


def test_export_json_nested_structure(tmp_path: Path) -> None:
    root = _build_tree()
    out = tmp_path / "tree.json"
    count = export_json(root, out)
    assert count == 4

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["name"] == "root"
    assert data["path"] == "."
    assert {c["name"] for c in data["children"]} == {"dirA", "dirB"}

    dir_a = next(c for c in data["children"] if c["name"] == "dirA")
    assert dir_a["path"] == "dirA"
    assert [c["name"] for c in dir_a["children"]] == ["subA"]
    assert dir_a["children"][0]["path"] == "dirA/subA"
    assert dir_a["children"][0]["depth"] == 2


def test_export_json_respects_max_depth(tmp_path: Path) -> None:
    root = _build_tree()
    out = tmp_path / "shallow.json"
    count = export_json(root, out, max_depth=1)
    assert count == 3
    data = json.loads(out.read_text(encoding="utf-8"))
    for child in data["children"]:
        assert child["children"] == []


def test_export_json_deep_chain_does_not_recurse(tmp_path: Path) -> None:
    depth = 5000
    nodes = [FsNode(1, "root", None, mtime=1.0)]
    for i in range(1, depth):
        nodes.append(FsNode(i + 1, f"d{i}", nodes[-1], mtime=1.0))
    nodes[-1].add_file(10, 10, 1.0, "leaf.bin")
    for node in reversed(nodes):  # children before parents, no recursion
        node.finalize()

    out = tmp_path / "deep.json"
    count = export_json(nodes[0], out)  # must not raise RecursionError
    assert count == depth

    csv_out = tmp_path / "deep.csv"
    csv_count = export_csv(nodes[0], csv_out)
    assert csv_count == depth


def test_export_top_files_sorted_and_limited(tmp_path: Path) -> None:
    root = FsNode(1, "root", None, mtime=1.0, top_limit=10)
    for alloc, name in (
        (50, "a.bin"),
        (500, "b.bin"),
        (300, "c.bin"),
        (10, "d.bin"),
        (900, "e.bin"),
    ):
        root.add_file(alloc, alloc, 1.0, name)
    root.finalize()

    out = tmp_path / "top.csv"
    count = export_top_files(root, out, limit=3)
    assert count == 3

    with out.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    allocs = [int(r["alloc"]) for r in rows]
    assert allocs == [900, 500, 300]
    assert allocs == sorted(allocs, reverse=True)
    assert rows[0]["path"] == "e.bin"
