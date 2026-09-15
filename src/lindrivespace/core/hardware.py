"""Hardware & I/O introspection: what the kernel knows about this machine.

Pure Python (stdlib only — see .claude/rules/core-purity.md); every collector
reads from injectable roots (``sys_root``, ``proc_root``) or injectable text so
it can be unit-tested against the canned fixtures in
``tests/core/fixtures/hardware/`` without touching the real machine, and every
parser is defensive: malformed or missing input degrades to empty/"Unknown"
fields rather than raising. :func:`collect` wraps each collector in its own
``try/except`` so a single failure becomes a note in ``HardwareReport.notes``
instead of aborting the whole report.

Everything here runs unprivileged. Fields that would need root (SMART data,
full serial numbers, some temperature sensors) are simply left out or masked;
see the "never asks for elevated privileges" note :func:`collect` always adds.
"""

from __future__ import annotations

import glob
import json
import os
import re
import socket
import subprocess
from dataclasses import dataclass, replace
from typing import Any

# ---- dataclasses --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SystemInfo:
    hostname: str
    distro: str
    kernel: str
    arch: str
    uptime_seconds: float
    chassis_type: str
    virtualization: str


@dataclass(frozen=True, slots=True)
class BoardInfo:
    sys_vendor: str | None
    product_name: str | None
    product_version: str | None
    board_vendor: str | None
    board_name: str | None
    board_version: str | None
    bios_vendor: str | None
    bios_version: str | None
    bios_date: str | None


@dataclass(frozen=True, slots=True)
class CpuInfo:
    model: str
    vendor: str
    sockets: int
    cores: int
    threads: int
    max_mhz: float | None
    flags_of_interest: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MemoryInfo:
    total: int
    available: int
    swap_total: int
    swap_free: int


@dataclass(frozen=True, slots=True)
class StorageController:
    slot: str
    kind: str  # "NVMe" | "SATA/AHCI" | "RAID" | "SAS/SCSI" | "USB" | "SD/MMC" | "IDE" | "Other"
    vendor: str
    device: str


@dataclass(frozen=True, slots=True)
class DiskHardware:
    kname: str
    path: str
    model: str | None
    serial_masked: str  # last 4 chars only ("…AB12"), or "—"
    size: int
    transport: str  # nvme/sata/usb/mmc/virtio/...
    rotational: bool
    removable: bool
    logical_block: int
    physical_block: int
    scheduler: str | None
    queue_depth: int | None
    discard_supported: bool
    write_cache: str | None
    nvme_firmware: str | None
    nvme_temperature: float | None  # degrees C
    link: str | None
    partitions: tuple[tuple[str, int, str | None, str | None], ...]  # name, size, fstype, mount


@dataclass(frozen=True, slots=True)
class IoStats:
    kname: str
    reads_completed: int
    reads_sectors: int
    writes_completed: int
    writes_sectors: int
    in_flight: int
    io_ticks_ms: int
    time_in_queue_ms: int


@dataclass(frozen=True, slots=True)
class IoRate:
    kname: str
    read_bytes_per_s: float
    write_bytes_per_s: float
    iops_r: float
    iops_w: float
    utilization_pct: float


@dataclass(frozen=True, slots=True)
class HardwareReport:
    system: SystemInfo
    board: BoardInfo
    cpu: CpuInfo
    memory: MemoryInfo
    controllers: tuple[StorageController, ...]
    disks: tuple[DiskHardware, ...]
    filesystems: tuple[str, ...]
    pseudo_filesystems: tuple[str, ...]
    drive_types: tuple[str, ...]
    notes: tuple[str, ...]


_SECTOR_SIZE = 512

# ---- low-level read helpers -----------------------------------------------------


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def _read_first_line(path: str) -> str | None:
    text = _read_text(path)
    if text is None:
        return None
    line = text.strip()
    return line or None


