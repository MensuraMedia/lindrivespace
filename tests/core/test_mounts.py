from __future__ import annotations

from pathlib import Path

import psutil
import pytest

from lindrivespace.core.mounts import (
    DEFAULT_HIDDEN_FSTYPES,
    MountMonitor,
    group_by_disk,
    list_mounts,
    parse_lsblk_json,
    parse_mountinfo,
)

FIXTURES = Path(__file__).parent / "fixtures"
MOUNTINFO_TEXT = (FIXTURES / "mountinfo.txt").read_text(encoding="utf-8")
LSBLK_TEXT = (FIXTURES / "lsblk.json").read_text(encoding="utf-8")


# ---- parse_mountinfo --------------------------------------------------------------


def test_parse_mountinfo_basic_fields() -> None:
    rows = parse_mountinfo(MOUNTINFO_TEXT)
    by_mountpoint = {r.mountpoint: r for r in rows}

    root = by_mountpoint["/"]
    assert root.mount_id == 34
    assert root.parent_id == 2
    assert root.maj_min == "259:2"
    assert root.fstype == "ext4"
    assert root.source == "/dev/nvme0n1p2"
    assert root.root == "/"


def test_parse_mountinfo_octal_escape_decodes_space() -> None:
    rows = parse_mountinfo(MOUNTINFO_TEXT)
    mountpoints = [r.mountpoint for r in rows]
    assert "/mnt/My Backup" in mountpoints
    assert not any("\\040" in mp for mp in mountpoints)


def test_parse_mountinfo_bind_detection() -> None:
    rows = parse_mountinfo(MOUNTINFO_TEXT)
    by_mountpoint = {r.mountpoint: r for r in rows}

    bind = by_mountpoint["/mnt/homebind"]
    assert bind.root == "/home"  # not "/" -> a bind mount
    home = by_mountpoint["/home"]
    assert home.root == "/"  # the real mount is not a bind


def test_parse_mountinfo_ignores_blank_lines() -> None:
    rows = parse_mountinfo("\n" + MOUNTINFO_TEXT + "\n\n")
    assert len(rows) == len(parse_mountinfo(MOUNTINFO_TEXT))


# ---- parse_lsblk_json ---------------------------------------------------------------


def test_parse_lsblk_json_flattens_partition_to_disk() -> None:
    nodes = parse_lsblk_json(LSBLK_TEXT)
    assert nodes["nvme0n1p3"].pkname == "nvme0n1"
    assert nodes["nvme0n1p3"].disk_kname == "nvme0n1"
    assert nodes["nvme0n1"].disk_kname == "nvme0n1"  # a disk is its own top
    assert nodes["sda1"].disk_kname == "sda"


def test_parse_lsblk_json_lvm_over_luks_resolves_to_disk() -> None:
    nodes = parse_lsblk_json(LSBLK_TEXT)
    luks = nodes["dm-0"]
    lvm = nodes["dm-1"]
    assert luks.type == "crypt"
    assert lvm.type == "lvm"
    assert luks.disk_kname == "sdc"
    assert lvm.disk_kname == "sdc"
    assert lvm.mountpoint == "/mnt/vault"


def test_parse_lsblk_json_loop_is_its_own_top() -> None:
    nodes = parse_lsblk_json(LSBLK_TEXT)
    assert nodes["loop0"].disk_kname is None
    assert nodes["loop0"].type == "loop"


def test_parse_lsblk_json_transport_and_rota() -> None:
    nodes = parse_lsblk_json(LSBLK_TEXT)
    assert nodes["nvme0n1"].tran == "nvme"
    assert nodes["sdb"].tran == "usb"
    assert nodes["sda"].tran == "sata" and nodes["sda"].rota is False
    assert nodes["sdd"].tran == "sata" and nodes["sdd"].rota is True


def test_parse_lsblk_json_handles_garbage() -> None:
    assert parse_lsblk_json("") == {}
    assert parse_lsblk_json("not json") == {}
    assert parse_lsblk_json("{}") == {}
    assert parse_lsblk_json('{"blockdevices": "nope"}') == {}


# ---- list_mounts ------------------------------------------------------------------


