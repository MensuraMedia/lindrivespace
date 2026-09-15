"""CSV / JSON export of a scanned tree, and a top-files CSV.

GTK-free (stdlib + ``core`` only) so it can be unit-tested headlessly and
reused by a future CLI. Every traversal is iterative (an explicit stack, no
Python recursion) since a directory chain can be thousands of levels deep --
see ``core/snapshot.py``'s own writer for the same concern and the benchmark
behind it (recursive ``json.dump``/generator-based encoders blow the stack or
go quadratic well before depth 5000).
"""

from __future__ import annotations

import csv
import heapq
import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from lindrivespace.core.fsnode import FsNode

_CSV_FIELDS = (
    "depth",
    "path",
    "name",
    "size",
    "alloc",
    "files",
    "dirs",
    "percent_of_parent",
    "mtime_max",
    "flags",
)


def _iso(ts: float) -> str:
    """A unix timestamp as a local ISO 8601 string, or "" for ``ts <= 0``."""
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def flatten(root: FsNode, max_depth: int | None) -> Iterator[tuple[int, str, FsNode]]:
    """Pre-order ``(depth, relative_path, node)`` triples, iterative.

    ``depth`` 0 is ``root`` itself (relative path ``"."``); descendants use
    ``/``-joined relative paths. When ``max_depth`` is given, nodes deeper
    than it are omitted entirely (their subtrees are not descended into).
    """
    stack: list[tuple[FsNode, int, str]] = [(root, 0, ".")]
    while stack:
        node, depth, rel = stack.pop()
        yield depth, rel, node
        if max_depth is not None and depth >= max_depth:
            continue
        for child in reversed(node.children):
            child_rel = child.name if rel == "." else f"{rel}/{child.name}"
            stack.append((child, depth + 1, child_rel))


def export_csv(
    root: FsNode,
    path: Path,
    *,
    max_depth: int | None = None,
    allocated_primary: bool = True,
) -> int:
    """Write a flattened CSV table of ``root``'s subtree; returns the row count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(_CSV_FIELDS)
        for depth, rel, node in flatten(root, max_depth):
            writer.writerow(
                (
                    depth,
                    rel,
                    node.name,
                    node.size,
                    node.alloc,
                    node.files,
                    node.dirs,
                    f"{node.percent_of_parent(allocated_primary):.2f}",
                    _iso(node.mtime_max),
                    node.flags,
                )
            )
            count += 1
    return count


def _emit_json_node(
    out: list[str], node: FsNode, rel: str, depth: int, allocated_primary: bool
) -> None:
    out.append("{")
    out.append(f'"depth":{depth},')
    out.append('"path":')
    out.append(json.dumps(rel))
    out.append(',"name":')
    out.append(json.dumps(node.name))
    out.append(f',"size":{int(node.size)}')
    out.append(f',"alloc":{int(node.alloc)}')
    out.append(f',"files":{int(node.files)}')
    out.append(f',"dirs":{int(node.dirs)}')
    out.append(f',"percent_of_parent":{node.percent_of_parent(allocated_primary):.4f}')
    out.append(',"mtime_max":')
    out.append(json.dumps(_iso(node.mtime_max)))
    out.append(f',"flags":{int(node.flags)}')
    out.append(',"children":[')


class _JFrame:
    """Mutable walk state for one open node while emitting its "children" array."""

    __slots__ = ("node", "rel", "depth", "child_iter", "started")

    def __init__(self, node: FsNode, rel: str, depth: int) -> None:
        self.node = node
        self.rel = rel
        self.depth = depth
        self.child_iter = iter(node.children)
        self.started = False


def export_json(root: FsNode, path: Path, *, max_depth: int | None = None) -> int:
    """Write a nested JSON tree of ``root``'s subtree; returns the node count.

    Never calls ``json.dump``/``json.dumps`` on the nested structure itself
    (only on individual scalar fields) and walks with an explicit stack, so a
    5000-deep directory chain exports in linear time with no recursion.
    """
    allocated_primary = True
    count = 0
    out: list[str] = []

    def within_depth(depth: int) -> bool:
        return max_depth is None or depth < max_depth

    _emit_json_node(out, root, ".", 0, allocated_primary)
    count += 1
    stack: list[_JFrame] = [_JFrame(root, ".", 0)]

    while stack:
        frame = stack[-1]
        child = next(frame.child_iter, None) if within_depth(frame.depth) else None
        if child is None:
            out.append("]}")
            stack.pop()
            continue
        out.append("," if frame.started else "")
        frame.started = True
        child_rel = child.name if frame.rel == "." else f"{frame.rel}/{child.name}"
        child_depth = frame.depth + 1
        _emit_json_node(out, child, child_rel, child_depth, allocated_primary)
        count += 1
        stack.append(_JFrame(child, child_rel, child_depth))

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write("".join(out))
    return count


def _iter_top_file_rows(root: FsNode) -> Iterator[tuple[str, int, int, float]]:
    for _depth, rel, node in flatten(root, None):
        for tf in node.top_files:
            file_rel = tf.name if rel == "." else f"{rel}/{tf.name}"
            yield file_rel, tf.size, tf.alloc, tf.mtime


def export_top_files(root: FsNode, path: Path, limit: int = 500) -> int:
    """CSV of the largest files across ``root``'s subtree, by allocated size.

    Gathered from each directory's bounded ``top_files`` ring (see
    ``FsNode.top_limit``): a directory with more files than its ring size
    undercounts silently, same caveat as ``core.classify.summarize_top_files``.
    """
    rows = heapq.nlargest(limit, _iter_top_file_rows(root), key=lambda r: r[2])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(("path", "size", "alloc", "mtime"))
        for file_rel, size, alloc, mtime in rows:
            writer.writerow((file_rel, size, alloc, _iso(mtime)))
    return len(rows)