def _read_int(path: str) -> int | None:
    text = _read_first_line(path)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _run(cmd: list[str], timeout: float = 3.0) -> str | None:
    """Run ``cmd``; None on any failure or non-zero exit."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout


def _detect_virt_output() -> str | None:
    """``systemd-detect-virt`` prints its answer even on its "no virt" exit(1)."""
    try:
        result = subprocess.run(
            ["systemd-detect-virt"], capture_output=True, text=True, timeout=3, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = result.stdout.strip()
    return text or None


# ---- coercion helpers (lsblk JSON is untyped) ------------------------------------


def _clean_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return bool(value)


# ---- system ---------------------------------------------------------------------

# SMBIOS chassis type codes (DMTF spec), collapsed to the words the UI shows.
_CHASSIS_TYPES: dict[str, str] = {
    "1": "other",
    "2": "unknown",
    "3": "desktop",
    "4": "desktop",
    "5": "desktop",
    "6": "desktop",
    "7": "desktop",
    "8": "laptop",
    "9": "laptop",
    "10": "notebook",
    "11": "handheld",
    "12": "docking-station",
    "13": "all-in-one",
    "14": "notebook",
    "15": "desktop",
    "16": "desktop",
    "17": "server",
    "18": "expansion-chassis",
    "19": "sub-chassis",
    "20": "bus-expansion-chassis",
    "21": "peripheral-chassis",
    "22": "raid-chassis",
    "23": "server",
    "24": "desktop",
    "25": "multi-system-chassis",
    "28": "blade",
    "29": "blade-enclosure",
    "30": "tablet",
    "31": "convertible",
    "32": "detachable",
    "33": "iot-gateway",
    "34": "embedded-pc",
    "35": "mini-pc",
    "36": "stick-pc",
    "30001": "vm",  # never emitted by real firmware; kept for tests/back-compat
}


def chassis_type_name(raw: str | None) -> str:
    """Map a raw ``/sys/class/dmi/id/chassis_type`` code to a display word."""
    if raw is None:
        return "unknown"
    return _CHASSIS_TYPES.get(raw.strip(), "unknown")


def parse_os_release(text: str) -> dict[str, str]:
    """Parse ``/etc/os-release`` ``KEY=value`` (optionally quoted) lines."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        result[key.strip()] = value
    return result


def parse_uptime(text: str) -> float:
    """Parse the first field of ``/proc/uptime`` (seconds, float)."""
    try:
        return float(text.split()[0])
    except (ValueError, IndexError):
        return 0.0


def collect_system(
    sys_root: str = "/sys",
    proc_root: str = "/proc",
    *,
    os_release_path: str = "/etc/os-release",
    virt_text: str | None = None,
) -> SystemInfo:
    hostname = socket.gethostname()
    os_release_text = _read_text(os_release_path) or ""
    distro = parse_os_release(os_release_text).get("PRETTY_NAME", "Unknown")

    uname_result = os.uname()
    kernel = uname_result.release
    arch = uname_result.machine

    uptime_text = _read_text(f"{proc_root}/uptime")
    uptime_seconds = parse_uptime(uptime_text) if uptime_text else 0.0

    chassis_raw = _read_first_line(f"{sys_root}/class/dmi/id/chassis_type")
    chassis_type = chassis_type_name(chassis_raw)

    if virt_text is None:
        virt_text = _detect_virt_output()
    virtualization = (virt_text or "none").strip() or "none"

    return SystemInfo(
        hostname=hostname,
        distro=distro,
        kernel=kernel,
        arch=arch,
        uptime_seconds=uptime_seconds,
        chassis_type=chassis_type,
        virtualization=virtualization,
    )


# ---- motherboard / firmware ------------------------------------------------------

# Deliberately excludes *_serial and product_uuid (never read/shown, even
# though root is not required to read them on Mint) per the WP16 spec.
_DMI_FIELDS: tuple[str, ...] = (
    "sys_vendor",
    "product_name",
    "product_version",
    "board_vendor",
    "board_name",
    "board_version",
    "bios_vendor",
    "bios_version",
    "bios_date",
)


def collect_board(sys_root: str = "/sys") -> BoardInfo:
    base = f"{sys_root}/class/dmi/id"
    values = {name: _read_first_line(f"{base}/{name}") for name in _DMI_FIELDS}
    return BoardInfo(
        sys_vendor=values["sys_vendor"],
        product_name=values["product_name"],
        product_version=values["product_version"],
        board_vendor=values["board_vendor"],
        board_name=values["board_name"],
        board_version=values["board_version"],
        bios_vendor=values["bios_vendor"],
        bios_version=values["bios_version"],
        bios_date=values["bios_date"],
    )


# ---- CPU --------------------------------------------------------------------------

