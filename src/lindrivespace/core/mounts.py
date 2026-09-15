"""Mount & disk topology: psutil + ``/proc/self/mountinfo`` + ``lsblk``.

Pure Python (stdlib + psutil); see docs/CONCEPT-AND-TECHNICAL-DESIGN.md §8 and
.claude/rules/core-purity.md. ``pyudev`` is imported lazily, only inside
:class:`MountMonitor`, so this module still imports cleanly on a machine (or
in a test) that does not have it installed.

Merge key between the three sources is major:minor (``maj:min`` in ``lsblk``,
the third field of a ``mountinfo`` line); mountpoint is the fallback when a
device has no block-device backing (tmpfs, proc, overlay, ...).
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from typing import Any

import psutil

# Mirrors config/settings.py DEFAULTS["mounts"]["hidden_fstypes"]. Core stays
# independent of config (see .claude/rules/core-purity.md), so the tuple is
# duplicated here rather than imported.
DEFAULT_HIDDEN_FSTYPES: tuple[str, ...] = (
    "squashfs",
    "tmpfs",
    "devtmpfs",
    "proc",
    "sysfs",
    "cgroup",
    "cgroup2",
    "overlay",
    "fuse.portal",
    "efivarfs",
    "autofs",
)

_LSBLK_COLUMNS = "NAME,KNAME,PKNAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINT,MODEL,ROTA,TRAN,MAJ:MIN"

# Kind priority for group_by_disk ordering: physical disks first, then loop/virtual.
_KIND_PRIORITY = {"nvme": 0, "ssd": 1, "hdd": 1, "usb": 2, "loop": 3, "virtual": 4}


@dataclass(slots=True, frozen=True)
class MountInfoRaw:
    """One parsed line of ``/proc/self/mountinfo`` (see ``proc(5)``)."""

    mount_id: int
    parent_id: int
    maj_min: str
    root: str
    mountpoint: str
    options: str
    fstype: str
    source: str


@dataclass(slots=True, frozen=True)
class LsblkNode:
    """One flattened node from ``lsblk -J`` output (disk, part, crypt, lvm, loop, ...)."""

    name: str
    kname: str
    pkname: str | None
    size: int
    type: str
    fstype: str | None
    label: str | None
    uuid: str | None
    mountpoint: str | None
    model: str | None
    rota: bool
    tran: str | None
    maj_min: str
    disk_kname: str | None  # top-level ancestor of type "disk"; None for loop/virtual


@dataclass(slots=True, frozen=True)
class MountInfo:
    """A single active mount, merged from psutil + mountinfo + lsblk."""

    device: str
    kname: str
    mountpoint: str
    fstype: str
    options: str
    total: int
    used: int
    free: int
    percent_used: float
    label: str | None
    uuid: str | None
    maj_min: str
    disk_kname: str | None
    hidden: bool
    mount_id: int | None
    parent_id: int | None
    is_bind: bool
    display_name: str


@dataclass(slots=True)
class DiskInfo:
    """A physical (or virtual) disk grouping the mounts found on it."""

    kname: str
    path: str
    model: str | None
    size: int
    transport: str
    rotational: bool
    mounts: list[MountInfo] = field(default_factory=list)
    kind: str = "virtual"


# ---- mountinfo ---------------------------------------------------------------


def _unescape_octal(value: str) -> str:
    """Undo mountinfo's octal escaping (``\\040`` -> space, ``\\011`` -> tab, ...)."""
    if "\\" not in value:
        return value
    out: list[str] = []
    i = 0
    n = len(value)
    while i < n:
        ch = value[i]
        if ch == "\\" and i + 3 < n and value[i + 1 : i + 4].isdigit():
            out.append(chr(int(value[i + 1 : i + 4], 8)))
            i += 4
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def parse_mountinfo(text: str) -> list[MountInfoRaw]:
    """Parse ``/proc/self/mountinfo``-formatted text into raw rows.

    Handles the variable number of optional fields before the ``-``
    separator and the kernel's octal escaping of spaces/tabs/newlines/
    backslashes in ``root`` and ``mountpoint``.
    """
    rows: list[MountInfoRaw] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        fields = line.split(" ")
        try:
            separator = fields.index("-")
        except ValueError:
            continue
        pre = fields[:separator]
        post = fields[separator + 1 :]
        if len(pre) < 6 or len(post) < 2:
            continue
        rows.append(
            MountInfoRaw(
                mount_id=int(pre[0]),
                parent_id=int(pre[1]),
                maj_min=pre[2],
                root=_unescape_octal(pre[3]),
                mountpoint=_unescape_octal(pre[4]),
                options=pre[5],
                fstype=post[0],
                source=_unescape_octal(post[1]),
            )
        )
    return rows