def _fake_partitions() -> list[psutil._common.sdiskpart]:
    rows = [
        ("sysfs", "/sys", "sysfs", "rw,nosuid,nodev,noexec,relatime"),
        ("proc", "/proc", "proc", "rw,nosuid,nodev,noexec,relatime"),
        ("tmpfs", "/run", "tmpfs", "rw,nosuid,nodev,noexec,relatime,size=1319324k"),
        ("/dev/nvme0n1p2", "/", "ext4", "rw,relatime,errors=remount-ro"),
        ("/dev/loop0", "/snap/core22/2411", "squashfs", "ro,nodev,relatime"),
        ("/dev/loop2", "/snap/core24/1587", "squashfs", "ro,nodev,relatime"),
        ("/dev/nvme0n1p3", "/home", "ext4", "rw,relatime"),
        ("/dev/sda1", "/mnt/data", "ext4", "rw,relatime"),
        ("/dev/nvme0n1p1", "/boot/efi", "vfat", "rw,fmask=0077,dmask=0077"),
        ("/dev/sdb1", "/media/user/USBSTICK", "vfat", "rw,nosuid,nodev,relatime,uid=1000,gid=1000"),
        ("/dev/mapper/vgdata-lvroot", "/mnt/vault", "ext4", "rw,relatime"),
        ("/dev/sdd1", "/mnt/My Backup", "ext4", "rw,relatime"),
        ("/dev/nvme0n1p3", "/mnt/homebind", "ext4", "rw,relatime"),
    ]
    return [
        psutil._common.sdiskpart(
            device=device, mountpoint=mp, fstype=fstype, opts=opts, maxfile=255, maxpath=4096
        )
        for device, mp, fstype, opts in rows
    ]


_STATVFS_BY_MOUNTPOINT: dict[str, tuple[int, int, int]] = {
    # mountpoint -> (frsize, blocks, bavail); bfree == bavail here for simplicity
    "/": (4096, 25_000_000, 10_000_000),
    "/home": (4096, 400_000_000, 300_000_000),
    "/boot/efi": (4096, 131_072, 100_000),
    "/mnt/data": (4096, 244_000_000, 100_000_000),
    "/media/user/USBSTICK": (4096, 7_815_000, 2_000_000),
    "/mnt/vault": (4096, 244_000_000, 50_000_000),
    "/mnt/My Backup": (4096, 976_000_000, 900_000_000),
    "/mnt/homebind": (4096, 400_000_000, 300_000_000),
}


class _FakeStatvfsResult:
    def __init__(self, f_frsize: int, f_blocks: int, f_bavail: int) -> None:
        self.f_frsize = f_frsize
        self.f_blocks = f_blocks
        self.f_bavail = f_bavail
        self.f_bfree = f_bavail  # no reserved-for-root distinction needed here


def _fake_statvfs(path: str) -> _FakeStatvfsResult:
    if path not in _STATVFS_BY_MOUNTPOINT:
        raise OSError(f"no fake statvfs for {path}")
    frsize, blocks, bavail = _STATVFS_BY_MOUNTPOINT[path]
    return _FakeStatvfsResult(frsize, blocks, bavail)


def _list_mounts(*, include_hidden: bool = False) -> list:
    return list_mounts(
        include_hidden=include_hidden,
        mountinfo_text=MOUNTINFO_TEXT,
        lsblk_text=LSBLK_TEXT,
        statvfs=_fake_statvfs,  # type: ignore[arg-type]
    )


