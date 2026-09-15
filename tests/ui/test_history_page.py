"""HistoryPage tests (needs a display). Uses the session-scoped ``window``
fixture from ``tests/ui/conftest.py`` -- see its docstring for why a full
``LinDriveSpaceApp`` is only built once per test session.
"""

from __future__ import annotations

import time
from pathlib import Path

import gi
import pytest

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from lindrivespace.core.history import HistoryStore  # noqa: E402
from lindrivespace.ui.widgets.trend_chart import TrendChart  # noqa: E402

DAY = 86400.0


def _pump() -> None:
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)


def _seeded_store(tmp_path: Path, *, days: int = 10, path: str = "/") -> HistoryStore:
    store = HistoryStore(tmp_path / "history.json", usage_min_interval=0.0)
    now = time.time()
    for i in range(days):
        ts = now - (days - 1 - i) * DAY
        store.add_sample(
            path, used=1_000_000 + i * 100_000, total=100_000_000, ts=ts, source="usage"
        )
    return store


@pytest.fixture
def page(window, tmp_path: Path):  # type: ignore[no-untyped-def]
    window.show_page("snapshots")
    page = window.pages["snapshots"]
    page.store = _seeded_store(tmp_path)
    page.refresh()
    _pump()
    yield page
    # Leave the shared session window/app on a harmless state for other modules.
    page.store = HistoryStore(tmp_path / "empty.json")
    page.refresh()
    _pump()


# ---------------------------------------------------------------------------
# path combo / period chips / chart wiring
# ---------------------------------------------------------------------------


def test_combo_lists_seeded_path(page) -> None:  # type: ignore[no-untyped-def]
    model = page.path_combo.get_model()
    values = [row[0] for row in model]
    assert values == ["/"]
    assert page.path_combo.get_active_text() == "/"
    assert page._current_path == "/"


def test_default_period_is_week(page) -> None:  # type: ignore[no-untyped-def]
    assert page._period == "week"
    assert page.period_buttons["week"].get_active() is True
    assert page.period_buttons["day"].get_active() is False


def test_switching_period_changes_chart_point_count(page) -> None:  # type: ignore[no-untyped-def]
    page.set_period("day")
    _pump()
    day_points = len(page.chart._points)

    page.set_period("week")
    _pump()
    week_points = len(page.chart._points)

    # a day window (one sample/day series) holds at most 1 bucketed point;
    # a week window sees several of the seeded daily samples, each 24h apart
    # (wider than the week period's 6-hour buckets), so it holds more.
    assert day_points <= 1
    assert week_points >= 5
    assert week_points > day_points


def test_set_period_persists_to_settings(page) -> None:  # type: ignore[no-untyped-def]
    page.set_period("month")
    assert page.settings.get("history.period") == "month"
    page.set_period("week")  # restore default for other tests in this module


def test_stats_labels_non_empty_when_data_present(page) -> None:  # type: ignore[no-untyped-def]
    page.set_period("all")
    _pump()
    assert page.tile_first.value_label.get_text() not in ("", "—")
    assert page.tile_latest.value_label.get_text() not in ("", "—")
    assert page.tile_change.value_label.get_text() not in ("", "—")
    assert page.tile_growth.value_label.get_text() not in ("", "—")
    page.set_period("week")