_FLAGS_OF_INTEREST: tuple[str, ...] = (
    "aes",
    "avx",
    "avx2",
    "avx512f",
    "sse4_1",
    "sse4_2",
    "sha_ni",
    "vmx",
    "svm",
)


def parse_cpuinfo(text: str) -> CpuInfo:
    model = ""
    vendor = ""
    physical_ids: set[str] = set()
    cores_per_phys: dict[str, set[str]] = {}
    threads = 0
    max_mhz = 0.0
    flags: tuple[str, ...] = ()

    for block in text.split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
        if not fields:
            continue
        if "processor" in fields:
            threads += 1
        if not model and "model name" in fields:
            model = fields["model name"]
        if not vendor and "vendor_id" in fields:
            vendor = fields["vendor_id"]
        phys = fields.get("physical id")
        core = fields.get("core id")
        if phys is not None:
            physical_ids.add(phys)
            if core is not None:
                cores_per_phys.setdefault(phys, set()).add(core)
        mhz_text = fields.get("cpu MHz")
        if mhz_text:
            try:
                max_mhz = max(max_mhz, float(mhz_text))
            except ValueError:
                pass
        if not flags:
            raw_flags = fields.get("flags") or fields.get("Features")
            if raw_flags:
                flags = tuple(raw_flags.split())

    sockets = len(physical_ids) or (1 if threads else 0)
    cores = sum(len(v) for v in cores_per_phys.values()) or threads
    flags_of_interest = tuple(f for f in _FLAGS_OF_INTEREST if f in flags)

    return CpuInfo(
        model=model or "Unknown",
        vendor=vendor or "Unknown",
        sockets=sockets,
        cores=cores,
        threads=threads,
        max_mhz=max_mhz if max_mhz > 0 else None,
        flags_of_interest=flags_of_interest,
    )


def _parse_lscpu_fields(text: str) -> dict[str, str]:
    try:
        data: Any = json.loads(text)
    except ValueError:
        return {}
    entries = data.get("lscpu") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return {}
    out: dict[str, str] = {}
    for item in entries:
        if not isinstance(item, dict):
            continue
        field_name = str(item.get("field", "")).rstrip(":").strip()
        value = item.get("data")
        if field_name and value is not None:
            out[field_name] = str(value)
    return out


def collect_cpu(proc_root: str = "/proc", *, lscpu_text: str | None = None) -> CpuInfo:
    cpuinfo_text = _read_text(f"{proc_root}/cpuinfo") or ""
    info = parse_cpuinfo(cpuinfo_text)

    if lscpu_text is None:
        lscpu_text = _run(["lscpu", "-J"])
    if not lscpu_text:
        return info

    fields = _parse_lscpu_fields(lscpu_text)
    sockets = info.sockets
    cores = info.cores
    max_mhz = info.max_mhz
    try:
        if "Socket(s)" in fields:
            sockets = int(fields["Socket(s)"])
    except ValueError:
        pass
    try:
        if "Core(s) per socket" in fields:
            cores = sockets * int(fields["Core(s) per socket"])
    except ValueError:
        pass
    if "CPU max MHz" in fields:
        try:
            max_mhz = float(fields["CPU max MHz"])
        except ValueError:
            pass
    return replace(
        info, sockets=sockets or info.sockets, cores=cores or info.cores, max_mhz=max_mhz
    )


# ---- memory -----------------------------------------------------------------------


def parse_meminfo(text: str) -> MemoryInfo:
    values: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, rest = line.partition(":")
        parts = rest.strip().split()
        if not parts:
            continue
        try:
            values[key.strip()] = int(parts[0])
        except ValueError:
            continue

    def _bytes(key: str) -> int:
        return values.get(key, 0) * 1024

    return MemoryInfo(
        total=_bytes("MemTotal"),
        available=_bytes("MemAvailable") or _bytes("MemFree"),
        swap_total=_bytes("SwapTotal"),
        swap_free=_bytes("SwapFree"),
    )


def collect_memory(proc_root: str = "/proc") -> MemoryInfo:
    text = _read_text(f"{proc_root}/meminfo") or ""
    return parse_meminfo(text)


# ---- storage controllers (lspci -mm) ----------------------------------------------

