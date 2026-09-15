"""WP9: InsightPanel and its four tab views (needs a display)."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import gi
import pytest

# The ``window`` fixture (tests/ui/conftest.py) is session-scoped, so pytest
# instantiates it (and the ``Settings()`` it builds) before the per-test
# ``isolated_xdg`` autouse fixture in tests/conftest.py gets a chance to
# monkeypatch XDG_CONFIG_HOME/XDG_CACHE_HOME — broader-scoped fixtures are
# always set up before narrower-scoped ones, autouse or not. Without this,
# ``page.settings.save()`` (exercised below) would read/write the real
# ``~/.config/lindrivespace/settings.json``. Force an isolated location here,
# at import time, before any fixture (this one included) can run.
_ISOLATED_XDG = Path(tempfile.mkdtemp(prefix="lindrivespace-test-insight-"))
os.environ["XDG_CONFIG_HOME"] = str(_ISOLATED_XDG / "config")
os.environ["XDG_CACHE_HOME"] = str(_ISOLATED_XDG / "cache")

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from lindrivespace.core.treemap import hit_test  # noqa: E402
from lindrivespace.ui.widgets.treemap_view import TreemapView  # noqa: E402

_NOW = time.time()


def _pump(cond, timeout: float = 30.0) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while not cond() and time.monotonic() < deadline:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.002)
    for _ in range(20):
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)


def _make_tree(tmp_path: Path) -> Path:
    """root/{videos/big (48h old), docs/{a.txt, b.txt (400d old)}, cache/tmp}."""
    root = tmp_path / "scanroot"
    (root / "videos").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    (root / "cache").mkdir(parents=True)

    videos_big = root / "videos" / "big.mkv"
    videos_big.write_bytes(b"v" * 500_000)

    doc_a = root / "docs" / "a.txt"
    doc_a.write_bytes(b"a" * 2_000)
    doc_b = root / "docs" / "b.txt"
    doc_b.write_bytes(b"b" * 1_000)

    cache_tmp = root / "cache" / "scratch.tmp"
    cache_tmp.write_bytes(b"c" * 500)

    recent = _NOW - 3600  # 1 hour old
    old = _NOW - 400 * 86400  # ~400 days old
    os.utime(videos_big, (recent, recent))
    os.utime(doc_a, (recent, recent))
    os.utime(doc_b, (old, old))
    os.utime(cache_tmp, (recent, recent))
    return root


@pytest.fixture
def page(window):  # type: ignore[no-untyped-def]
    window.show_page("explorer")
    page = window.pages["explorer"]
    if not page.has_side_panel:  # an earlier collapse test may have hidden it
        page.set_panel_visible(True)
    # The fixture tree is made of tiny files; the default 64 KB analysis threshold
    # (scan.top_min_bytes) would keep them all out of the Top files / Types / Age views.
    settings = window.app.settings
    previous = settings.get("scan.top_min_bytes", 65_536)
    settings.set("scan.top_min_bytes", 0)
    yield page
    settings.set("scan.top_min_bytes", previous)


def _scan_and_select_root(page, tmp_path: Path):  # type: ignore[no-untyped-def]
    root = _make_tree(tmp_path)
    page.start_scan(str(root))
    _pump(lambda: not page.controller.running)
    page.tree.select_node(page.model.root)
    _pump(lambda: page.panel.treemap.get_allocated_width() > 0)
    return page.model.root


# ---- panel presence / collapse -------------------------------------------------


def test_panel_present_by_default(page) -> None:  # type: ignore[no-untyped-def]
    assert page.has_side_panel is True
    assert page.settings.get("window.panel_visible", True) is True


def test_set_panel_visible_false_removes_and_persists(page) -> None:  # type: ignore[no-untyped-def]
    page.set_panel_visible(False)
    assert page.has_side_panel is False
    assert page.settings.get("window.panel_visible") is False


def test_toggle_panel_brings_it_back(page) -> None:  # type: ignore[no-untyped-def]
    page.set_panel_visible(False)
    page.toggle_panel()
    assert page.has_side_panel is True
    assert page.settings.get("window.panel_visible") is True


def test_toolbar_toggle_hides_panel(page) -> None:  # type: ignore[no-untyped-def]
    assert page.toolbar.panel_button.get_active() is True
    page.toolbar.panel_button.set_active(False)
    assert page.has_side_panel is False
    assert page.settings.get("window.panel_visible") is False


def test_collapse_button_hides_panel(page) -> None:  # type: ignore[no-untyped-def]
    if not page.has_side_panel:
        page.set_panel_visible(True)
    page.panel.emit("collapse-requested")
    assert page.has_side_panel is False
    assert page.toolbar.panel_button.get_active() is False


# ---- data flow: node-selected -> panel.set_node --------------------------------


def test_treemap_items_cover_root_area(page, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    root = _scan_and_select_root(page, tmp_path)
    panel = page.panel
    assert panel.current_tab == "treemap"

    treemap = panel.treemap
    items = treemap.items
    assert items, "expected the treemap to lay out at least one item"

    top_level = [it for it in items if it.depth == 0]
    total_area = sum(it.rect.w * it.rect.h for it in top_level)
    view_w = treemap.get_allocated_width()
    view_h = treemap.get_allocated_height()
    assert view_w > 0 and view_h > 0
    assert total_area == pytest.approx(view_w * view_h, rel=0.02)

    largest = max(top_level, key=lambda it: it.rect.w * it.rect.h)
    cx = largest.rect.x + largest.rect.w / 2
    cy = largest.rect.y + largest.rect.h / 2
    # Query against the top-level items only: at max_depth=2 the biggest
    # top-level rectangle is itself subdivided one level further (its own
    # children/"files" portion fully tiles its padded interior), so hit_test
    # against the *full* nested item list would correctly return that deeper
    # item instead — this checks the top-level geometry/identity in isolation.
    hit = hit_test(top_level, cx, cy)
    assert hit is not None
    assert hit.node is largest.node

    biggest_child = max(root.children, key=lambda n: n.alloc)
    assert largest.node is biggest_child


def test_top_files_view_lists_largest_first(page, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _scan_and_select_root(page, tmp_path)
    panel = page.panel
    panel.current_tab = "top_files"
    _pump(lambda: len(panel.top_files.rows) > 0)

    rows = panel.top_files.rows
    assert rows
    assert rows[0][0] == "videos/big.mkv"


def test_file_types_view_covers_present_classes(page, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _scan_and_select_root(page, tmp_path)
    panel = page.panel
    panel.current_tab = "types"
    _pump(lambda: len(panel.file_types.rows) > 0)

    labels = {row[0] for row in panel.file_types.rows}
    # big.mkv -> Video, a.txt/b.txt -> Documents, scratch.tmp -> Cache/temp
    assert {"Video", "Documents", "Cache/temp"} <= labels


def test_age_view_buckets_sum_to_subtree_allocation(page, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    root = _scan_and_select_root(page, tmp_path)
    panel = page.panel
    panel.current_tab = "age"
    _pump(lambda: sum(t for _l, t in panel.age.bucket_totals) > 0)

    expected_total = sum(tf.alloc for n in root.walk() for tf in n.top_files)
    bucket_total = sum(total for _label, total in panel.age.bucket_totals)
    assert bucket_total == expected_total

    labels = [label for label, _total in panel.age.bucket_totals]
    assert labels == ["7 d", "30 d", "90 d", "1 y", "older"]
    # b.txt is ~400 days old -> "older" bucket carries at least its allocation.
    older_total = dict(panel.age.bucket_totals)["older"]
    assert older_total > 0


# ---- offscreen render -----------------------------------------------------------


def test_treemap_offscreen_render_shows_accent_at_largest_rect(page, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    root = _scan_and_select_root(page, tmp_path)
    model = page.model

    # A standalone TreemapView (not the live panel's) so the offscreen render
    # doesn't disturb the page's own widget tree.
    treemap = TreemapView(page.theme)
    treemap.set_node(root, model)

    offscreen = Gtk.OffscreenWindow()
    offscreen.set_default_size(300, 220)
    offscreen.add(treemap)
    offscreen.show_all()
    _pump(lambda: treemap.get_allocated_width() > 0)
    treemap.ensure_fresh()
    treemap.queue_draw()
    _pump(lambda: False, timeout=0.2)

    pixbuf = offscreen.get_pixbuf()
    assert pixbuf is not None

    top_level = [it for it in treemap.items if it.depth == 0]
    assert top_level
    largest = max(top_level, key=lambda it: it.rect.w * it.rect.h)
    # Squarify always places the largest (first, sorted-descending) item's row
    # starting at the container's own origin, so the biggest top-level item's
    # rect starts exactly at the canvas's top-left corner (0, 0).
    assert largest.rect.x == pytest.approx(0.0, abs=0.01)
    assert largest.rect.y == pytest.approx(0.0, abs=0.01)
    # Sample just inside the item's own fill: past the 1 px bg_deep border
    # (which occupies column/row 0) but before the padded inset where a
    # nested (depth-1) child is drawn on top — a 1 px-wide band that is
    # never touched by either the border stroke or the recursion below it.
    cx = min(max(1, 0), pixbuf.get_width() - 1)
    cy = min(max(5, 0), pixbuf.get_height() - 1)

    n_channels = pixbuf.get_n_channels()
    rowstride = pixbuf.get_rowstride()
    pixels = pixbuf.get_pixels()
    offset = cy * rowstride + cx * n_channels
    r, g, b = pixels[offset], pixels[offset + 1], pixels[offset + 2]

    theme = page.theme
    accent_r, accent_g, accent_b = (int(round(c * 255)) for c in theme.rgb("accent"))
    assert abs(r - accent_r) <= 6
    assert abs(g - accent_g) <= 6
    assert abs(b - accent_b) <= 6

    offscreen.destroy()
