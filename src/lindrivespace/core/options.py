"""Scan options — a frozen contract shared by the scanner, the controller and settings."""

from __future__ import annotations

from dataclasses import dataclass

# Pruned before scandir. Trailing slash semantics: a path is excluded when it
# equals the entry or starts with entry + "/".
DEFAULT_EXCLUDES: tuple[str, ...] = (
    "/proc",
    "/sys",
    "/dev",
    "/run",
    "/snap",
    "/var/lib/snapd/snap",
)


@dataclass(slots=True, frozen=True)
class ScanOptions:
    """How a scan behaves. Defaults match the concept document §3.2."""

    follow_symlinks: bool = False
    cross_mounts: bool = False
    count_hardlinks_once: bool = True
    show_hidden: bool = True
    excludes: tuple[str, ...] = DEFAULT_EXCLUDES
    top_files: int = 50  # per-directory ring of largest files (0 = keep none)
    top_min_bytes: int = 65_536  # files below this never enter the ring (memory + speed)
    batch_size: int = 5000  # events per batch before a Progress heartbeat
    progress_interval: float = 0.1  # seconds between Progress events

    def is_excluded(self, path: str) -> bool:
        for ex in self.excludes:
            if path == ex or path.startswith(ex.rstrip("/") + "/"):
                return True
        return False