_CONTROLLER_KIND_MAP: tuple[tuple[str, str], ...] = (
    ("Non-Volatile memory controller", "NVMe"),
    ("SATA controller", "SATA/AHCI"),
    ("RAID bus controller", "RAID"),
    ("SAS controller", "SAS/SCSI"),
    ("SCSI storage controller", "SAS/SCSI"),
    ("USB controller", "USB"),
    ("SD Host controller", "SD/MMC"),
    ("MMC/SD/SDIO controller", "SD/MMC"),
    ("IDE interface", "IDE"),
    ("Mass storage controller", "Other"),
)

_QUOTED_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _classify_controller(class_str: str) -> str | None:
    for needle, kind in _CONTROLLER_KIND_MAP:
        if needle in class_str:
            return kind
    return None


def parse_lspci_controllers(text: str) -> tuple[StorageController, ...]:
    """Parse ``lspci -mm`` output, keeping only storage-relevant device classes."""
    out: list[StorageController] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        slot = parts[0]
        groups = _QUOTED_RE.findall(parts[1])
        if len(groups) < 3:
            continue
        class_str, vendor, device = groups[0], groups[1], groups[2]
        kind = _classify_controller(class_str)
        if kind is None:
            continue
        out.append(StorageController(slot=slot, kind=kind, vendor=vendor, device=device))
    return tuple(out)


def collect_controllers(*, lspci_text: str | None = None) -> tuple[StorageController, ...]:
    if lspci_text is None:
        lspci_text = _run(["lspci", "-mm"])
    if not lspci_text:
        return ()
    return parse_lspci_controllers(lspci_text)


# ---- disks (lsblk -J -b + /sys) ---------------------------------------------------

_DISK_LSBLK_COLUMNS = (
    "NAME,KNAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,MODEL,SERIAL,ROTA,TRAN,RM,LOG-SEC,PHY-SEC"
)
_NVME_CTRL_RE = re.compile(r"^(nvme\d+)")
_SCHED_ACTIVE_RE = re.compile(r"\[([\w-]+)\]")


def _run_lsblk_disks() -> str:
    return _run(["lsblk", "-J", "-b", "-o", _DISK_LSBLK_COLUMNS]) or "{}"


def parse_lsblk_disks_json(text: str) -> list[dict[str, Any]]:
    try:
        data: Any = json.loads(text) if text.strip() else {}
    except ValueError:
        data = {}
    devices = data.get("blockdevices") if isinstance(data, dict) else None
    if not isinstance(devices, list):
        return []
    return [d for d in devices if isinstance(d, dict)]


def _mask_serial(serial: object) -> str:
    text = _clean_str(serial)
    if not text or len(text) <= 4:
        return "—"
    return f"…{text[-4:]}"


def _guess_transport(kname: str) -> str:
    if kname.startswith("nvme"):
        return "nvme"
    if kname.startswith("mmcblk"):
        return "mmc"
    if kname.startswith("vd"):
        return "virtio"
    if kname.startswith("xvd"):
        return "xen"
    return ""


def _read_scheduler(sys_root: str, kname: str) -> str | None:
    text = _read_first_line(f"{sys_root}/block/{kname}/queue/scheduler")
    if text is None:
        return None
    match = _SCHED_ACTIVE_RE.search(text)
    if match:
        return match.group(1)
    parts = text.split()
    return parts[0] if parts else None


def _nvme_controller(kname: str) -> str | None:
    match = _NVME_CTRL_RE.match(kname)
    return match.group(1) if match else None


def _read_nvme_temperature(sys_root: str, ctrl: str) -> float | None:
    patterns = (
        f"{sys_root}/class/nvme/{ctrl}/hwmon*/temp1_input",
        f"{sys_root}/class/nvme/{ctrl}/device/hwmon*/temp1_input",
    )
    for pattern in patterns:
        for match in sorted(glob.glob(pattern)):
            raw = _read_int(match)
            if raw is not None:
                return raw / 1000.0
    return None


def _sata_link_speed(sys_root: str, kname: str) -> str | None:
    device_path = f"{sys_root}/block/{kname}/device"
    real = os.path.realpath(device_path)
    match = re.search(r"/(link\d+)(?:/|$)", real)
    if not match:
        return None
    return _read_first_line(f"{sys_root}/class/ata_link/{match.group(1)}/sata_spd")