def test_stats_show_placeholder_with_no_selected_path(window, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    window.show_page("snapshots")
    page = window.pages["snapshots"]
    page.store = HistoryStore(tmp_path / "empty2.json")
    page.refresh()
    _pump()
    assert page._current_path is None
    assert page.tile_first.value_label.get_text() == "—"
    assert page.save_pattern_button.get_sensitive() is False


# ---------------------------------------------------------------------------
# Pattern History: save / open / remove
# ---------------------------------------------------------------------------


def test_save_current_view_adds_pattern_row(page) -> None:  # type: ignore[no-untyped-def]
    assert page.pattern_list.get_children() == []
    assert page.pattern_empty_label.get_visible() is True

    pattern = page.save_current_view("test")
    _pump()

    assert pattern is not None
    assert pattern.name == "test"
    assert pattern.path == "/"
    rows = page.pattern_list.get_children()
    assert len(rows) == 1
    assert page.pattern_empty_label.get_visible() is False
    assert page.pattern_list.get_visible() is True


def test_save_current_view_defaults_name_when_blank(page) -> None:  # type: ignore[no-untyped-def]
    pattern = page.save_current_view()
    assert pattern is not None
    assert pattern.path in pattern.name
    assert page._period in pattern.name or pattern.name  # sanity: non-empty, informative


def test_open_pattern_restores_path_and_period(page) -> None:  # type: ignore[no-untyped-def]
    page.set_period("month")
    pattern = page.save_current_view("open-me")
    _pump()
    page.set_period("day")
    assert page._period == "day"

    page._on_pattern_open(None, pattern)
    _pump()

    assert page._period == "month"
    assert page._current_path == "/"
    page.set_period("week")


def test_remove_pattern_deletes_row(page) -> None:  # type: ignore[no-untyped-def]
    pattern = page.save_current_view("to-remove")
    _pump()
    assert len(page.pattern_list.get_children()) == 1

    page._on_pattern_remove(None, pattern.id)
    _pump()

    assert page.pattern_list.get_children() == []
    assert page.pattern_empty_label.get_visible() is True
    assert page.store.patterns() == []


# ---------------------------------------------------------------------------
# TrendChart rendering
# ---------------------------------------------------------------------------


def _render(widget: Gtk.Widget):  # type: ignore[no-untyped-def]
    """Render ``widget`` off-screen, then put it back where it came from.

    ``page.chart`` normally lives inside the shared session window's
    ``PrefGroup`` card; a GTK widget can only have one parent, so this
    temporarily detaches it, grabs its pixbuf, and reattaches it to its
    original parent box afterwards so later tests still see an intact page.
    """
    parent = widget.get_parent()
    if parent is not None:
        parent.remove(widget)
    offscreen = Gtk.OffscreenWindow()
    offscreen.add(widget)
    offscreen.show_all()
    _pump()
    pixbuf = offscreen.get_pixbuf()
    offscreen.remove(widget)
    offscreen.destroy()
    if parent is not None:
        parent.pack_start(widget, False, False, 0)
        parent.show_all()
    return pixbuf


def test_trend_chart_renders_with_data(page) -> None:  # type: ignore[no-untyped-def]
    pixbuf = _render(page.chart)
    assert pixbuf is not None
    assert pixbuf.get_width() > 0
    assert pixbuf.get_height() > 0
    assert page.chart.get_parent() is not None


def test_trend_chart_renders_empty_state() -> None:  # type: ignore[no-untyped-def]
    from lindrivespace.config.theme import get_theme

    chart = TrendChart(get_theme(None))
    chart.set_series([], period="week")
    pixbuf = _render(chart)
    assert pixbuf is not None
    assert pixbuf.get_width() > 0
    assert pixbuf.get_height() > 0


# ---------------------------------------------------------------------------
# "Where space changed" (clickable Change tile)
# ---------------------------------------------------------------------------


def _pump_until(predicate, timeout: float = 5.0) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _pump()
        if predicate():
            return
        time.sleep(0.02)
    _pump()


def _two_snapshots(directory: Path, root_path: str = "/") -> None:
    from lindrivespace.core.fsnode import FsNode
    from lindrivespace.core.snapshot import save_snapshot

    def tree(video: int) -> FsNode:
        root = FsNode(1, root_path, top_limit=5)
        media = FsNode(2, "media", root)
        media.add_file(video, video, 1.0, "movie.mkv")
        media.finalize()
        root.finalize()
        return root

    directory.mkdir(parents=True, exist_ok=True)
    save_snapshot(tree(10_000_000), directory / "a.json.gz")
    time.sleep(0.01)
    save_snapshot(tree(60_000_000), directory / "b.json.gz")


def test_change_tile_is_a_button_and_panel_starts_hidden(page) -> None:  # type: ignore[no-untyped-def]
    assert isinstance(page.change_button, Gtk.Button)
    assert page.tile_change.get_parent() is page.change_button
    assert not page.change_group.get_visible()


def test_clicking_change_with_one_snapshot_explains(page, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    page.snapshot_dir = tmp_path / "scans"
    page.change_button.clicked()
    _pump_until(lambda: "Comparing" not in page.change_summary.get_text())
    assert page.change_summary.is_visible()
    assert "No completed scan" in page.change_summary.get_text()
    assert not page.change_frame.get_visible()
    page.change_button.clicked()  # toggles back off
    _pump()
    assert not page.change_group.get_visible()


def test_clicking_change_lists_folders_and_files(page, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    page.snapshot_dir = tmp_path / "scans"
    _two_snapshots(page.snapshot_dir, "/")
    page.show_changes(True)
    _pump_until(lambda: len(page.change_store) > 0)
    rows = {row[0]: row for row in page.change_store}
    assert "media" in rows and "media/movie.mkv" in rows
    assert rows["media"][1] == "Grew" and rows["media"][4].startswith("+")
    assert rows["media/movie.mkv"][7] is True  # is_file
    assert rows["media"][7] is False
    assert "+50" in page.change_summary.get_text()
    assert page.change_view.is_visible()  # the table and every ancestor are shown
    # first row is the largest absolute change
    first = page.change_store[0]
    assert first[5] == max(r[5] for r in page.change_store)
    # the copyable card carries the table's text
    assert "movie.mkv" in page.change_group.as_text()
    page.show_changes(False)
    _pump()


def test_save_pattern_row_shows_its_entry(page) -> None:  # type: ignore[no-untyped-def]
    page._on_save_pattern_clicked(page.save_pattern_button)
    _pump()
    assert page.pattern_name_entry.is_visible()
    page._on_pattern_save_cancel(None)
    _pump()
    assert not page.pattern_save_row.get_visible()
