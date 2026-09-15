from __future__ import annotations

from lindrivespace.core.fsnode import FsNode
from lindrivespace.core.treemap import Rect, hit_test, layout_node, squarify

VALUES = [188, 151, 97, 62, 45, 39, 13, 10, 3, 1]


def _pairs(values: list[float]) -> list[tuple[int, float]]:
    return list(enumerate(values))


def test_squarify_areas_sum_to_rect_area() -> None:
    rect = Rect(0, 0, 348, 230)
    items = squarify(_pairs([float(v) for v in VALUES]), rect)
    total = sum(item.rect.area for item in items)
    assert abs(total - rect.area) <= rect.area * 1e-6
    assert len(items) == len(VALUES)


def test_squarify_no_overlaps() -> None:
    rect = Rect(0, 0, 348, 230)
    items = squarify(_pairs([float(v) for v in VALUES]), rect)
    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            ra, rb = a.rect, b.rect
            # No overlap if separated on either axis (touching edges are fine).
            separated = (
                ra.x + ra.w <= rb.x + 1e-9
                or rb.x + rb.w <= ra.x + 1e-9
                or ra.y + ra.h <= rb.y + 1e-9
                or rb.y + rb.h <= ra.y + 1e-9
            )
            assert separated, f"overlap between {ra} and {rb}"


def test_squarify_aspect_ratio_of_largest_item_reasonable() -> None:
    # Squeezing the smallest remaining slivers into whatever thin leftover
    # strip is left can blow up their aspect ratio; that's expected. What
    # must stay squarish is the biggest item, since that's the one users
    # actually look at.
    rect = Rect(0, 0, 348, 230)
    items = squarify(_pairs([float(v) for v in VALUES]), rect)
    largest = max(items, key=lambda item: item.value)
    r = largest.rect
    ratio = max(r.w / r.h, r.h / r.w)
    assert ratio <= 4.0, f"largest item's aspect ratio {ratio} exceeds 4"


def test_squarify_empty_input() -> None:
    assert squarify([], Rect(0, 0, 100, 100)) == []
    assert squarify([("a", 1.0)], Rect(0, 0, 0, 0)) == []


def test_squarify_skips_zero_and_negative() -> None:
    items = squarify([("a", 10.0), ("b", 0.0), ("c", -5.0)], Rect(0, 0, 100, 100))
    assert [item.key for item in items] == ["a"]
    assert items[0].rect.area == 100.0 * 100.0


def test_squarify_single_item_fills_rect() -> None:
    rect = Rect(10, 20, 100, 50)
    items = squarify([("only", 42.0)], rect)
    assert len(items) == 1
    assert items[0].rect == rect


def test_squarify_order_stable_for_ties() -> None:
    # Unsorted input; descending sort should be stable for equal values.
    items = squarify([("a", 5.0), ("b", 5.0), ("c", 5.0)], Rect(0, 0, 90, 30))
    assert [item.key for item in items] == ["a", "b", "c"]


def _build_tree() -> FsNode:
    root = FsNode(1, "/data", top_limit=5)
    a = FsNode(2, "a", root, mtime=1.0)
    b = FsNode(3, "b", root, mtime=2.0)
    c = FsNode(4, "c", a, mtime=3.0)
    a.add_file(1000, 1000, 5.0, "big.bin")
    b.add_file(2000, 2000, 6.0, "video.mp4")
    c.add_file(500, 500, 7.0, "note.txt")
    root.add_file(100, 100, 8.0, "readme.md")
    for node in (c, a, b, root):
        node.finalize()
    return root


def test_layout_node_parents_before_children() -> None:
    root = _build_tree()
    items = layout_node(root, Rect(0, 0, 400, 300), max_depth=3, min_area=1.0)
    seen_ids: set[int] = set()
    for item in items:
        if item.node is not None:
            if item.node.parent is not None:
                assert item.node.parent.id in seen_ids or item.node.parent.id == root.id
            seen_ids.add(item.node.id)


def test_layout_node_depth_values() -> None:
    root = _build_tree()
    items = layout_node(root, Rect(0, 0, 400, 300), max_depth=3, min_area=1.0)
    depth_by_id = {item.node.id: item.depth for item in items if item.node is not None}
    a = root.find(2)
    c = root.find(4)
    assert a is not None and c is not None
    assert depth_by_id[a.id] == 0
    assert depth_by_id[c.id] == 1


def test_layout_node_synthetic_files_item_present() -> None:
    root = _build_tree()
    items = layout_node(root, Rect(0, 0, 400, 300), max_depth=3, min_area=1.0)
    files_items = [item for item in items if isinstance(item.key, tuple) and item.key[0] == "files"]
    assert any(item.key == ("files", root.id) for item in files_items)
    assert all(item.node is None for item in files_items)


def test_layout_node_max_depth_limits_recursion() -> None:
    root = _build_tree()
    items = layout_node(root, Rect(0, 0, 400, 300), max_depth=0, min_area=1.0)
    assert all(item.depth == 0 for item in items)
    # No grandchildren (depth 1) should appear when max_depth=0.
    c = root.find(4)
    assert c is not None
    assert not any(item.node is c for item in items)


def test_layout_node_respects_min_area() -> None:
    root = _build_tree()
    items = layout_node(root, Rect(0, 0, 10, 10), max_depth=3, min_area=1_000_000.0)
    assert items == []


def test_hit_test_returns_deepest_item() -> None:
    root = _build_tree()
    items = layout_node(root, Rect(0, 0, 400, 300), max_depth=3, min_area=1.0)
    a = root.find(2)
    assert a is not None
    a_item = next(item for item in items if item.node is a)
    cx = a_item.rect.x + a_item.rect.w / 2
    cy = a_item.rect.y + a_item.rect.h / 2
    hit = hit_test(items, cx, cy)
    assert hit is not None
    assert hit.rect.x <= cx <= hit.rect.x + hit.rect.w
    assert hit.rect.y <= cy <= hit.rect.y + hit.rect.h
    # The deepest item at that point should have depth >= the depth of `a`'s item.
    assert hit.depth >= a_item.depth


def test_hit_test_outside_returns_none() -> None:
    root = _build_tree()
    items = layout_node(root, Rect(0, 0, 400, 300), max_depth=3, min_area=1.0)
    assert hit_test(items, -10, -10) is None