def _disk_link(sys_root: str, kname: str, transport: str) -> str | None:
    if transport == "nvme" or kname.startswith("nvme"):
        ctrl = _nvme_controller(kname)
        if ctrl is None:
            return None
        speed = _read_first_line(f"{sys_root}/class/nvme/{ctrl}/device/current_link_speed")
        width = _read_first_line(f"{sys_root}/class/nvme/{ctrl}/device/current_link_width")
        if speed and width:
            return f"{speed} x{width}"
        return speed
    if transport in ("sata", "ata"):
        return _sata_link_speed(sys_root, kname)
    return None


def collect_disks(
    sys_root: str = "/sys", *, lsblk_text: str | None = None
) -> tuple[DiskHardware, ...]:
    if lsblk_text is None:
        lsblk_text = _run_lsblk_disks()
    disks: list[DiskHardware] = []
    for node in parse_lsblk_disks_json(lsblk_text):
        if node.get("type") != "disk":
            continue
        kname = str(node.get("kname") or node.get("name") or "")
        if not kname:
            continue

        transport = _clean_str(node.get("tran")) or _guess_transport(kname)
        logical_block = _as_int(node.get("log-sec")) or 512
        physical_block = _as_int(node.get("phy-sec")) or logical_block

        partitions: list[tuple[str, int, str | None, str | None]] = []
        for child in node.get("children") or []:
            if not isinstance(child, dict) or child.get("type") != "part":
                continue
            partitions.append(
                (
                    str(child.get("kname") or child.get("name") or ""),
                    _as_int(child.get("size")),
                    _clean_str(child.get("fstype")),
                    _clean_str(child.get("mountpoint")),
                )
            )

        discard_granularity = _read_int(f"{sys_root}/block/{kname}/queue/discard_granularity")
        nvme_firmware: str | None = None
        nvme_temperature: float | None = None
        if kname.startswith("nvme"):
            ctrl = _nvme_controller(kname)
            if ctrl is not None:
                nvme_firmware = _read_first_line(f"{sys_root}/class/nvme/{ctrl}/firmware_rev")
                nvme_temperature = _read_nvme_temperature(sys_root, ctrl)

        disks.append(
            DiskHardware(
                kname=kname,
                path=f"/dev/{kname}",
                model=_clean_str(node.get("model")),
                serial_masked=_mask_serial(node.get("serial")),
                size=_as_int(node.get("size")),
                transport=transport,
                rotational=_as_bool(node.get("rota")),
                removable=_as_bool(node.get("rm")),
                logical_block=logical_block,
                physical_block=physical_block,
                scheduler=_read_scheduler(sys_root, kname),
                queue_depth=_read_int(f"{sys_root}/block/{kname}/device/queue_depth"),
                discard_supported=discard_granularity is not None and discard_granularity > 0,
                write_cache=_read_first_line(f"{sys_root}/block/{kname}/queue/write_cache"),
                nvme_firmware=nvme_firmware,
                nvme_temperature=nvme_temperature,
                link=_disk_link(sys_root, kname, transport),
                partitions=tuple(partitions),
            )
        )
    return tuple(disks)


# ---- I/O stats (/proc/diskstats) --------------------------------------------------


def parse_diskstats(text: str) -> dict[str, IoStats]:
    out: dict[str, IoStats] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 14:
            continue
        name = parts[2]
        try:
            out[name] = IoStats(
                kname=name,
                reads_completed=int(parts[3]),
                reads_sectors=int(parts[5]),
                writes_completed=int(parts[7]),
                writes_sectors=int(parts[9]),
                in_flight=int(parts[11]),
                io_ticks_ms=int(parts[12]),
                time_in_queue_ms=int(parts[13]),
            )
        except (ValueError, IndexError):
            continue
    return out


def sample_io(proc_root: str = "/proc") -> dict[str, IoStats]:
    text = _read_text(f"{proc_root}/diskstats") or ""
    return parse_diskstats(text)


