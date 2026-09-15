from __future__ import annotations

import json
from pathlib import Path

import pytest

from lindrivespace.core.history import HistoryStore, Sample, default_history_path

DAY = 86400.0


def _store(tmp_path: Path, **kwargs: object) -> HistoryStore:
    return HistoryStore(tmp_path / "history.json", **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# default_history_path
# ---------------------------------------------------------------------------


def test_default_history_path_under_cache_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", "/tmp/xdg-cache-test")
    assert default_history_path() == Path("/tmp/xdg-cache-test/lindrivespace/history.json")


# ---------------------------------------------------------------------------
# add_sample: usage interval + 1% rule
# ---------------------------------------------------------------------------


def test_usage_sample_skipped_within_interval_and_small_change(tmp_path: Path) -> None:
    store = _store(tmp_path, usage_min_interval=3600.0)
    assert store.add_sample("/", used=1000, total=10_000, ts=0.0, source="usage") is True
    # 10 minutes later, used barely moved (< 1%) -> skipped
    kept = store.add_sample("/", used=1005, total=10_000, ts=600.0, source="usage")
    assert kept is False
    assert len(store.samples("/")) == 1


def test_usage_sample_kept_when_change_at_least_one_percent(tmp_path: Path) -> None:
    store = _store(tmp_path, usage_min_interval=3600.0)
    store.add_sample("/", used=1000, total=10_000, ts=0.0, source="usage")
    # 10 minutes later but used grew by >= 1%
    kept = store.add_sample("/", used=1020, total=10_000, ts=600.0, source="usage")
    assert kept is True
    assert len(store.samples("/")) == 2


def test_usage_sample_kept_once_interval_elapsed(tmp_path: Path) -> None:
    store = _store(tmp_path, usage_min_interval=3600.0)
    store.add_sample("/", used=1000, total=10_000, ts=0.0, source="usage")
    kept = store.add_sample("/", used=1001, total=10_000, ts=3600.0, source="usage")
    assert kept is True
    assert len(store.samples("/")) == 2


def test_scan_sample_always_kept(tmp_path: Path) -> None:
    store = _store(tmp_path, usage_min_interval=3600.0)
    store.add_sample("/", used=1000, total=10_000, ts=0.0, source="scan", alloc=900, entries=5)
    kept = store.add_sample(
        "/", used=1001, total=10_000, ts=1.0, source="scan", alloc=901, entries=6
    )
    assert kept is True
    samples = store.samples("/")
    assert len(samples) == 2
    assert samples[1].alloc == 901
    assert samples[1].entries == 6
    assert samples[1].source == "scan"


def test_add_sample_trims_to_max_per_path(tmp_path: Path) -> None:
    store = _store(tmp_path, max_per_path=5, usage_min_interval=0.0)
    for i in range(10):
        # each sample changes used a lot so none is skipped by the 1 % rule
        store.add_sample("/", used=1000 * (i + 1), total=1_000_000, ts=float(i), source="usage")
    samples = store.samples("/")
    assert len(samples) == 5
    # oldest ones are dropped -- the newest 5 (ts 5..9) remain, chronological
    assert [s.ts for s in samples] == [5.0, 6.0, 7.0, 8.0, 9.0]


def test_paths_most_sampled_first(tmp_path: Path) -> None:
    store = _store(tmp_path, usage_min_interval=0.0)
    store.add_sample("/a", used=1, total=10, ts=0.0)
    store.add_sample("/b", used=1, total=10, ts=0.0)
    store.add_sample("/b", used=2, total=10, ts=1.0)
    store.add_sample("/b", used=3, total=10, ts=2.0)
    assert store.paths() == ["/b", "/a"]


# ---------------------------------------------------------------------------
# series / buckets per period
# ---------------------------------------------------------------------------


def _seed_daily_series(store: HistoryStore, path: str, days: int, now: float) -> None:
    """One sample per day, ``days`` days back from ``now`` (inclusive of today)."""
    for i in range(days):
        ts = now - (days - 1 - i) * DAY
        store.add_sample(path, used=1000 + i * 100, total=1_000_000, ts=ts, source="usage")


def test_series_filters_by_period_window(tmp_path: Path) -> None:
    store = _store(tmp_path, usage_min_interval=0.0)
    now = 1000 * DAY
    _seed_daily_series(store, "/", days=40, now=now)

    week_series = store.series("/", "week", now=now)
    # a week window (7 days) ending "now" should hold ~8 samples (day 0..7 back)
    assert all(s.ts >= now - 7 * DAY for s in week_series)
    assert len(week_series) >= 7

    all_series = store.series("/", "all", now=now)
    assert len(all_series) == 40


def test_series_rejects_unknown_period(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.series("/", "fortnight")


def test_buckets_day_hourly(tmp_path: Path) -> None:
    store = _store(tmp_path, usage_min_interval=0.0)
    now = 10 * DAY
    # two samples in the same hour -> last one should win; plus one in a
    # different hour.
    store.add_sample("/", used=100, total=1000, ts=now - 7200, source="usage")
    store.add_sample("/", used=200, total=1000, ts=now - 7200 + 60, source="usage")
    store.add_sample("/", used=300, total=1000, ts=now - 1800, source="usage")

    buckets = store.buckets("/", "day", now=now)
    assert len(buckets) == 2
    # sorted by bucket start; the first bucket holds the *last* sample in it
    starts = [b[0] for b in buckets]
    assert starts == sorted(starts)
    first_bucket = buckets[0]
    assert first_bucket[1] == 200  # last-wins within the hour


def test_buckets_empty_when_no_samples(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.buckets("/nope", "week") == []


def test_buckets_month_daily_and_year_weekly(tmp_path: Path) -> None:
    store = _store(tmp_path, usage_min_interval=0.0)
    now = 400 * DAY
    _seed_daily_series(store, "/", days=25, now=now)

    month_buckets = store.buckets("/", "month", now=now)
    assert 20 <= len(month_buckets) <= 25  # ~daily buckets over the last 30 days

    year_buckets = store.buckets("/", "year", now=now)
    assert len(year_buckets) <= len(month_buckets)  # weekly buckets, coarser


# ---------------------------------------------------------------------------
# trend
# ---------------------------------------------------------------------------


def test_trend_empty_series(tmp_path: Path) -> None:
    store = _store(tmp_path)
    trend = store.trend("/missing", "week")
    assert trend == {
        "first": 0,
        "last": 0,
        "delta": 0,
        "per_day": 0.0,
        "days_to_full": None,
        "samples": 0,
    }


def test_trend_growing_series_has_positive_per_day_and_days_to_full(tmp_path: Path) -> None:
    store = _store(tmp_path, usage_min_interval=0.0)
    now = 10 * DAY
    total = 1_000_000
    # used grows by exactly 10,000 bytes/day for 5 days
    for i in range(5):
        ts = now - (4 - i) * DAY
        store.add_sample("/", used=100_000 + i * 10_000, total=total, ts=ts, source="usage")

    trend = store.trend("/", "week", now=now)
    assert trend["samples"] == 5
    assert trend["first"] == 100_000
    assert trend["last"] == 140_000
    assert trend["delta"] == 40_000
    assert trend["per_day"] == pytest.approx(10_000.0, rel=0.05)
    assert trend["days_to_full"] is not None
    expected_days = (total - 140_000) / trend["per_day"]
    assert trend["days_to_full"] == pytest.approx(expected_days, rel=0.05)


def test_trend_flat_series_has_no_days_to_full(tmp_path: Path) -> None:
    store = _store(tmp_path, usage_min_interval=0.0)
    now = 10 * DAY
    for i in range(5):
        ts = now - (4 - i) * DAY
        store.add_sample("/", used=100_000, total=1_000_000, ts=ts, source="usage")
    trend = store.trend("/", "week", now=now)
    assert trend["per_day"] == pytest.approx(0.0, abs=1e-6)
    assert trend["days_to_full"] is None


def test_trend_shrinking_series_has_no_days_to_full(tmp_path: Path) -> None:
    store = _store(tmp_path, usage_min_interval=0.0)
    now = 10 * DAY
    for i in range(5):
        ts = now - (4 - i) * DAY
        store.add_sample("/", used=200_000 - i * 10_000, total=1_000_000, ts=ts, source="usage")
    trend = store.trend("/", "week", now=now)
    assert trend["per_day"] < 0
    assert trend["days_to_full"] is None


def test_trend_unknown_total_has_no_days_to_full(tmp_path: Path) -> None:
    store = _store(tmp_path, usage_min_interval=0.0)
    now = 10 * DAY
    for i in range(5):
        ts = now - (4 - i) * DAY
        store.add_sample("/", used=100_000 + i * 10_000, total=0, ts=ts, source="usage")
    trend = store.trend("/", "week", now=now)
    assert trend["per_day"] > 0
    assert trend["days_to_full"] is None


# ---------------------------------------------------------------------------
# patterns
# ---------------------------------------------------------------------------


def test_add_pattern_captures_series_summary(tmp_path: Path) -> None:
    store = _store(tmp_path, usage_min_interval=0.0)
    now = 10 * DAY
    for i in range(3):
        ts = now - (2 - i) * DAY
        store.add_sample("/", used=1000 + i * 100, total=10_000, ts=ts, source="usage")

    pattern = store.add_pattern("My view", "/", "week", note="baseline", now=now)
    assert pattern.name == "My view"
    assert pattern.path == "/"
    assert pattern.period == "week"
    assert pattern.note == "baseline"
    assert pattern.samples == 3
    assert pattern.first_used == 1000
    assert pattern.last_used == 1200
    assert [p.id for p in store.patterns()] == [pattern.id]


def test_remove_pattern(tmp_path: Path) -> None:
    store = _store(tmp_path, usage_min_interval=0.0)
    store.add_sample("/", used=1, total=10, ts=0.0)
    pattern = store.add_pattern("View", "/", "all")
    assert len(store.patterns()) == 1
    store.remove_pattern(pattern.id)
    assert store.patterns() == []


def test_rename_pattern(tmp_path: Path) -> None:
    store = _store(tmp_path, usage_min_interval=0.0)
    store.add_sample("/", used=1, total=10, ts=0.0)
    pattern = store.add_pattern("Old name", "/", "all")
    store.rename_pattern(pattern.id, "New name")
    (renamed,) = store.patterns()
    assert renamed.name == "New name"
    assert renamed.id == pattern.id


def test_rename_missing_pattern_is_a_no_op(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.rename_pattern("does-not-exist", "New name")
    assert store.patterns() == []


# ---------------------------------------------------------------------------
# persistence: corrupt file + atomic round trip
# ---------------------------------------------------------------------------


def test_load_missing_file_gives_empty_store(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.paths() == []
    assert store.patterns() == []


def test_load_corrupt_file_backs_up_and_starts_empty(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    path.write_text("{not json", encoding="utf-8")
    store = HistoryStore(path)
    assert store.paths() == []
    assert store.patterns() == []
    backup = path.with_suffix(path.suffix + ".bak")
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == "{not json"
    assert not path.exists()


def test_save_round_trip_preserves_samples_and_patterns(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    store = HistoryStore(path, usage_min_interval=0.0)
    store.add_sample("/", used=1000, total=10_000, ts=0.0, source="usage")
    store.add_sample("/", used=1100, total=10_000, ts=100.0, source="scan", alloc=900, entries=42)
    store.add_pattern("Snap", "/", "all", now=200.0)

    reloaded = HistoryStore(path)
    samples = reloaded.samples("/")
    assert len(samples) == 2
    assert samples[0] == Sample(
        ts=0.0, path="/", used=1000, total=10_000, alloc=0, entries=0, source="usage"
    )
    assert samples[1].source == "scan"
    assert samples[1].alloc == 900
    assert samples[1].entries == 42

    patterns = reloaded.patterns()
    assert len(patterns) == 1
    assert patterns[0].name == "Snap"

    # no stray temp file left behind
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_save_writes_atomically_via_tmp_and_replace(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    store = HistoryStore(path, usage_min_interval=0.0)
    store.add_sample("/", used=1, total=10, ts=0.0, source="usage")
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["version"] == 1
    assert "/" in on_disk["samples"]
    assert on_disk["samples"]["/"][0][:3] == [0.0, 1, 10]
