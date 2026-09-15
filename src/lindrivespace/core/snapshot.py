"""Save / load / diff scans (design doc §3.4, §16: gzip, not zstd).

On-disk format: gzip-compressed JSON, ``.json.gz``::

    {"version": 1, "meta": {...}, "root": {<node>}}

with each node serialised as::

    {"n": name, "s": size, "a": alloc, "f": files, "d": dirs, "m": mtime,
     "mm": mtime_max, "fl": flags, "t": [[alloc, size, mtime, name], ...],
     "c": [<child node>, ...]}

A directory chain can be thousands of levels deep (see
``tests/core/test_snapshot.py``'s 5000-deep chain), and the stdlib ``json``
module's encoder/decoder both recurse per nesting level -- with Python's
default recursion limit that raises ``RecursionError`` well before 5000
levels, regardless of how the Python object tree was built. So:

- **Writing** never calls ``json.dump``/``json.dumps`` on the nested tree.
  ``_node_tree_to_json`` walks it with an explicit stack and emits JSON text
  directly (each node contributes a handful of ``json.dumps`` calls for its
  own *scalar* fields only, which is not nesting-sensitive).
- **Reading** first tries the fast C-accelerated ``json.loads``; only if that
  raises ``RecursionError`` (an unusually deep tree) does it fall back to the
  pure-Python decoder with a temporarily raised ``sys.recursionlimit``, which
  is slower but has no comparable native-stack ceiling for our tree depths.
- Reconstructing :class:`FsNode` objects from the parsed dict tree is done
  with an explicit stack too (mirrors :meth:`FsNode.walk`'s own iterative
  pre-order), never Python recursion.

Values are stored fully finalised (whole-subtree totals), so loading sets
fields directly and never calls :meth:`FsNode.finalize`.
"""

from __future__ import annotations

import gzip
import heapq
import json
import json.scanner
import os
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from typing import Any, Literal

from lindrivespace.core.fsnode import FsNode, TopFile

_FORMAT_VERSION = 1

# ---------------------------------------------------------------------------
# Deep-safe JSON helpers
# ---------------------------------------------------------------------------


def _parse_json_text(text: str) -> Any:
    """Parse `text` as JSON, falling back to a recursion-limit-safe path.

    The default (C-accelerated) decoder is tried first since it is much
    faster for the large, mostly-wide trees a real scan produces; it is only
    replaced for pathologically deep documents.
    """
    try:
        return json.loads(text)
    except RecursionError:
        return _parse_json_text_deep(text)


def _parse_json_text_deep(text: str) -> Any:
    old_limit = sys.getrecursionlimit()
    # Empirically safe and fast well past any real filesystem depth (path
    # length limits keep directory nesting to a few hundred/thousand levels
    # in practice); see the change manifest for the benchmark this is based on.
    sys.setrecursionlimit(max(old_limit, 100_000))
    try:
        # Both attributes are real at runtime but missing from typeshed's
        # json stubs, so mypy needs to be told explicitly.
        decoder = json.JSONDecoder()
        decoder.scan_once = json.scanner.py_make_scanner(decoder)  # type: ignore[attr-defined]
        return decoder.decode(text)
    finally:
        sys.setrecursionlimit(old_limit)


class _Frame:
    """Mutable walk state for one open node while emitting its "c" array."""

    __slots__ = ("node", "child_iter", "started")

    def __init__(self, node: FsNode) -> None:
        self.node = node
        self.child_iter: Iterator[FsNode] = iter(node.children)
        self.started = False


def _emit_node_open(n: FsNode, out: list[str]) -> None:
    out.append('{"n":')
    out.append(json.dumps(n.name))
    out.append(',"s":')
    out.append(str(int(n.size)))
    out.append(',"a":')
    out.append(str(int(n.alloc)))
    out.append(',"f":')
    out.append(str(int(n.files)))
    out.append(',"d":')
    out.append(str(int(n.dirs)))
    out.append(',"m":')
    out.append(json.dumps(n.mtime))
    out.append(',"mm":')
    out.append(json.dumps(n.mtime_max))
    out.append(',"fl":')
    out.append(str(int(n.flags)))
    out.append(',"t":[')
    for idx, tf in enumerate(n.top_files):
        if idx:
            out.append(",")
        out.append("[")
        out.append(json.dumps(tf.alloc))
        out.append(",")
        out.append(json.dumps(tf.size))
        out.append(",")
        out.append(json.dumps(tf.mtime))
        out.append(",")
        out.append(json.dumps(tf.name))
        out.append("]")
    out.append('],"c":[')