def io_rates(
    prev: dict[str, IoStats], curr: dict[str, IoStats], interval_s: float
) -> tuple[IoRate, ...]:
    """Compute per-device rates between two :func:`sample_io` snapshots."""
    if interval_s <= 0:
        return ()
    out: list[IoRate] = []
    for name, c in curr.items():
        p = prev.get(name)
        if p is None:
            continue
        d_read_sectors = max(0, c.reads_sectors - p.reads_sectors)
        d_write_sectors = max(0, c.writes_sectors - p.writes_sectors)
        d_reads = max(0, c.reads_completed - p.reads_completed)
        d_writes = max(0, c.writes_completed - p.writes_completed)
        d_ticks = max(0, c.io_ticks_ms - p.io_ticks_ms)
        out.append(
            IoRate(
                kname=name,
                read_bytes_per_s=(d_read_sectors * _SECTOR_SIZE) / interval_s,
                write_bytes_per_s=(d_write_sectors * _SECTOR_SIZE) / interval_s,
                iops_r=d_reads / interval_s,
                iops_w=d_writes / interval_s,
                utilization_pct=min(100.0, (d_ticks / (interval_s * 1000.0)) * 100.0),
            )
        )
    return tuple(out)


# ---- filesystems & modules ---------------------------------------------------------


def parse_filesystems(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split ``/proc/filesystems`` into (real filesystems, pseudo/"nodev" ones)."""
    fs: list[str] = []
    pseudo: list[str] = []
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "nodev":
            if len(parts) > 1:
                pseudo.append(parts[1])
        else:
            fs.append(parts[0])
    return tuple(fs), tuple(pseudo)


def parse_modules(text: str) -> tuple[str, ...]:
    """Module names (first column) from ``/proc/modules``."""
    names: list[str] = []
    for line in text.splitlines():
        parts = line.split()
        if parts:
            names.append(parts[0])
    return tuple(names)


_MODULE_DRIVE_MAP: tuple[tuple[str, str], ...] = (
    ("nvme", "NVMe"),
    ("ahci", "SATA/AHCI"),
    ("usb_storage", "USB mass storage"),
    ("uas", "USB mass storage"),
    ("mmc_block", "SD/MMC"),
    ("virtio_blk", "Virtio block"),
    ("sd_mod", "SCSI/SATA disk"),
)

_TRANSPORT_DRIVE_MAP: dict[str, str] = {
    "nvme": "NVMe",
    "sata": "SATA/AHCI",
    "ata": "SATA/AHCI",
    "usb": "USB mass storage",
    "mmc": "SD/MMC",
    "virtio": "Virtio block",
}


def supported_drive_types(
    controllers: tuple[StorageController, ...],
    disks: tuple[DiskHardware, ...],
    modules: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Derive drive-type labels from controllers seen, transports in use, and loaded modules."""
    found: set[str] = set()
    for controller in controllers:
        if controller.kind == "USB":
            found.add("USB mass storage")
        elif controller.kind != "Other":
            found.add(controller.kind)
    for disk in disks:
        label = _TRANSPORT_DRIVE_MAP.get(disk.transport.lower())
        if label:
            found.add(label)
    module_set = set(modules)
    for module_name, label in _MODULE_DRIVE_MAP:
        if module_name in module_set:
            found.add(label)
    return tuple(sorted(found))


# ---- top-level collection -----------------------------------------------------------


def collect(sys_root: str = "/sys", proc_root: str = "/proc") -> HardwareReport:
    """Collect the full report. Never raises: a failed collector becomes a note."""
    notes: list[str] = []

    try:
        system = collect_system(sys_root=sys_root, proc_root=proc_root)
    except Exception as exc:  # noqa: BLE001 - one collector must never sink the report
        notes.append(f"System info unavailable: {exc}")
        system = SystemInfo(
            hostname="",
            distro="Unknown",
            kernel="",
            arch="",
            uptime_seconds=0.0,
            chassis_type="unknown",
            virtualization="none",
        )

    try:
        board = collect_board(sys_root=sys_root)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Motherboard info unavailable: {exc}")
        board = BoardInfo(None, None, None, None, None, None, None, None, None)

    try:
        cpu = collect_cpu(proc_root=proc_root)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"CPU info unavailable: {exc}")
        cpu = CpuInfo(
            model="Unknown",
            vendor="Unknown",
            sockets=0,
            cores=0,
            threads=0,
            max_mhz=None,
            flags_of_interest=(),
        )

    try:
        memory = collect_memory(proc_root=proc_root)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Memory info unavailable: {exc}")
        memory = MemoryInfo(total=0, available=0, swap_total=0, swap_free=0)

    try:
        controllers = collect_controllers()
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Storage controller list unavailable: {exc}")
        controllers = ()
    if not controllers:
        notes.append("No PCI storage controllers found (lspci missing, or none reported).")

    try:
        disks = collect_disks(sys_root=sys_root)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Disk enumeration unavailable: {exc}")
        disks = ()

    try:
        fs_text = _read_text(f"{proc_root}/filesystems") or ""
        filesystems, pseudo_filesystems = parse_filesystems(fs_text)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Filesystem list unavailable: {exc}")
        filesystems, pseudo_filesystems = (), ()

    try:
        modules_text = _read_text(f"{proc_root}/modules") or ""
        modules = parse_modules(modules_text)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Kernel module list unavailable: {exc}")
        modules = ()

    try:
        drive_types = supported_drive_types(controllers, disks, modules)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Drive type inference failed: {exc}")
        drive_types = ()

    notes.append(
        "SMART health data, full serial numbers and some sensor readings need root and "
        "are not shown — LinDriveSpace never asks for elevated privileges."
    )

    return HardwareReport(
        system=system,
        board=board,
        cpu=cpu,
        memory=memory,
        controllers=controllers,
        disks=disks,
        filesystems=filesystems,
        pseudo_filesystems=pseudo_filesystems,
        drive_types=drive_types,
        notes=tuple(notes),
    )


