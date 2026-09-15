"""Where did the space go? -- folder *and file* level change reports.

The History page's "Change" tile shows *how much* a mount grew or shrank;
this module answers *where*. It compares two auto-saved scan snapshots of the
same root (``core.snapshot``): the newest one against the oldest one that
still falls inside the selected period. Directories are matched by relative
path (:func:`core.snapshot.diff_snapshots`); files come from each directory's
recorded largest files (``FsNode.top_files``), so the biggest new, grown,
shrunk and deleted files show up next to their folders.

Pure Python, no GTK (see ``tests/core/test_purity.py``).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from lindrivespace.core.fsnode import FsNode
from lindrivespace.core.snapshot import (
    SnapshotMeta,
    diff_snapshots,
    list_snapshots,
    load_snapshot,
)

Kind = Literal["grew", "shrank", "new", "deleted"]

# Period ids shared with ``core.history.PERIODS``: how far back the *older*
# snapshot may lie. ``None`` = no limit.
PERIOD_SPANS: dict[str, float | None] = {
    "day": 86_400.0,
    "week": 7 * 86_400.0,
    "month": 31 * 86_400.0,
    "year": 366 * 86_400.0,
    "all": None,
}


@dataclass(frozen=True, slots=True)
class ChangeItem:
    """One folder or file whose allocated size differs between two scans."""

    path: str  # relative to the scan root, "/"-separated
    kind: Kind
    before: int
    after: int
    delta: int
    is_file: bool


@dataclass(frozen=True, slots=True)
class ChangeReport:
    root_path: str
    before_at: str  # ISO timestamps from the snapshots' meta
    after_at: str
    before_alloc: int
    after_alloc: int
    items: list[ChangeItem]

    @property
    def delta(self) -> int:
        return self.after_alloc - self.before_alloc


def _file_changes(a: FsNode, b: FsNode, prefix: str, min_delta: int) -> list[ChangeItem]:
    """Compare the recorded largest files of one matched directory pair."""
    files_a = {f.name: f.alloc for f in a.top_files}
    files_b = {f.name: f.alloc for f in b.top_files}
    out: list[ChangeItem] = []
    for name in set(files_a) | set(files_b):
        before = files_a.get(name)
        after = files_b.get(name)
        rel = f"{prefix}/{name}" if prefix else name
        if before is not None and after is not None:
            delta = after - before
            if delta and abs(delta) >= min_delta:
                out.append(
                    ChangeItem(rel, "grew" if delta > 0 else "shrank", before, after, delta, True)
                )
        elif after is not None:
            if after >= min_delta:
                out.append(ChangeItem(rel, "new", 0, after, after, True))
        elif before is not None and before >= min_delta:
            out.append(ChangeItem(rel, "deleted", before, 0, -before, True))
    return out


def diff_trees(
    a: FsNode, b: FsNode, *, min_delta: int = 1_000_000, max_depth: int = 6
) -> list[ChangeItem]:
    """Folder changes (from :func:`diff_snapshots`) plus file changes inside every
    matched directory down to ``max_depth``, sorted by ``|delta|`` descending."""
    items: list[ChangeItem] = [
        ChangeItem(e.path, e.kind, e.before, e.after, e.delta, False)
        for e in diff_snapshots(a, b, min_delta=min_delta, max_depth=max_depth)
    ]
    # Walk matched directory pairs (root included) for file-level changes.
    stack: list[tuple[FsNode, FsNode, str, int]] = [(a, b, "", 0)]
    while stack:
        node_a, node_b, prefix, depth = stack.pop()
        items.extend(_file_changes(node_a, node_b, prefix, min_delta))
        if depth >= max_depth:
            continue
        by_name_b = {c.name: c for c in node_b.children}
        for child_a in node_a.children:
            child_b = by_name_b.get(child_a.name)
            if child_b is not None:
                rel = f"{prefix}/{child_a.name}" if prefix else child_a.name
                stack.append((child_a, child_b, rel, depth + 1))
    items.sort(key=lambda i: abs(i.delta), reverse=True)
    return items


def _saved_ts(meta: SnapshotMeta) -> float:
    try:
        return datetime.fromisoformat(meta.saved_at).timestamp()
    except ValueError:
        return 0.0


def pick_snapshots(
    metas: list[SnapshotMeta], root_path: str, period: str, now: float | None = None
) -> tuple[SnapshotMeta, SnapshotMeta] | None:
    """Choose (older, newest) snapshots of ``root_path`` for ``period``.

    ``newest`` is the most recent snapshot; ``older`` the oldest one taken
    within the period's span (so "Week" compares against the scan closest to
    seven days ago, not merely the previous run). Returns ``None`` when fewer
    than two distinct snapshots qualify.
    """
    now = time.time() if now is None else now
    mine = sorted((m for m in metas if m.root_path == root_path), key=_saved_ts)
    if len(mine) < 2:
        return None
    newest = mine[-1]
    span = PERIOD_SPANS.get(period)
    candidates = mine[:-1]
    if span is not None:
        inside = [m for m in candidates if _saved_ts(m) >= now - span]
        candidates = inside or candidates[-1:]  # nothing that old yet: use the previous run
    return (candidates[0], newest)


def change_report(
    directory: Path,
    root_path: str,
    period: str = "week",
    *,
    now: float | None = None,
    min_delta: int = 1_000_000,
    max_depth: int = 6,
) -> ChangeReport | None:
    """Load the two chosen snapshots under ``directory`` and diff them."""
    picked = pick_snapshots(list_snapshots(directory), root_path, period, now)
    if picked is None:
        return None
    older, newest = picked
    root_a, meta_a = load_snapshot(older.path)
    root_b, meta_b = load_snapshot(newest.path)
    items = diff_trees(root_a, root_b, min_delta=min_delta, max_depth=max_depth)
    return ChangeReport(
        root_path=root_path,
        before_at=str(meta_a.get("saved_at", older.saved_at)),
        after_at=str(meta_b.get("saved_at", newest.saved_at)),
        before_alloc=root_a.alloc,
        after_alloc=root_b.alloc,
        items=items,
    )


def snapshot_count(directory: Path, root_path: str) -> int:
    """How many snapshots of ``root_path`` exist (for the page's empty state)."""
    return sum(1 for m in list_snapshots(directory) if m.root_path == root_path)


def format_saved_at(iso: str) -> str:
    """``2026-09-15T06:42:56+00:00`` -> local ``2026-09-15 08:42``; passthrough if odd."""
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    else:
        dt = dt.replace(tzinfo=timezone.utc).astimezone()
    return dt.strftime("%Y-%m-%d %H:%M")
