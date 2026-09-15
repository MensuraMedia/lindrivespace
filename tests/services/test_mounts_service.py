"""MountsService tests: headless, driven entirely through an injected ``lister``.

No real ``lsblk``/``pyudev`` involved for the ``refresh()``-only tests; the
default (``Gtk.init_check`` gated) collection skip in ``tests/conftest.py``
does not apply here since this module needs only ``GLib``, not a display -- it
still lives under ``tests/services`` (not ``tests/core``) because it exercises
GObject signals and the GLib main loop.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from lindrivespace.config.settings import Settings  # noqa: E402
from lindrivespace.core.mounts import DiskInfo, MountInfo  # noqa: E402
from lindrivespace.services.mounts_service import MountsService  # noqa: E402


def _make_mount(
    mountpoint: str, *, total: int = 100, used: int = 50, hidden: bool = False
) -> MountInfo:
    free = total - used
    return MountInfo(
        device=f"/dev/{mountpoint.strip('/') or 'root'}",
        kname=mountpoint.strip("/") or "root",
        mountpoint=mountpoint,
        fstype="ext4",
        options="rw",
        total=total,
        used=used,
        free=free,
        percent_used=(used / total * 100.0) if total else 0.0,
        label=None,
        uuid=None,
        maj_min="259:1",
        disk_kname="nvme0n1",
        hidden=hidden,
        mount_id=None,
        parent_id=None,
        is_bind=False,
        display_name=mountpoint,
    )


def _make_disk(kname: str, mounts: list[MountInfo], *, kind: str = "nvme") -> DiskInfo:
    return DiskInfo(
        kname=kname,
        path=f"/dev/{kname}",
        model="Test Disk",
        size=1_000_000,
        transport="nvme" if kind == "nvme" else "sata",
        rotational=False,
        mounts=mounts,
        kind=kind,
    )


def _settings(tmp_path: Path) -> Settings:
    return Settings(path=tmp_path / "settings.json")


def _pump_until(condition, timeout: float = 5.0) -> None:
    """Pump the default GLib main context until ``condition()`` is true."""
    ctx = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise TimeoutError("condition not met before timeout")
        if ctx.pending():
            ctx.iteration(False)
        else:
            time.sleep(0.005)


def test_refresh_populates_disks_and_mounts(tmp_path: Path) -> None:
    root = _make_mount("/")
    home = _make_mount("/home")
    disk = _make_disk("nvme0n1", [root, home])

    service = MountsService(_settings(tmp_path), lister=lambda: ([disk], [root, home]))
    fired = []
    service.connect("mounts-changed", lambda _s: fired.append(1))

    service.refresh()
    _pump_until(lambda: fired)

    assert service.disks == [disk]
    assert service.mounts == [root, home]
    assert service.last_refresh_monotonic is not None


def test_refresh_coalesces_concurrent_requests(tmp_path: Path) -> None:
    started = threading.Event()
    release = threading.Event()
    calls: list[int] = []

    def blocking_lister() -> tuple[list[DiskInfo], list[MountInfo]]:
        calls.append(1)
        started.set()
        release.wait(timeout=5)
        return [], []

    service = MountsService(_settings(tmp_path), lister=blocking_lister)
    fired: list[int] = []
    service.connect("mounts-changed", lambda _s: fired.append(1))

    service.refresh()
    assert started.wait(timeout=5), "worker thread never started"
    started.clear()

    # A second refresh while the first is still running must not spawn a
    # second worker immediately -- it schedules exactly one more run.
    service.refresh()

    release.set()
    _pump_until(lambda: len(fired) >= 2)

    # Give a moment for a hypothetical (buggy) extra emission to show up.
    time.sleep(0.05)
    ctx = GLib.MainContext.default()
    while ctx.pending():
        ctx.iteration(False)

    assert len(fired) == 2
    assert len(calls) == 2


def test_show_hidden_setter_persists_and_refreshes(tmp_path: Path) -> None:
    calls: list[int] = []

    def lister() -> tuple[list[DiskInfo], list[MountInfo]]:
        calls.append(1)
        return [], []

    settings = _settings(tmp_path)
    service = MountsService(settings, lister=lister)
    fired: list[int] = []
    service.connect("mounts-changed", lambda _s: fired.append(1))

    assert service.show_hidden is False
    service.show_hidden = True
    _pump_until(lambda: fired)

    assert settings.get("mounts.show_hidden") is True
    assert service.show_hidden is True
    assert len(calls) == 1


def test_start_stop_lifecycle(tmp_path: Path) -> None:
    root = _make_mount("/")
    disk = _make_disk("nvme0n1", [root])

    service = MountsService(_settings(tmp_path), lister=lambda: ([disk], [root]))
    fired: list[int] = []
    service.connect("mounts-changed", lambda _s: fired.append(1))
    try:
        service.start()
        _pump_until(lambda: fired)
        assert service.disks == [disk]
        assert isinstance(service.monitor_available, bool)
    finally:
        service.stop()