@pytest.fixture(autouse=True)
def _fake_psutil(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(psutil, "disk_partitions", lambda all=False: _fake_partitions())


def test_list_mounts_hides_squashfs_by_default() -> None:
    mounts = _list_mounts()
    mountpoints = {m.mountpoint for m in mounts}
    assert "/snap/core22/2411" not in mountpoints
    assert "/snap/core24/1587" not in mountpoints
    assert "/sys" not in mountpoints
    assert "/proc" not in mountpoints
    assert "/run" not in mountpoints
    assert "/" in mountpoints
    assert "/home" in mountpoints


def test_list_mounts_include_hidden_reveals_squashfs() -> None:
    mounts = _list_mounts(include_hidden=True)
    mountpoints = {m.mountpoint for m in mounts}
    assert "/snap/core22/2411" in mountpoints
    assert "/sys" in mountpoints
    hidden_entry = next(m for m in mounts if m.mountpoint == "/snap/core22/2411")
    assert hidden_entry.hidden is True


def test_list_mounts_is_sorted_by_mountpoint() -> None:
    mounts = _list_mounts()
    assert [m.mountpoint for m in mounts] == sorted(m.mountpoint for m in mounts)


def test_list_mounts_usage_math_and_percent() -> None:
    mounts = {m.mountpoint: m for m in _list_mounts()}
    root = mounts["/"]
    frsize, blocks, bavail = _STATVFS_BY_MOUNTPOINT["/"]
    assert root.total == frsize * blocks
    assert root.free == frsize * bavail
    assert root.used == root.total - root.free  # bfree == bavail in the fake
    assert root.percent_used == pytest.approx(root.used * 100.0 / root.total)
    assert 0.0 <= root.percent_used <= 100.0


def test_list_mounts_device_and_kname() -> None:
    mounts = {m.mountpoint: m for m in _list_mounts()}
    home = mounts["/home"]
    assert home.device == "/dev/nvme0n1p3"
    assert home.kname == "nvme0n1p3"
    assert home.maj_min == "259:3"
    assert home.disk_kname == "nvme0n1"


def test_list_mounts_lvm_mapper_device_resolves_to_real_kname_and_disk() -> None:
    mounts = {m.mountpoint: m for m in _list_mounts()}
    vault = mounts["/mnt/vault"]
    assert vault.kname == "dm-1"  # not the /dev/mapper/<name> alias
    assert vault.disk_kname == "sdc"  # resolved through crypt -> lvm -> disk


def test_list_mounts_usb_label_and_display_name() -> None:
    mounts = {m.mountpoint: m for m in _list_mounts()}
    usb = mounts["/media/user/USBSTICK"]
    assert usb.label == "USBSTICK"
    assert usb.display_name == "USBSTICK"
    assert usb.uuid == "1234-5678"

    home = mounts["/home"]
    assert home.label is None
    assert home.display_name == "/home"


def test_list_mounts_bind_flag() -> None:
    mounts = {m.mountpoint: m for m in _list_mounts()}
    assert mounts["/mnt/homebind"].is_bind is True
    assert mounts["/home"].is_bind is False
    assert mounts["/"].is_bind is False


def test_list_mounts_mount_id_and_parent_id() -> None:
    mounts = {m.mountpoint: m for m in _list_mounts()}
    home = mounts["/home"]
    assert home.mount_id == 96
    assert home.parent_id == 34


def test_default_hidden_fstypes_used_by_default() -> None:
    assert "squashfs" in DEFAULT_HIDDEN_FSTYPES
    assert "tmpfs" in DEFAULT_HIDDEN_FSTYPES


# ---- group_by_disk ------------------------------------------------------------------


def test_group_by_disk_kind_derivation() -> None:
    mounts = _list_mounts()
    disks = {d.kname: d for d in group_by_disk(mounts, lsblk_text=LSBLK_TEXT)}
    assert disks["nvme0n1"].kind == "nvme"
    assert disks["sda"].kind == "ssd"  # sata, non-rotational
    assert disks["sdb"].kind == "usb"
    assert disks["sdc"].kind == "ssd"  # sata, non-rotational (holds the LUKS/LVM chain)
    assert disks["sdd"].kind == "hdd"  # sata, rotational


def test_group_by_disk_physical_before_loop_and_virtual() -> None:
    mounts = _list_mounts(include_hidden=True)
    disks = group_by_disk(mounts, lsblk_text=LSBLK_TEXT)
    kinds = [d.kind for d in disks]
    physical_kinds = {"nvme", "ssd", "hdd", "usb"}
    first_non_physical = next(i for i, k in enumerate(kinds) if k not in physical_kinds)
    assert all(k in physical_kinds for k in kinds[:first_non_physical])
    assert all(k not in physical_kinds for k in kinds[first_non_physical:])
    # squashfs loops and pseudo mounts (proc/sysfs/tmpfs, no block device) both appear.
    assert "loop" in kinds
    assert "virtual" in kinds


def test_group_by_disk_mounts_sorted_within_disk() -> None:
    mounts = _list_mounts()
    disks = {d.kname: d for d in group_by_disk(mounts, lsblk_text=LSBLK_TEXT)}
    nvme = disks["nvme0n1"]
    mountpoints = [m.mountpoint for m in nvme.mounts]
    assert mountpoints == sorted(mountpoints)
    assert set(mountpoints) == {"/", "/home", "/boot/efi", "/mnt/homebind"}


def test_group_by_disk_lvm_luks_chain_groups_under_physical_disk() -> None:
    mounts = _list_mounts()
    disks = {d.kname: d for d in group_by_disk(mounts, lsblk_text=LSBLK_TEXT)}
    sdc = disks["sdc"]
    assert sdc.model == "Crucial MX500 1TB"
    assert [m.mountpoint for m in sdc.mounts] == ["/mnt/vault"]


def test_group_by_disk_usb_stick_grouping() -> None:
    mounts = _list_mounts()
    disks = {d.kname: d for d in group_by_disk(mounts, lsblk_text=LSBLK_TEXT)}
    sdb = disks["sdb"]
    assert sdb.transport == "usb"
    assert sdb.model == "Kingston DataTraveler 3.0"
    assert [m.mountpoint for m in sdb.mounts] == ["/media/user/USBSTICK"]


# ---- live system test ---------------------------------------------------------------


def test_list_mounts_live_system_has_root() -> None:
    """No fixtures: exercise the real psutil/mountinfo/lsblk on this machine."""
    mounts = list_mounts()
    assert any(m.mountpoint == "/" for m in mounts)


# ---- MountMonitor -------------------------------------------------------------------


def test_mount_monitor_lifecycle_does_not_raise() -> None:
    monitor = MountMonitor()
    monitor.start()
    try:
        events = monitor.poll()
        assert isinstance(events, list)
        if monitor.available:
            assert isinstance(monitor.fileno(), int)
    finally:
        monitor.stop()
    assert monitor.available is False


def test_mount_monitor_poll_before_start_is_empty() -> None:
    monitor = MountMonitor()
    assert monitor.poll() == []
    monitor.stop()  # must not raise even though start() was never called
