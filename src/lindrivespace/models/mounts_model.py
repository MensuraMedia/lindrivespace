"""MountsModel: pure-Python view over one MountsService snapshot.

Kept free of GTK so it can be unit-tested headlessly (see
``tests/services/test_mounts_service.py`` and ``tests/ui/test_overview.py``).
The only non-stdlib import is :class:`MountCardData`, a plain dataclass from
``ui/widgets`` (WP5) with no GTK dependency of its own.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from lindrivespace.core.mounts import DiskInfo, MountInfo
from lindrivespace.ui.widgets import MountCardData

# Mirrors ring_gauge.colour_token_for_percent's "warn" threshold (§7.4).
_URGENT_THRESHOLD = 85.0
# Loop (snap squashfs) and virtual (no backing block device, e.g. tmpfs) disks
# are excluded from totals/counts so a physical disk is never double-counted
# and pseudo-filesystems never inflate "Total capacity".
_NON_PHYSICAL_KINDS = ("loop", "virtual")


@dataclass(slots=True)
class MountsModel:
    """Thin wrapper around the last (disks, mounts) snapshot from MountsService."""

    disks: list[DiskInfo] = field(default_factory=list)
    mounts: list[MountInfo] = field(default_factory=list)

    def set_snapshot(self, disks: list[DiskInfo], mounts: list[MountInfo]) -> None:
        self.disks = disks
        self.mounts = mounts

    # ---- internal filtering -------------------------------------------------

    def _counted_pairs(self) -> Iterator[tuple[MountInfo, DiskInfo]]:
        """Non-hidden, non-bind mounts living on a physical disk.

        Bind mounts are skipped so the same backing device isn't counted
        twice; loop/virtual disk groups (snap squashfs, tmpfs, ...) are
        skipped entirely so they never inflate capacity/usage totals.
        """
        for disk in self.disks:
            if disk.kind in _NON_PHYSICAL_KINDS:
                continue
            for mount in disk.mounts:
                if mount.hidden or mount.is_bind:
                    continue
                yield mount, disk

    def is_visible(self, mount: MountInfo, *, show_hidden: bool) -> bool:
        """Whether ``mount`` should render as a card given the "Show hidden" state."""
        return show_hidden or not mount.hidden

    def is_visible_disk(self, disk: DiskInfo, *, show_hidden: bool) -> bool:
        """Whether ``disk`` (a whole loop/virtual group) should render at all.

        Catches pseudo-filesystems whose fstype isn't in ``mounts.hidden_fstypes``
        (e.g. ``hugetlbfs``, ``mqueue``) but that still have no backing block
        device -- without this, "Show hidden" off would still surface a stray
        "virtual"/"loop" disk group full of not-technically-hidden mounts.
        """
        return show_hidden or disk.kind not in _NON_PHYSICAL_KINDS

    # ---- KPIs -----------------------------------------------------------------

    def totals(self) -> tuple[int, int, int]:
        """(capacity, used, free) over non-hidden, non-bind, physical mounts."""
        capacity = used = free = 0
        for mount, _disk in self._counted_pairs():
            capacity += mount.total
            used += mount.used
            free += mount.free
        return capacity, used, free

    def scanned_count(self, scan_history: dict[str, str]) -> int:
        """Number of counted mounts whose mountpoint is in ``scan_history``."""
        return sum(1 for mount, _disk in self._counted_pairs() if mount.mountpoint in scan_history)

    def counted_mount_count(self) -> int:
        return sum(1 for _ in self._counted_pairs())

    def counted_disk_count(self) -> int:
        return len({disk.kname for _mount, disk in self._counted_pairs()})

    def hidden_count(self) -> int:
        """Number of mounts flagged hidden regardless of the "Show hidden" state."""
        return sum(1 for disk in self.disks for mount in disk.mounts if mount.hidden)

    def most_urgent(self) -> MountInfo | None:
        """The counted mount with the highest usage, if any is >= 85%."""
        candidates = [
            mount
            for mount, _disk in self._counted_pairs()
            if mount.percent_used >= _URGENT_THRESHOLD
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda m: m.percent_used)

    # ---- card adaptation --------------------------------------------------

    def card_data(self, mount: MountInfo, scan_history: dict[str, str]) -> MountCardData:
        """Adapt one :class:`MountInfo` (+ its disk's kind) into a MountCardData."""
        disk = next((d for d in self.disks if mount in d.mounts), None)
        kind = disk.kind if disk is not None else "virtual"
        return MountCardData(
            name=mount.display_name,
            device=mount.kname or mount.device,
            fstype=mount.fstype,
            mountpoint=mount.mountpoint,
            used=mount.used,
            total=mount.total,
            scanned_at=scan_history.get(mount.mountpoint),
            kind=kind,
        )