def _node_tree_to_json(root: FsNode) -> str:
    """Serialise `root`'s subtree to JSON text with an explicit stack."""
    out: list[str] = []
    _emit_node_open(root, out)
    stack: list[_Frame] = [_Frame(root)]

    while stack:
        frame = stack[-1]
        child = next(frame.child_iter, None)
        if child is None:
            out.append("]}")
            stack.pop()
            continue
        out.append("," if frame.started else "")
        frame.started = True
        _emit_node_open(child, out)
        stack.append(_Frame(child))

    return "".join(out)


def _restore_top_files(node: FsNode, entries: list[TopFile]) -> None:
    """Push `entries` into `node`'s (private) top-files ring.

    `node.top_limit` is sized to `len(entries)` by the caller, so every push
    lands in the ring with no eviction -- the saved set is reproduced exactly.
    """
    node._top = []
    for entry in entries:
        heapq.heappush(node._top, entry)


def _build_node(data: dict[str, Any], parent: FsNode | None, node_id: int) -> FsNode:
    top_entries = [TopFile(alloc=t[0], size=t[1], mtime=t[2], name=t[3]) for t in data.get("t", ())]
    node = FsNode(
        node_id,
        data["n"],
        parent,
        mtime=data["m"],
        flags=data["fl"],
        top_limit=len(top_entries),
    )
    node.size = data["s"]
    node.alloc = data["a"]
    node.files = data["f"]
    node.dirs = data["d"]
    node.mtime_max = data["mm"]
    _restore_top_files(node, top_entries)
    node._finalized = True
    return node


def _dict_to_node(root_data: dict[str, Any]) -> FsNode:
    """Rebuild an :class:`FsNode` tree from a parsed node dict, iteratively.

    Ids are assigned fresh in pre-order, matching :meth:`FsNode.walk`.
    """
    ids = count(1)
    root_node = _build_node(root_data, None, next(ids))
    # (child_data, already-built parent) pairs; push reversed so popping
    # restores the original left-to-right child order (same trick FsNode.walk
    # uses internally).
    stack: list[tuple[dict[str, Any], FsNode]] = [
        (child_data, root_node) for child_data in reversed(root_data.get("c", ()))
    ]
    while stack:
        data, parent = stack.pop()
        node = _build_node(data, parent, next(ids))
        for child_data in reversed(data.get("c", ())):
            stack.append((child_data, node))
    return root_node


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def save_snapshot(root: FsNode, path: Path, meta: dict[str, Any] | None = None) -> Path:
    """Write `root`'s subtree to `path` as gzip-compressed JSON.

    `meta` is merged with ``saved_at`` (ISO timestamp), ``root_path`` and
    ``entries`` (total directory count, including `root` itself).
    """
    full_meta: dict[str, Any] = dict(meta or {})
    full_meta["saved_at"] = datetime.now(timezone.utc).isoformat()
    full_meta["root_path"] = root.path()
    full_meta["entries"] = root.dirs + 1

    meta_json = json.dumps(full_meta, sort_keys=True)
    root_json = _node_tree_to_json(root)
    content = f'{{"version": {_FORMAT_VERSION}, "meta": {meta_json}, "root": {root_json}}}'

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        fh.write(content)
    os.replace(tmp, path)
    return path


def load_snapshot(path: Path) -> tuple[FsNode, dict[str, Any]]:
    """Read a snapshot written by :func:`save_snapshot`.

    Returns the reconstructed root :class:`FsNode` (with fresh, freshly
    assigned pre-order ids) and the stored meta dict.
    """
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        text = fh.read()
    data = _parse_json_text(text)
    if not isinstance(data, dict) or data.get("version") != _FORMAT_VERSION:
        raise ValueError(f"unsupported snapshot format in {path}")
    root = _dict_to_node(data["root"])
    meta = dict(data.get("meta", {}))
    return root, meta


def default_snapshot_dir() -> Path:
    """Where snapshots live by default: ``<cache_dir>/scans``.

    Mirrors :func:`lindrivespace.config.settings.cache_dir` (``$XDG_CACHE_HOME``
    or ``~/.cache``) without importing it: `core/` stays a leaf package and
    `mypy --strict` stays happy following that module's own imports.
    """
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return Path(base) / "lindrivespace" / "scans"


