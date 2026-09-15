"""Squarified treemap geometry (Bruls-Huizing-van Wijk, see design doc §5.4).

Pure geometry: no drawing here. Callers (Cairo widgets) turn :class:`TreemapItem`
rects into paint calls. This module only depends on :mod:`lindrivespace.core.fsnode`
for typing the optional node reference carried by each item.

The core layout routine follows the standard squarify formulation (lay rows or
columns greedily, minimising the worst aspect ratio in the row before it stops
growing) rather than a from-scratch derivation, since that formulation is the
one proven to keep aspect ratios low in the original paper.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from lindrivespace.core.fsnode import FsNode


@dataclass(frozen=True, slots=True)
class Rect:
    """An axis-aligned rectangle in layout units (pixels)."""

    x: float
    y: float
    w: float
    h: float

    @property
    def area(self) -> float:
        return self.w * self.h


@dataclass(frozen=True, slots=True)
class TreemapItem:
    """One laid-out cell: either a real node or a synthetic "files here" item."""

    key: Any
    value: float
    rect: Rect
    depth: int
    node: FsNode | None


def _layout_strip(sizes: Sequence[float], x: float, y: float, dx: float, dy: float) -> list[Rect]:
    """Lay `sizes` (areas) as one strip filling the short side of (dx, dy)."""
    covered = sum(sizes)
    if dx >= dy:
        # Horizontal container: strip is a column stack on the left, each
        # rect spanning the full available width-share, stacked in y.
        width = covered / dy if dy > 0 else 0.0
        rects = []
        cursor = y
        for s in sizes:
            h = s / width if width > 0 else 0.0
            rects.append(Rect(x, cursor, width, h))
            cursor += h
        return rects
    # Vertical container: strip is a row stack along the top, each rect
    # spanning the full available height-share, stacked in x.
    height = covered / dx if dx > 0 else 0.0
    rects = []
    cursor = x
    for s in sizes:
        w = s / height if height > 0 else 0.0
        rects.append(Rect(cursor, y, w, height))
        cursor += w
    return rects


def _worst_ratio(sizes: Sequence[float], x: float, y: float, dx: float, dy: float) -> float:
    if not sizes:
        return float("inf")
    rects = _layout_strip(sizes, x, y, dx, dy)
    worst = 0.0
    for r in rects:
        if r.w <= 0 or r.h <= 0:
            return float("inf")
        ratio = max(r.w / r.h, r.h / r.w)
        if ratio > worst:
            worst = ratio
    return worst


def _leftover(
    sizes: Sequence[float], x: float, y: float, dx: float, dy: float
) -> tuple[float, float, float, float]:
    covered = sum(sizes)
    if dx >= dy:
        width = covered / dy if dy > 0 else 0.0
        return (x + width, y, dx - width, dy)
    height = covered / dx if dx > 0 else 0.0
    return (x, y + height, dx, dy - height)


def squarify(values: Sequence[tuple[Any, float]], rect: Rect) -> list[TreemapItem]:
    """Lay out `values` (key, value) squarified into `rect`.

    Input may be unsorted; sorted descending internally. Non-positive values are
    skipped. Handles an empty sequence and a zero-area rect (returns []).
    """
    positive = [(k, float(v)) for k, v in values if v > 0]
    if not positive or rect.area <= 0:
        return []
    positive.sort(key=lambda kv: kv[1], reverse=True)

    total = sum(v for _, v in positive)
    scale = rect.area / total  # normalise values into the rect's area units
    remaining: list[tuple[Any, float]] = [(k, v * scale) for k, v in positive]

    items: list[TreemapItem] = []
    x, y, dx, dy = rect.x, rect.y, rect.w, rect.h

    while remaining:
        if dx <= 0 or dy <= 0:
            for key, val in remaining:
                items.append(
                    TreemapItem(
                        key=key, value=val / scale, rect=Rect(x, y, 0.0, 0.0), depth=0, node=None
                    )
                )
            break

        sizes = [v for _, v in remaining]
        i = 1
        while i < len(sizes) and _worst_ratio(sizes[:i], x, y, dx, dy) >= _worst_ratio(
            sizes[: i + 1], x, y, dx, dy
        ):
            i += 1

        current = remaining[:i]
        remaining = remaining[i:]
        rects = _layout_strip([v for _, v in current], x, y, dx, dy)
        for (key, val), r in zip(current, rects, strict=True):
            items.append(TreemapItem(key=key, value=val / scale, rect=r, depth=0, node=None))

        x, y, dx, dy = _leftover([v for _, v in current], x, y, dx, dy)

    return items


def layout_node(
    node: FsNode,
    rect: Rect,
    *,
    max_depth: int = 2,
    min_area: float = 24.0,
    padding: float = 2.0,
    allocated: bool = True,
    include_files: bool = True,
) -> list[TreemapItem]:
    """Nested squarified layout of `node`'s subtree, parents before children.

    Each directory child contributes its alloc/size; if `include_files` and the
    node has bytes not accounted for by children, a synthetic item
    (key=("files", node.id), node=None) represents "files directly here".
    Recursion stops at `max_depth` or when a child's rect area falls below
    `min_area`; child rects are inset by `padding` on each side before recursing.

    Output order: a node's own items are appended before it is expanded into
    its children's items, so a painter drawing in list order paints parents
    first (an explicit stack is used; no Python recursion).
    """

    def value_of(n: FsNode) -> float:
        return float(n.alloc if allocated else n.size)

    results: list[TreemapItem] = []
    stack: list[tuple[FsNode, Rect, int]] = [(node, rect, 0)]

    while stack:
        cur_node, cur_rect, depth = stack.pop()
        if cur_rect.area < min_area:
            continue

        entries: list[tuple[Any, float]] = [(c, value_of(c)) for c in cur_node.children]
        children_total = sum(v for _, v in entries)
        files_value = value_of(cur_node) - children_total
        if include_files and files_value > 0:
            entries.append((("files", cur_node.id), files_value))

        for item in squarify(entries, cur_rect):
            key = item.key
            item_node = key if isinstance(key, FsNode) else None
            resolved_key = key.id if isinstance(key, FsNode) else key
            results.append(
                TreemapItem(
                    key=resolved_key,
                    value=item.value,
                    rect=item.rect,
                    depth=depth,
                    node=item_node,
                )
            )
            if item_node is not None and depth + 1 <= max_depth and item.rect.area >= min_area:
                inset = Rect(
                    item.rect.x + padding,
                    item.rect.y + padding,
                    max(0.0, item.rect.w - 2 * padding),
                    max(0.0, item.rect.h - 2 * padding),
                )
                if inset.area >= min_area:
                    stack.append((item_node, inset, depth + 1))

    return results


def hit_test(items: Sequence[TreemapItem], x: float, y: float) -> TreemapItem | None:
    """Return the deepest item whose rect contains (x, y), or None."""
    best: TreemapItem | None = None
    for item in items:
        r = item.rect
        if (
            r.x <= x <= r.x + r.w
            and r.y <= y <= r.y + r.h
            and (best is None or item.depth >= best.depth)
        ):
            best = item
    return best
