from __future__ import annotations

from pathlib import Path

from lindrivespace.core import hardware as hw

FIXTURES = Path(__file__).parent / "fixtures" / "hardware"
CPUINFO_TEXT = (FIXTURES / "cpuinfo").read_text(encoding="utf-8")
MEMINFO_TEXT = (FIXTURES / "meminfo").read_text(encoding="utf-8")
OS_RELEASE_TEXT = (FIXTURES / "os-release").read_text(encoding="utf-8")
FILESYSTEMS_TEXT = (FIXTURES / "filesystems").read_text(encoding="utf-8")
MODULES_TEXT = (FIXTURES / "modules").read_text(encoding="utf-8")
LSPCI_TEXT = (FIXTURES / "lspci.txt").read_text(encoding="utf-8")
LSBLK_TEXT = (FIXTURES / "lsblk.json").read_text(encoding="utf-8")
DISKSTATS_1 = (FIXTURES / "diskstats.sample1").read_text(encoding="utf-8")
DISKSTATS_2 = (FIXTURES / "diskstats.sample2").read_text(encoding="utf-8")


# ---- parse_os_release / chassis_type_name / parse_uptime --------------------------------


def test_parse_os_release_pretty_name() -> None:
    values = hw.parse_os_release(OS_RELEASE_TEXT)
    assert values["PRETTY_NAME"] == "Linux Mint 22.3"
    assert values["ID"] == "linuxmint"


def test_parse_os_release_ignores_blank_and_comment_lines() -> None:
    values = hw.parse_os_release("\n# comment\nFOO=bar\n")
    assert values == {"FOO": "bar"}


def test_chassis_type_name_known_and_unknown() -> None:
    assert hw.chassis_type_name("35") == "mini-pc"
    assert hw.chassis_type_name("9") == "laptop"
    assert hw.chassis_type_name("3") == "desktop"
    assert hw.chassis_type_name(None) == "unknown"
    assert hw.chassis_type_name("999") == "unknown"


def test_parse_uptime() -> None:
    assert hw.parse_uptime("12345.67 98765.43\n") == 12345.67
    assert hw.parse_uptime("not a number") == 0.0
    assert hw.parse_uptime("") == 0.0


# ---- parse_cpuinfo ------------------------------------------------------------------------


def test_parse_cpuinfo_from_fixture() -> None:
    cpu = hw.parse_cpuinfo(CPUINFO_TEXT)
    assert cpu.model == "AMD Ryzen 5 5560U with Radeon Graphics"
    assert cpu.vendor == "AuthenticAMD"
    assert cpu.sockets == 1
    assert cpu.cores == 6
    assert cpu.threads == 12
    assert cpu.max_mhz is not None and cpu.max_mhz > 0
    assert "aes" in cpu.flags_of_interest
    assert "avx2" in cpu.flags_of_interest
    assert "svm" in cpu.flags_of_interest


def test_parse_cpuinfo_empty_text_is_safe() -> None:
    cpu = hw.parse_cpuinfo("")
    assert cpu.model == "Unknown"
    assert cpu.vendor == "Unknown"
    assert cpu.threads == 0
    assert cpu.max_mhz is None
    assert cpu.flags_of_interest == ()


# ---- parse_meminfo ------------------------------------------------------------------------


def test_parse_meminfo_from_fixture() -> None:
    mem = hw.parse_meminfo(MEMINFO_TEXT)
    assert mem.total == 13193212 * 1024
    assert mem.swap_total == 0
    assert mem.swap_free == 0
    assert mem.available > 0


def test_parse_meminfo_falls_back_to_memfree() -> None:
    mem = hw.parse_meminfo("MemTotal:  1000 kB\nMemFree:  200 kB\n")
    assert mem.available == 200 * 1024


# ---- parse_lspci_controllers ---------------------------------------------------------------