def _slugify(path: str) -> str:
    trimmed = path.strip("/")
    if not trimmed:
        return "root"
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", trimmed).strip("-").lower()
    return slug or "root"


def snapshot_filename(root_path: str, when: datetime | None = None) -> str:
    """A filename like ``home-2026-09-14T18-41-05.json.gz``."""
    ts = when or datetime.now()
    stamp = ts.strftime("%Y-%m-%dT%H-%M-%S")
    return f"{_slugify(root_path)}-{stamp}.json.gz"


@dataclass(frozen=True, slots=True)
class SnapshotMeta:
    """Cheaply-read metadata about one saved snapshot, for a picker list."""

    path: Path
    root_path: str
    saved_at: str
    entries: int
    alloc: int


def list_snapshots(directory: Path) -> list[SnapshotMeta]:
    """List snapshots under `directory`, newest first.

    Reads each file's meta by parsing the whole (small, compressed) JSON
    document once -- acceptable for v1 (see the design doc). Unreadable or
    malformed files are skipped.
    """
    if not directory.exists():
        return []
    results: list[SnapshotMeta] = []
    for entry in sorted(directory.glob("*.json.gz")):
        try:
            with gzip.open(entry, "rt", encoding="utf-8") as fh:
                data = _parse_json_text(fh.read())
        except (OSError, ValueError) as exc:
            print(f"snapshot: skipping unreadable {entry}: {exc}", file=sys.stderr)
            continue
        if not isinstance(data, dict):
            continue
        meta = data.get("meta", {})
        root = data.get("root", {})
        if not isinstance(meta, dict) or not isinstance(root, dict):
            continue
        results.append(
            SnapshotMeta(
                path=entry,
                root_path=str(meta.get("root_path", "")),
                saved_at=str(meta.get("saved_at", "")),
                entries=int(meta.get("entries", 0)),
                alloc=int(root.get("a", 0)),
            )
        )
    results.sort(key=lambda m: m.saved_at, reverse=True)
    return results


@dataclass(frozen=True, slots=True)
class DiffEntry:
    """One changed directory between two snapshots, matched by relative path."""

    path: str
    kind: Literal["grew", "shrank", "new", "deleted"]
    before: int
    after: int
    delta: int


def diff_snapshots(
    a: FsNode, b: FsNode, *, min_delta: int = 1_000_000, max_depth: int = 6
) -> list[DiffEntry]:
    """Compare two snapshot roots, matching subdirectories by relative path.

    Direct children of the roots start at depth 1; recursion into matched
    pairs stops after `max_depth` levels. Entries are limited to
    ``|delta| >= min_delta`` and sorted by ``|delta|`` descending. Iterative
    (explicit stack): no Python recursion, so this scales to very deep trees.
    """
    entries: list[DiffEntry] = []
    # (node_in_a, node_in_b, relative_path, depth) -- at least one of the
    # nodes is not None.
    stack: list[tuple[FsNode | None, FsNode | None, str, int]] = []

    def seed(parent_a: FsNode | None, parent_b: FsNode | None, prefix: str, depth: int) -> None:
        by_name_a = {c.name: c for c in parent_a.children} if parent_a is not None else {}
        by_name_b = {c.name: c for c in parent_b.children} if parent_b is not None else {}
        for name in set(by_name_a) | set(by_name_b):
            rel = f"{prefix}/{name}" if prefix else name
            stack.append((by_name_a.get(name), by_name_b.get(name), rel, depth))

    seed(a, b, "", 1)

    while stack:
        node_a, node_b, rel_path, depth = stack.pop()
        alloc_a = node_a.alloc if node_a is not None else 0
        alloc_b = node_b.alloc if node_b is not None else 0
        delta = alloc_b - alloc_a

        if node_a is not None and node_b is not None:
            if delta != 0 and abs(delta) >= min_delta:
                kind: Literal["grew", "shrank"] = "grew" if delta > 0 else "shrank"
                entries.append(DiffEntry(rel_path, kind, alloc_a, alloc_b, delta))
            if depth < max_depth:
                seed(node_a, node_b, rel_path, depth + 1)
        elif node_a is not None:  # present only in a
            if alloc_a >= min_delta:
                entries.append(DiffEntry(rel_path, "deleted", alloc_a, 0, -alloc_a))
        elif node_b is not None:  # present only in b
            if alloc_b >= min_delta:
                entries.append(DiffEntry(rel_path, "new", 0, alloc_b, alloc_b))

    entries.sort(key=lambda e: abs(e.delta), reverse=True)
    return entries