# ---- text export --------------------------------------------------------------------


def to_text(report: HardwareReport) -> str:
    """Plain-text dump of a report, for the page's "Copy report" button."""
    s = report.system
    b = report.board
    c = report.cpu
    m = report.memory
    lines: list[str] = [
        f"Hardware report — {s.hostname or 'this machine'}",
        f"System: {s.distro} · kernel {s.kernel} · {s.arch} · "
        f"{s.chassis_type} · virtualization: {s.virtualization}",
        f"Uptime: {s.uptime_seconds:.0f} s",
        "",
        "Motherboard & firmware",
        (
            f"  System: {b.sys_vendor or '—'} {b.product_name or ''} {b.product_version or ''}"
        ).rstrip(),
        f"  Board: {b.board_vendor or '—'} {b.board_name or ''} {b.board_version or ''}".rstrip(),
        f"  BIOS/UEFI: {b.bios_vendor or '—'} {b.bios_version or '—'} ({b.bios_date or '—'})",
        "",
        "Processor & memory",
        f"  CPU: {c.model} ({c.vendor}) — {c.sockets} socket(s), {c.cores} cores, "
        f"{c.threads} threads",
    ]
    if c.max_mhz:
        lines.append(f"  Max clock: {c.max_mhz:.0f} MHz")
    if c.flags_of_interest:
        lines.append(f"  Notable flags: {', '.join(c.flags_of_interest)}")
    lines.append(f"  Memory: {m.total:,} bytes total, {m.available:,} bytes available")
    lines.append(f"  Swap: {m.swap_total:,} bytes total, {m.swap_free:,} bytes free")

    lines.append("")
    lines.append("Storage controllers")
    if report.controllers:
        for ctl in report.controllers:
            lines.append(f"  {ctl.kind} — {ctl.vendor} {ctl.device} ({ctl.slot})")
    else:
        lines.append("  none detected")

    lines.append("")
    lines.append("Disks")
    if report.disks:
        for d in report.disks:
            lines.append(
                f"  {d.path} — {d.model or 'Unknown model'} · {d.size:,} bytes · "
                f"{d.transport or 'unknown transport'} · serial {d.serial_masked}"
            )
            for name, size, fstype, mountpoint in d.partitions:
                lines.append(
                    f"    {name}: {size:,} bytes {fstype or ''} {mountpoint or ''}".rstrip()
                )
    else:
        lines.append("  none detected")

    lines.append("")
    lines.append(f"Supported drive types: {', '.join(report.drive_types) or 'none detected'}")
    lines.append(f"Filesystems: {', '.join(report.filesystems) or 'none'}")
    lines.append(f"Pseudo filesystems: {', '.join(report.pseudo_filesystems) or 'none'}")

    if report.notes:
        lines.append("")
        lines.append("Notes")
        for note in report.notes:
            lines.append(f"  - {note}")

    return "\n".join(lines)