def test_parse_lspci_controllers_from_fixture() -> None:
    controllers = hw.parse_lspci_controllers(LSPCI_TEXT)
    kinds = {c.kind for c in controllers}
    assert "NVMe" in kinds
    assert "SATA/AHCI" in kinds
    assert "USB" in kinds
    nvme = next(c for c in controllers if c.kind == "NVMe")
    assert nvme.slot == "03:00.0"
    assert "Sandisk" in nvme.vendor
    # Non-storage classes (Host bridge, IOMMU, VGA, Audio, ...) must be excluded.
    assert all(c.kind != "Other" or "storage" in c.kind.lower() for c in controllers)


def test_parse_lspci_controllers_skips_non_storage_classes() -> None:
    text = '00:02.0 "VGA compatible controller" "Acme" "Widget GPU"'
    assert hw.parse_lspci_controllers(text) == ()


def test_collect_controllers_empty_when_lspci_missing() -> None:
    assert hw.collect_controllers(lspci_text=None) is not None  # never raises
    assert hw.collect_controllers(lspci_text="") == ()


# ---- parse_filesystems / parse_modules --------------------------------------------------


def test_parse_filesystems_splits_pseudo() -> None:
    fs, pseudo = hw.parse_filesystems(FILESYSTEMS_TEXT)
    assert "ext4" in fs
    assert "btrfs" in fs
    assert "tmpfs" in pseudo
    assert "sysfs" in pseudo
    assert "tmpfs" not in fs


def test_parse_modules_first_column() -> None:
    names = hw.parse_modules(MODULES_TEXT)
    assert "veth" in names
    assert "zfs" in names


# ---- diskstats / io_rates ------------------------------------------------------------------


def test_parse_diskstats_from_fixture() -> None:
    stats = hw.parse_diskstats(DISKSTATS_1)
    assert "sda" in stats
    assert "nvme0n1" in stats
    assert stats["sda"].reads_completed > 0


def test_io_rates_between_two_samples() -> None:
    prev = hw.parse_diskstats(DISKSTATS_1)
    curr = hw.parse_diskstats(DISKSTATS_2)
    rates = hw.io_rates(prev, curr, interval_s=1.0)
    by_name = {r.kname: r for r in rates}
    assert "nvme0n1" in by_name
    rate = by_name["nvme0n1"]
    assert rate.read_bytes_per_s >= 0
    assert rate.utilization_pct >= 0


def test_io_rates_zero_interval_returns_empty() -> None:
    prev = hw.parse_diskstats(DISKSTATS_1)
    curr = hw.parse_diskstats(DISKSTATS_2)
    assert hw.io_rates(prev, curr, interval_s=0.0) == ()


def test_io_rates_skips_unknown_devices() -> None:
    prev: dict[str, hw.IoStats] = {}
    curr = hw.parse_diskstats(DISKSTATS_2)
    assert hw.io_rates(prev, curr, interval_s=1.0) == ()


# ---- lsblk-based disk parsing ---------------------------------------------------------------


def test_parse_lsblk_disks_json_from_fixture() -> None:
    devices = hw.parse_lsblk_disks_json(LSBLK_TEXT)
    disk_names = {d["name"] for d in devices if d.get("type") == "disk"}
    assert "sda" in disk_names
    assert "nvme0n1" in disk_names


def test_mask_serial() -> None:
    assert hw._mask_serial("S6PYNS0T123456") == "…3456"
    assert hw._mask_serial(None) == "—"
    assert hw._mask_serial("") == "—"
    assert hw._mask_serial("abc") == "—"


