"""Historical disk-usage recording (WP17): periodic "usage" samples plus
"scan" samples taken when a scan finishes, kept per path (mountpoint or
folder) and rolled up into per-period series/buckets/trend figures for the
History page. Also stores small user-named "Pattern History" bookmarks of a
particular path/period view.

Pure Python, stdlib only (see ``.claude/rules/core-purity.md``): ``core/`` is
a leaf package, so ``default_history_path`` replicates the XDG cache lookup
from ``config/settings.py`` instead of importing it (same precedent as
``core/snapshot.py::default_snapshot_dir``).

On-disk format (``default_history_path()``, JSON)::

    {"version": 1,
     "samples": {path: [[ts, used, total, alloc, entries, source], ...]},
     "patterns": [{"id", "name", "path", "period", "created", "note",
                    "first_used", "last_used", "samples"}, ...]}

Samples are stored chronologically per path. Writes are atomic (tmp file +
``os.replace``); a corrupt file is preserved as ``<path>.bak`` and loading
falls back to an empty store.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Sample:
    ts: float  # unix time
    path: str  # mountpoint or folder
    used: int  # bytes used on the filesystem (statvfs) -- 0 if unknown
    total: int  # bytes total -- 0 if unknown
    alloc: int = 0  # allocated bytes from a completed scan -- 0 if not a scan sample
    entries: int = 0  # entries from a completed scan
    source: str = "usage"  # "usage" (periodic) | "scan" (completed scan)


@dataclass(frozen=True, slots=True)
class Pattern:
    id: str  # short unique id
    name: str
    path: str
    period: str  # "day" | "week" | "month" | "year" | "all"
    created: float
    note: str = ""
    first_used: int = 0  # summary of the series at save time
    last_used: int = 0
    samples: int = 0


# (id, label, span in seconds -- None means "all history")
PERIODS: tuple[tuple[str, str, float | None], ...] = (
    ("day", "Day", 86400.0),
    ("week", "Week", 7 * 86400.0),
    ("month", "Month", 30 * 86400.0),
    ("year", "Year", 365 * 86400.0),
    ("all", "All", None),
)
_PERIOD_SPANS: dict[str, float | None] = {pid: span for pid, _label, span in PERIODS}
_VALID_PERIODS: frozenset[str] = frozenset(_PERIOD_SPANS)

# Bucket width (seconds) per period, used by :meth:`HistoryStore.buckets`.
_BUCKET_SPANS: dict[str, float] = {
    "day": 3600.0,  # hourly
    "week": 6 * 3600.0,  # 6-hour
    "month": 86400.0,  # daily
    "year": 7 * 86400.0,  # weekly
    "all": 30 * 86400.0,  # ~monthly
}

_FORMAT_VERSION = 1


def default_history_path() -> Path:
    """``<cache_dir>/history.json`` (``$XDG_CACHE_HOME`` or ``~/.cache``).

    Mirrors :func:`lindrivespace.config.settings.cache_dir` without importing
    it, so ``core/`` stays a leaf package.
    """
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return Path(base) / "lindrivespace" / "history.json"


class HistoryStore:
    """Loads/saves samples and patterns, and rolls samples up into series."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        max_per_path: int = 5000,
        usage_min_interval: float = 3600.0,
    ) -> None:
        self.path = path or default_history_path()
        self.max_per_path = max_per_path
        self.usage_min_interval = usage_min_interval
        self._samples: dict[str, list[Sample]] = {}
        self._patterns: list[Pattern] = []
        self.load()

    # ---- persistence ------------------------------------------------------

    def load(self) -> None:
        """Populate from disk. Tolerant of a missing or corrupt file."""
        self._samples = {}
        self._patterns = []
        try:
            with open(self.path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            return
        try:
            data = json.loads(text)
        except ValueError:
            self._backup_corrupt()
            return
        if not isinstance(data, dict):
            self._backup_corrupt()
            return

        raw_samples = data.get("samples", {})
        if isinstance(raw_samples, dict):
            for sample_path, rows in raw_samples.items():
                if not isinstance(sample_path, str) or not isinstance(rows, list):
                    continue
                parsed = [s for row in rows if (s := _row_to_sample(sample_path, row)) is not None]
                parsed.sort(key=lambda s: s.ts)
                self._samples[sample_path] = parsed

        raw_patterns = data.get("patterns", [])
        if isinstance(raw_patterns, list):
            self._patterns = [p for row in raw_patterns if (p := _dict_to_pattern(row)) is not None]

    def _backup_corrupt(self) -> None:
        try:
            self.path.replace(self.path.with_suffix(self.path.suffix + ".bak"))
        except OSError:
            pass

    def save(self) -> None:
        """Atomic write: temp file in the same directory, then ``os.replace``."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "version": _FORMAT_VERSION,
            "samples": {
                sample_path: [_sample_to_row(s) for s in rows]
                for sample_path, rows in self._samples.items()
            },
            "patterns": [_pattern_to_dict(p) for p in self._patterns],
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    # ---- samples ------------------------------------------------------------

    def add_sample(
        self,
        path: str,
        *,
        used: int,
        total: int,
        ts: float | None = None,
        source: str = "usage",
        alloc: int = 0,
        entries: int = 0,
    ) -> bool:
        """Record one sample; returns whether it was kept.

        A "usage" sample within ``usage_min_interval`` seconds of the previous
        usage sample for the same path is skipped unless ``used`` changed by
        at least 1 %. "scan" samples are always kept. Trims the path's series
        to ``max_per_path`` (oldest first) and saves.
        """
        when = ts if ts is not None else time.time()
        series = self._samples.setdefault(path, [])

        if source == "usage":
            previous = next((s for s in reversed(series) if s.source == "usage"), None)
            if previous is not None and (when - previous.ts) < self.usage_min_interval:
                base = previous.used if previous.used else 1
                if abs(used - previous.used) / base < 0.01:
                    return False

        series.append(
            Sample(
                ts=when,
                path=path,
                used=used,
                total=total,
                alloc=alloc,
                entries=entries,
                source=source,
            )
        )
        series.sort(key=lambda s: s.ts)
        if len(series) > self.max_per_path:
            del series[: len(series) - self.max_per_path]
        self.save()
        return True

    def paths(self) -> list[str]:
        """All recorded paths, most-sampled first (alphabetical tiebreak)."""
        return sorted(self._samples, key=lambda p: (-len(self._samples[p]), p))

    def samples(self, path: str) -> list[Sample]:
        """Every sample for ``path``, chronological."""
        return list(self._samples.get(path, ()))

    def series(self, path: str, period: str, now: float | None = None) -> list[Sample]:
        """Samples for ``path`` within ``period``'s span ending at ``now``."""
        span = _period_span(period)
        rows = self._samples.get(path, ())
        if span is None:
            return list(rows)
        cutoff = (now if now is not None else time.time()) - span
        return [s for s in rows if s.ts >= cutoff]

    def buckets(
        self, path: str, period: str, now: float | None = None
    ) -> list[tuple[float, int, int]]:
        """``(bucket_start_ts, used_last, total_last)`` per non-empty bucket.

        Bucket width follows ``period`` (hourly for a day, 6-hourly for a
        week, daily for a month, weekly for a year, ~monthly for "all"); the
        last sample within a bucket wins.
        """
        bucket_span = _BUCKET_SPANS[_check_period(period)]
        rolled: dict[int, tuple[float, int, int]] = {}
        for s in self.series(path, period, now):
            start = (int(s.ts) // int(bucket_span)) * int(bucket_span)
            rolled[start] = (float(start), s.used, s.total)
        return [rolled[key] for key in sorted(rolled)]

    def trend(self, path: str, period: str, now: float | None = None) -> dict[str, Any]:
        """Summary stats for ``path`` over ``period``.

        ``per_day`` is a linear (least-squares) fit of ``used`` over time,
        in bytes/day. ``days_to_full`` is ``None`` unless the series is
        growing and the filesystem total is known.
        """
        series = self.series(path, period, now)
        if not series:
            return {
                "first": 0,
                "last": 0,
                "delta": 0,
                "per_day": 0.0,
                "days_to_full": None,
                "samples": 0,
            }

        first = series[0].used
        last = series[-1].used
        per_day = _linear_fit_per_day(series)

        days_to_full: float | None = None
        total = series[-1].total
        if per_day > 0 and total > 0:
            remaining = total - last
            days_to_full = max(0.0, remaining) / per_day

        return {
            "first": first,
            "last": last,
            "delta": last - first,
            "per_day": per_day,
            "days_to_full": days_to_full,
            "samples": len(series),
        }

    # ---- patterns -----------------------------------------------------------

    def patterns(self) -> list[Pattern]:
        return list(self._patterns)

    def add_pattern(
        self, name: str, path: str, period: str, note: str = "", now: float | None = None
    ) -> Pattern:
        """Save the current ``path``/``period`` view as a named pattern."""
        series = self.series(path, _check_period(period), now)
        pattern = Pattern(
            id=uuid.uuid4().hex[:12],
            name=name,
            path=path,
            period=period,
            created=now if now is not None else time.time(),
            note=note,
            first_used=series[0].used if series else 0,
            last_used=series[-1].used if series else 0,
            samples=len(series),
        )
        self._patterns.append(pattern)
        self.save()
        return pattern

    def remove_pattern(self, pattern_id: str) -> None:
        before = len(self._patterns)
        self._patterns = [p for p in self._patterns if p.id != pattern_id]
        if len(self._patterns) != before:
            self.save()

    def rename_pattern(self, pattern_id: str, name: str) -> None:
        for i, p in enumerate(self._patterns):
            if p.id == pattern_id:
                self._patterns[i] = Pattern(
                    id=p.id,
                    name=name,
                    path=p.path,
                    period=p.period,
                    created=p.created,
                    note=p.note,
                    first_used=p.first_used,
                    last_used=p.last_used,
                    samples=p.samples,
                )
                self.save()
                return


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _check_period(period: str) -> str:
    if period not in _VALID_PERIODS:
        raise ValueError(f"unknown period: {period!r}")
    return period


def _period_span(period: str) -> float | None:
    return _PERIOD_SPANS[_check_period(period)]


def _linear_fit_per_day(series: list[Sample]) -> float:
    """Least-squares slope of ``used`` over ``ts``, in bytes/day."""
    n = len(series)
    if n < 2:
        return 0.0
    xs = [s.ts for s in series]
    ys = [float(s.used) for s in series]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    numer = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    slope_per_second = numer / denom
    return slope_per_second * 86400.0


def _sample_to_row(s: Sample) -> list[Any]:
    return [s.ts, s.used, s.total, s.alloc, s.entries, s.source]


def _row_to_sample(path: str, row: Any) -> Sample | None:
    if not isinstance(row, list) or len(row) < 3:
        return None
    try:
        ts = float(row[0])
        used = int(row[1])
        total = int(row[2])
        alloc = int(row[3]) if len(row) > 3 else 0
        entries = int(row[4]) if len(row) > 4 else 0
        source = str(row[5]) if len(row) > 5 else "usage"
    except (TypeError, ValueError):
        return None
    return Sample(
        ts=ts, path=path, used=used, total=total, alloc=alloc, entries=entries, source=source
    )


def _pattern_to_dict(p: Pattern) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "path": p.path,
        "period": p.period,
        "created": p.created,
        "note": p.note,
        "first_used": p.first_used,
        "last_used": p.last_used,
        "samples": p.samples,
    }


def _dict_to_pattern(row: Any) -> Pattern | None:
    if not isinstance(row, dict):
        return None
    try:
        return Pattern(
            id=str(row["id"]),
            name=str(row["name"]),
            path=str(row["path"]),
            period=str(row["period"]),
            created=float(row["created"]),
            note=str(row.get("note", "")),
            first_used=int(row.get("first_used", 0)),
            last_used=int(row.get("last_used", 0)),
            samples=int(row.get("samples", 0)),
        )
    except (KeyError, TypeError, ValueError):
        return None
