"""Headless collector: ``lindrivespace --collect [--scan]``.

Records a usage sample (statvfs used/total) for every physical mount into the
history store, and with ``--scan`` also runs a full scan of each mount and
records the allocated total. No GTK import — this is what the scheduler's
systemd user timer runs in the background.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from lindrivespace import __version__, logsetup
from lindrivespace.core.history import HistoryStore, default_history_path
from lindrivespace.core.mounts import DEFAULT_HIDDEN_FSTYPES, group_by_disk, list_mounts
from lindrivespace.core.options import DEFAULT_EXCLUDES, ScanOptions
from lindrivespace.core.scanner import Scanner

_PHYSICAL = {"nvme", "ssd", "hdd", "usb"}


def physical_mountpoints() -> list[str]:
    """Mountpoints on physical disks (same rule as the Overview's list)."""
    mounts = list_mounts(DEFAULT_HIDDEN_FSTYPES, include_hidden=False)
    disks = group_by_disk(mounts)
    out: list[str] = []
    for disk in disks:
        if disk.kind not in _PHYSICAL:
            continue
        for m in disk.mounts:
            if not m.hidden and not m.is_bind:
                out.append(m.mountpoint)
    return sorted(set(out))


def usage_of(path: str) -> tuple[int, int]:
    try:
        st = os.statvfs(path)
    except OSError:
        return (0, 0)
    total = st.f_blocks * st.f_frsize
    used = (st.f_blocks - st.f_bfree) * st.f_frsize
    return (max(0, used), max(0, total))


def collect(
    *, scan: bool = False, store: HistoryStore | None = None, paths: list[str] | None = None
) -> int:
    """Record usage (and optionally scan) samples. Returns the number of samples written."""
    log = logsetup.get_logger("collector")
    store = store or HistoryStore(default_history_path())
    targets = paths if paths is not None else physical_mountpoints()
    written = 0
    for path in targets:
        used, total = usage_of(path)
        if store.add_sample(path, used=used, total=total, source="usage"):
            written += 1
        if not scan:
            continue
        options = ScanOptions(excludes=DEFAULT_EXCLUDES)
        started = time.monotonic()
        entries = 0

        def on_event(_ev: object) -> None:
            pass

        try:
            root = Scanner().scan(path, options, on_event)
        except Exception as exc:  # noqa: BLE001 - one bad mount must not stop the run
            log.error("collector scan failed for %s: %s", path, exc)
            continue
        entries = root.files + root.dirs
        store.add_sample(
            path, used=used, total=total, source="scan", alloc=root.alloc, entries=entries
        )
        written += 1
        log.info(
            "collector scanned %s: %d entries, %d bytes in %.1f s",
            path,
            entries,
            root.alloc,
            time.monotonic() - started,
        )
    log.info("collector wrote %d samples for %d mounts", written, len(targets))
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lindrivespace --collect")
    parser.add_argument("--scan", action="store_true", help="also run a full scan of each mount")
    parser.add_argument("--path", action="append", help="limit to these mountpoints/folders")
    parser.add_argument("--version", action="version", version=f"lindrivespace {__version__}")
    args = parser.parse_args(argv)
    logsetup.setup_logging()
    written = collect(scan=args.scan, paths=args.path)
    print(f"recorded {written} sample(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