def test_collect_disks_from_fixture(tmp_path: Path) -> None:
    sys_root = tmp_path / "sys"
    for kname in ("sda", "nvme0n1"):
        queue_dir = sys_root / "block" / kname / "queue"
        queue_dir.mkdir(parents=True)
        (queue_dir / "scheduler").write_text("none [mq-deadline] \n")
        (queue_dir / "discard_granularity").write_text("512\n")
        (queue_dir / "write_cache").write_text("write back\n")

    disks = hw.collect_disks(sys_root=str(sys_root), lsblk_text=LSBLK_TEXT)
    by_kname = {d.kname: d for d in disks}
    assert "sda" in by_kname
    assert "nvme0n1" in by_kname

    sda = by_kname["sda"]
    assert sda.transport == "sata"
    assert sda.scheduler == "mq-deadline"
    assert sda.discard_supported is True
    assert sda.write_cache == "write back"
    assert len(sda.partitions) >= 1
    assert sda.serial_masked == "—" or sda.serial_masked.startswith("…")

    nvme = by_kname["nvme0n1"]
    assert nvme.transport == "nvme"
    assert len(nvme.partitions) == 3


def test_collect_disks_reads_nvme_firmware(tmp_path: Path) -> None:
    sys_root = tmp_path / "sys"
    nvme_dir = sys_root / "class" / "nvme" / "nvme0"
    nvme_dir.mkdir(parents=True)
    (nvme_dir / "firmware_rev").write_text("731100WD\n")

    disks = hw.collect_disks(sys_root=str(sys_root), lsblk_text=LSBLK_TEXT)
    nvme = next(d for d in disks if d.kname == "nvme0n1")
    assert nvme.nvme_firmware == "731100WD"


def test_read_scheduler_handles_hyphenated_names(tmp_path: Path) -> None:
    sys_root = tmp_path / "sys"
    queue_dir = sys_root / "block" / "sda" / "queue"
    queue_dir.mkdir(parents=True)
    (queue_dir / "scheduler").write_text("none [mq-deadline] \n")
    assert hw._read_scheduler(str(sys_root), "sda") == "mq-deadline"


# ---- supported_drive_types -----------------------------------------------------------------


def test_supported_drive_types_from_controllers_and_disks() -> None:
    controllers = hw.parse_lspci_controllers(LSPCI_TEXT)
    disks = hw.collect_disks(sys_root="/nonexistent", lsblk_text=LSBLK_TEXT)
    types = hw.supported_drive_types(controllers, disks, modules=())
    assert "NVMe" in types
    assert "SATA/AHCI" in types
    assert "USB mass storage" in types


def test_supported_drive_types_from_modules_only() -> None:
    types = hw.supported_drive_types((), (), modules=("mmc_block", "ahci"))
    assert "SD/MMC" in types
    assert "SATA/AHCI" in types


# ---- collect() / to_text() -- integration on the real machine ------------------------------


def test_collect_on_real_machine_has_kernel_and_disk() -> None:
    report = hw.collect()
    assert report.system.kernel
    assert report.system.hostname
    assert len(report.disks) >= 1
    assert isinstance(report.notes, tuple)
    assert len(report.notes) >= 1  # at least the "no root" note


def test_collect_never_raises_with_bogus_roots() -> None:
    # sys_root/proc_root only gate /sys and /proc reads; lsblk/lspci still run for
    # real, so this asserts "never raises and returns a well-formed report", not
    # that every field is empty.
    report = hw.collect(sys_root="/does/not/exist", proc_root="/does/not/exist")
    assert report.system is not None
    assert report.system.uptime_seconds == 0.0  # /proc/uptime unreadable under the bogus root
    assert isinstance(report.disks, tuple)
    assert isinstance(report.controllers, tuple)
    assert report.filesystems == ()
    assert report.pseudo_filesystems == ()


def test_to_text_contains_hostname() -> None:
    report = hw.collect()
    text = hw.to_text(report)
    assert report.system.hostname in text
    assert "Hardware report" in text
    assert "Storage controllers" in text
    assert "Disks" in text


def test_to_text_masks_serials_not_full_value() -> None:
    report = hw.collect()
    text = hw.to_text(report)
    for disk in report.disks:
        assert disk.serial_masked in text
