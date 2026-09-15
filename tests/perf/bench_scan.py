#!/usr/bin/env python3
"""Manual throughput benchmark for :class:`core.scanner.Scanner`.

Not a pytest test -- deliberately named ``bench_*.py`` (outside pytest's
``test_*.py`` discovery pattern) with no ``test_`` functions, so it is never
collected. Run it directly::

    .venv/bin/python tests/perf/bench_scan.py --entries 100000

It builds (and reuses, if already present) a synthetic tree of the requested
size under the system temp directory, then times one warm-cache scan and
prints an ``entries/s`` line. Budget target (CLAUDE.md): >= 150k entries/s.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from lindrivespace.core.options import ScanOptions  # noqa: E402
from lindrivespace.core.scanner import Scanner  # noqa: E402

FILES_PER_DIR = 100
DIRS_PER_BUCKET = 200  # keep any single directory's fan-out reasonable


def build_tree(base: Path, entries: int) -> int:
    """Build (or reuse) a synthetic tree with ``entries`` files under ``base``.

    Returns the actual number of files created. A marker file *next to*
    ``base`` (not inside it, so it never pollutes the scanned entry count)
    records the entry count so a rerun with the same ``--entries`` reuses
    the tree as-is (matches the "reuse if exists" requirement); any other
    content at ``base`` is rebuilt from scratch.
    """
    marker = base.parent / f"{base.name}.marker"
    if marker.is_file():
        try:
            recorded = int(marker.read_text().strip())
        except ValueError:
            recorded = -1
        if recorded == entries:
            return recorded

    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)

    num_dirs = max(1, (entries + FILES_PER_DIR - 1) // FILES_PER_DIR)
    created = 0
    bucket: Path | None = None
    for d in range(num_dirs):
        if d % DIRS_PER_BUCKET == 0:
            bucket = base / f"bucket{d // DIRS_PER_BUCKET}"
            bucket.mkdir()
        assert bucket is not None
        d_path = bucket / f"d{d}"
        d_path.mkdir()
        for f in range(FILES_PER_DIR):
            if created >= entries:
                break
            (d_path / f"f{f}.txt").write_bytes(b"x")
            created += 1
        if created >= entries:
            break

    marker.write_text(str(created))
    return created


def run_bench(base: Path, entries: int) -> None:
    options = ScanOptions()

    # Warm-cache pass: discard timing, just get inodes/dentries into cache.
    Scanner().scan(str(base), options, lambda _e: None)

    start = time.perf_counter()
    root_node = Scanner().scan(str(base), options, lambda _e: None)
    elapsed = time.perf_counter() - start

    rate = entries / elapsed if elapsed > 0 else float("inf")
    print(f"entries={entries} elapsed={elapsed:.3f}s entries/s={rate:,.0f}")
    print(f"root files={root_node.files} dirs={root_node.dirs} size={root_node.size}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--entries", type=int, default=200_000, help="number of files to scan (default 200000)"
    )
    parser.add_argument(
        "--path",
        default=None,
        help="build/reuse the synthetic tree here instead of the default temp location",
    )
    args = parser.parse_args(argv)

    base = (
        Path(args.path)
        if args.path
        else Path(tempfile.gettempdir()) / f"lindrivespace_bench_{args.entries}"
    )
    actual_entries = build_tree(base, args.entries)
    run_bench(base, actual_entries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