def read_mountinfo() -> str:
    """Read this process's mountinfo; "" on any failure."""
    try:
        with open("/proc/self/mountinfo", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


# ---- lsblk ---------------------------------------------------------------------


def run_lsblk() -> str:
    """Run ``lsblk -J -b`` with the columns this module needs; "{}" on any failure."""
    try:
        result = subprocess.run(
            ["lsblk", "-J", "-b", "-o", _LSBLK_COLUMNS],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "{}"
    if result.returncode != 0 or not result.stdout.strip():
        return "{}"
    return result.stdout


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return bool(value)


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def parse_lsblk_json(text: str) -> dict[str, LsblkNode]:
    """Flatten ``lsblk -J`` output (nested ``children``), keyed by ``kname``.

    Each node's ``disk_kname`` is the top-level ancestor of type ``"disk"``,
    found by walking up through ``crypt``/``lvm``/``part``/``raid`` parents
    (so LVM-over-LUKS resolves to the underlying physical disk). Loop devices
    have no ``disk`` ancestor: ``disk_kname`` is ``None`` for them, and
    :func:`group_by_disk` treats each loop device as its own top-level group.
    """
    try:
        data: Any = json.loads(text) if text.strip() else {}
    except ValueError:
        data = {}
    devices = data.get("blockdevices") if isinstance(data, dict) else None
    if not isinstance(devices, list):
        return {}

    nodes: dict[str, LsblkNode] = {}
    parent_of: dict[str, str | None] = {}
    type_of: dict[str, str] = {}

    def walk(items: object, pkname: str | None) -> None:
        if not isinstance(items, list):
            return
        for raw in items:
            if not isinstance(raw, dict):
                continue
            kname = str(raw.get("kname") or raw.get("name") or "")
            if not kname:
                continue
            node_type = str(raw.get("type") or "")
            resolved_pkname = _as_optional_str(raw.get("pkname")) or pkname
            parent_of[kname] = resolved_pkname
            type_of[kname] = node_type
            nodes[kname] = LsblkNode(
                name=str(raw.get("name") or kname),
                kname=kname,
                pkname=resolved_pkname,
                size=_as_int(raw.get("size")),
                type=node_type,
                fstype=_as_optional_str(raw.get("fstype")),
                label=_as_optional_str(raw.get("label")),
                uuid=_as_optional_str(raw.get("uuid")),
                mountpoint=_as_optional_str(raw.get("mountpoint")),
                model=_as_optional_str(raw.get("model")),
                rota=_as_bool(raw.get("rota")),
                tran=_as_optional_str(raw.get("tran")),
                maj_min=str(raw.get("maj:min") or ""),
                disk_kname=None,  # resolved below, once the whole tree is flattened
            )
            children = raw.get("children")
            if isinstance(children, list):
                walk(children, kname)

    walk(devices, None)

    def find_disk_kname(kname: str) -> str | None:
        seen: set[str] = set()
        current: str | None = kname
        while current is not None and current not in seen:
            seen.add(current)
            if type_of.get(current) == "disk":
                return current
            current = parent_of.get(current)
        return None

    return {
        kname: replace(node, disk_kname=find_disk_kname(kname)) for kname, node in nodes.items()
    }


# ---- merged mount list -----------------------------------------------------------


def list_mounts(
    hidden_fstypes: Iterable[str] = DEFAULT_HIDDEN_FSTYPES,
    include_hidden: bool = False,
    *,
    mountinfo_text: str | None = None,
    lsblk_text: str | None = None,
    statvfs: Callable[[str], os.statvfs_result] = os.statvfs,
) -> list[MountInfo]:
    """Merge ``psutil.disk_partitions(all=True)`` with mountinfo and lsblk.

    ``mountinfo_text``/``lsblk_text`` let tests inject canned data instead of
    shelling out / reading ``/proc``; ``statvfs`` is injectable the same way.
    Hidden filesystems (``hidden_fstypes``) are dropped unless
    ``include_hidden`` is set. Bind mounts are kept (all mountpoints of a
    device are reported) and flagged via ``is_bind`` rather than deduped away.
    """
    hidden_set = set(hidden_fstypes)

    # maj:min is not unique when the same device is bind-mounted at several
    # places, so the precise key is (maj_min, mountpoint); maj:min alone and
    # mountpoint alone are progressively looser fallbacks.
    raw_rows = parse_mountinfo(mountinfo_text if mountinfo_text is not None else read_mountinfo())
    by_exact: dict[tuple[str, str], MountInfoRaw] = {}
    by_mountpoint: dict[str, MountInfoRaw] = {}
    by_maj_min: dict[str, MountInfoRaw] = {}
    for row in raw_rows:
        by_exact[(row.maj_min, row.mountpoint)] = row
        by_mountpoint[row.mountpoint] = row
        by_maj_min.setdefault(row.maj_min, row)

    lsblk_nodes = parse_lsblk_json(lsblk_text if lsblk_text is not None else run_lsblk())

    seen: set[tuple[str, str]] = set()
    mounts: list[MountInfo] = []
    for part in psutil.disk_partitions(all=True):
        key = (part.device, part.mountpoint)
        if key in seen:
            continue
        seen.add(key)

        raw_kname = part.device.rsplit("/", 1)[-1] if part.device.startswith("/dev/") else ""
        node = lsblk_nodes.get(raw_kname)
        if node is None and raw_kname:
            # /dev/mapper/<name> (LVM/LUKS) has a friendly name that differs
            # from its real KNAME (dm-N); fall back to a name match.
            node = next((n for n in lsblk_nodes.values() if n.name == raw_kname), None)
        kname = node.kname if node is not None else raw_kname
        maj_min = node.maj_min if node is not None and node.maj_min else ""

        raw = by_exact.get((maj_min, part.mountpoint)) if maj_min else None
        if raw is None:
            raw = by_mountpoint.get(part.mountpoint)
        if raw is None and maj_min:
            raw = by_maj_min.get(maj_min)

        fstype = part.fstype
        raw_fstype = raw.fstype if raw is not None else fstype
        is_snap_squashfs_loop = (
            node is not None
            and node.type == "loop"
            and fstype == "squashfs"
            and part.mountpoint.startswith("/snap/")
        )
        hidden = fstype in hidden_set or raw_fstype in hidden_set or is_snap_squashfs_loop
        if hidden and not include_hidden:
            continue

        try:
            st = statvfs(part.mountpoint)
            total = st.f_frsize * st.f_blocks
            free = st.f_frsize * st.f_bavail
            used = total - st.f_frsize * st.f_bfree
        except OSError:
            total = used = free = 0

        percent_used = (used / total * 100.0) if total > 0 else 0.0
        label = node.label if node is not None else None
        display_name = label if label else part.mountpoint

        mounts.append(
            MountInfo(
                device=part.device,
                kname=kname,
                mountpoint=part.mountpoint,
                fstype=fstype,
                options=part.opts,
                total=total,
                used=used,
                free=free,
                percent_used=percent_used,
                label=label,
                uuid=node.uuid if node is not None else None,
                maj_min=maj_min or (raw.maj_min if raw is not None else ""),
                disk_kname=node.disk_kname if node is not None else None,
                hidden=hidden,
                mount_id=raw.mount_id if raw is not None else None,
                parent_id=raw.parent_id if raw is not None else None,
                is_bind=raw.root != "/" if raw is not None else False,
                display_name=display_name,
            )
        )

    mounts.sort(key=lambda m: m.mountpoint)
    return mounts


# ---- grouping by physical disk ----------------------------------------------------


def _derive_kind(node_type: str, tran: str | None, rota: bool) -> str:
    if node_type == "loop":
        return "loop"
    if tran == "usb":
        return "usb"
    if tran == "nvme":
        return "nvme"
    if tran in ("sata", "ata", "scsi", "ide") or tran is None:
        return "hdd" if rota else "ssd"
    return "virtual"


def group_by_disk(mounts: list[MountInfo], *, lsblk_text: str | None = None) -> list[DiskInfo]:
    """Group mounts by their top-level physical disk (or loop device).

    Ordering: physical disks first (nvme, then sata/usb ssd/hdd), then loop
    and virtual (no backing block device) groups; mounts within a disk are
    sorted by mountpoint.
    """
    nodes = parse_lsblk_json(lsblk_text if lsblk_text is not None else run_lsblk())
    groups: dict[str, DiskInfo] = {}

    for mount in mounts:
        key = mount.disk_kname
        if key is None:
            loop_node = nodes.get(mount.kname)
            key = loop_node.kname if loop_node is not None and loop_node.type == "loop" else ""

        disk = groups.get(key)
        if disk is None:
            node = nodes.get(key)
            if node is not None:
                disk = DiskInfo(
                    kname=node.kname,
                    path=f"/dev/{node.kname}",
                    model=node.model,
                    size=node.size,
                    transport=node.tran or "",
                    rotational=node.rota,
                    kind=_derive_kind(node.type, node.tran, node.rota),
                )
            else:
                disk = DiskInfo(
                    kname=key,
                    path=f"/dev/{key}" if key else "",
                    model=None,
                    size=0,
                    transport="",
                    rotational=False,
                    kind="virtual",
                )
            groups[key] = disk
        disk.mounts.append(mount)

    for disk in groups.values():
        disk.mounts.sort(key=lambda m: m.mountpoint)

    return sorted(groups.values(), key=lambda d: (_KIND_PRIORITY.get(d.kind, 9), d.kname))


# ---- hotplug monitor --------------------------------------------------------------


class MountMonitor:
    """Watches for block-device hotplug via ``pyudev``, exposing one non-blocking fd.

    ``pyudev`` is imported lazily inside :meth:`start` so this module still
    imports cleanly when it is not installed (see .claude/rules/core-purity.md);
    in that case ``available`` stays False and every method is a safe no-op.
    No threads and no callbacks: the UI service watches :meth:`fileno` with
    ``GLib.io_add_watch`` and drains :meth:`poll` itself on the main loop.
    """

    def __init__(self) -> None:
        self.available = False
        self._monitor: Any = None

    def start(self) -> None:
        try:
            import pyudev
        except ImportError:
            self.available = False
            return
        try:
            context = pyudev.Context()
            monitor = pyudev.Monitor.from_netlink(context)
            monitor.filter_by(subsystem="block")
            monitor.start()
        except Exception:  # noqa: BLE001 - any udev/netlink failure means "unavailable"
            self.available = False
            self._monitor = None
            return
        self._monitor = monitor
        self.available = True

    def fileno(self) -> int:
        if self._monitor is None:
            raise RuntimeError("MountMonitor.start() was not called, or pyudev is unavailable")
        return int(self._monitor.fileno())

    def poll(self) -> list[tuple[str, str]]:
        """Drain pending udev events without blocking."""
        events: list[tuple[str, str]] = []
        if self._monitor is None:
            return events
        while True:
            device = self._monitor.poll(timeout=0)
            if device is None:
                break
            action = str(getattr(device, "action", "") or "")
            devname = str(getattr(device, "sys_name", "") or "")
            events.append((action, devname))
        return events

    def stop(self) -> None:
        self._monitor = None
        self.available = False
