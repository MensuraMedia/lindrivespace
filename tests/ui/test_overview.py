"""OverviewPage tests: build the page against a minimal app/window double,
inject a fake lister into the page's MountsService, and drive everything
through the GLib main loop -- no real ``lsblk``/``pyudev`` calls are asserted
on.

Deliberately does *not* build a full ``LinDriveSpaceApp`` + ``MainWindow``
(the pattern in ``tests/ui/test_smoke.py``): a ``Gtk.Application`` registers a
D-Bus object at a path derived from its (fixed) application id, and a second
live instance of that same id within the same test process -- i.e. this
module's own fixture, on top of ``test_smoke.py``'s -- reliably raises
``An object is already exported for the interface org.gtk.Application``
when the whole ``tests/ui`` suite runs together (reproduced directly: two
sequential ``LinDriveSpaceApp(smoke=True)().register(None)`` calls in one
process, even with ``Gio.ApplicationFlags.NON_UNIQUE``, hit this every time).
``BasePage``/``OverviewPage`` only ever touch ``window.app.settings``,
``window.app.theme``, ``window.scan_history`` and ``window.request_scan``, so
a tiny double covers everything the page needs -- the same spirit as
``tests/ui/test_widgets.py`` rendering widgets in a bare ``Gtk.OffscreenWindow``
rather than a full application.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import gi
import pytest

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from lindrivespace.config.settings import Settings  # noqa: E402
from lindrivespace.config.theme import get_theme  # noqa: E402
from lindrivespace.core.mounts import DiskInfo, MountInfo  # noqa: E402
from lindrivespace.core.units import format_bytes  # noqa: E402
from lindrivespace.ui.pages.overview import OverviewPage  # noqa: E402


def _mount(
    mountpoint: str,
    *,
    kname: str,
    disk_kname: str,
    total: int,
    used: int,
    hidden: bool = False,
    is_bind: bool = False,
) -> MountInfo:
    return MountInfo(
        device=f"/dev/{kname}",
        kname=kname,
        mountpoint=mountpoint,
        fstype="ext4",
        options="rw",
        total=total,
        used=used,
        free=total - used,
        percent_used=(used / total * 100.0) if total else 0.0,
        label=None,
        uuid=None,
        maj_min="0:0",
        disk_kname=disk_kname,
        hidden=hidden,
        mount_id=None,
        parent_id=None,
        is_bind=is_bind,
        display_name=mountpoint,
    )


def _disk(
    kname: str, mounts: list[MountInfo], *, kind: str, transport: str, rotational: bool
) -> DiskInfo:
    return DiskInfo(
        kname=kname,
        path=f"/dev/{kname}",
        model=f"Model {kname}",
        size=sum(m.total for m in mounts) or 1,
        transport=transport,
        rotational=rotational,
        mounts=mounts,
        kind=kind,
    )


def _fake_snapshot() -> tuple[list[DiskInfo], list[MountInfo]]:
    boot = _mount(
        "/boot/efi", kname="nvme0n1p1", disk_kname="nvme0n1", total=1_000_000_000, used=100_000_000
    )
    root = _mount(
        "/", kname="nvme0n1p2", disk_kname="nvme0n1", total=100_000_000_000, used=50_000_000_000
    )
    home = _mount(
        "/home",
        kname="nvme0n1p3",
        disk_kname="nvme0n1",
        total=200_000_000_000,
        used=100_000_000_000,
    )
    data = _mount(
        "/mnt/data", kname="sda1", disk_kname="sda", total=500_000_000_000, used=400_000_000_000
    )
    snap = _mount(
        "/snap/core22/2411",
        kname="loop0",
        disk_kname=None,
        total=80_000_000,
        used=80_000_000,
        hidden=True,
    )
    # Not fstype-hidden (mqueue/hugetlbfs aren't in mounts.hidden_fstypes) but
    # has no backing block device -- must still be excluded from cards by
    # default via disk.kind, not just the mount's own `hidden` flag.
    mqueue = _mount(
        "/dev/mqueue",
        kname="mqueue",
        disk_kname=None,
        total=0,
        used=0,
        hidden=False,
    )

    nvme_disk = _disk(
        "nvme0n1", [boot, root, home], kind="nvme", transport="nvme", rotational=False
    )
    sda_disk = _disk("sda", [data], kind="hdd", transport="sata", rotational=True)
    loop_disk = _disk("loop0", [snap], kind="loop", transport="", rotational=False)
    virtual_disk = _disk("", [mqueue], kind="virtual", transport="", rotational=False)

    disks = [nvme_disk, sda_disk, loop_disk, virtual_disk]
    mounts = [boot, root, home, data, snap, mqueue]
    return disks, mounts


def _pump_until(condition, timeout: float = 5.0) -> None:
    ctx = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise TimeoutError("condition not met before timeout")
        if ctx.pending():
            ctx.iteration(False)
        else:
            time.sleep(0.005)


def _all_cards(page) -> dict:  # type: ignore[no-untyped-def]
    return page._cards


class _FakeApp:
    """Just what BasePage/OverviewPage read off ``window.app``."""

    def __init__(self, settings: Settings) -> None:
        from lindrivespace.core import units
        from lindrivespace.core.options import ScanOptions
        from lindrivespace.models.tree_model import ScanTreeModel
        from lindrivespace.services.scan_registry import ScanRegistry

        self.settings = settings
        self.theme = get_theme(settings.get("theme"))
        self.format_bytes = lambda n: units.format_bytes(n)
        self.make_model = lambda: ScanTreeModel(show_files=False)
        self.scan_registry = ScanRegistry(self.make_model, lambda: ScanOptions())


class _FakeWindow:
    """Stands in for MainWindow: only what BasePage/OverviewPage touch."""

    def __init__(self, settings: Settings) -> None:
        self.app = _FakeApp(settings)
        self.scan_history: dict[str, str] = {}

    def request_scan(self, path: str, force: bool = False) -> None:  # pragma: no cover
        pass


@pytest.fixture(scope="module")
def window():  # type: ignore[no-untyped-def]
    settings = Settings(path=Path(tempfile.mkdtemp(prefix="lds-overview-")) / "settings.json")
    settings.set("overview.view", "cards")  # the card tests below exercise the cards view
    win = _FakeWindow(settings)

    offscreen = Gtk.OffscreenWindow()
    page = OverviewPage(win)
    offscreen.add(page)
    offscreen.show_all()
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)

    win.pages = {"overview": page}
    yield win
    offscreen.destroy()


@pytest.fixture()
def overview_page(window):  # type: ignore[no-untyped-def]
    page = window.pages["overview"]

    # A real refresh (against whatever this machine's lsblk/mountinfo report)
    # was already kicked off when the page/service was constructed. Let it
    # fully settle before swapping in the fake lister, so the emission we
    # wait for below is unambiguously the one built from our fake snapshot,
    # not a race against real system data.
    _pump_until(lambda: not page.service._refresh_in_progress, timeout=10)

    disks, mounts = _fake_snapshot()
    page.service.lister = lambda: (disks, mounts)

    changed: list[int] = []
    handler_id = page.service.connect("mounts-changed", lambda _s: changed.append(1))
    try:
        page.service.refresh()
        _pump_until(lambda: changed)
    finally:
        page.service.disconnect(handler_id)
    return page


def test_refresh_populates_kpi_totals(overview_page) -> None:  # type: ignore[no-untyped-def]
    capacity = 1_000_000_000 + 100_000_000_000 + 200_000_000_000 + 500_000_000_000
    used = 100_000_000 + 50_000_000_000 + 100_000_000_000 + 400_000_000_000

    cap_value, cap_unit = format_bytes(capacity).rsplit(" ", 1)
    used_value, used_unit = format_bytes(used).rsplit(" ", 1)

    assert overview_page.kpi_capacity.value_label.get_text() == cap_value
    assert overview_page.kpi_capacity.unit_label.get_text() == cap_unit
    assert overview_page.kpi_used.value_label.get_text() == used_value
    assert overview_page.kpi_used.unit_label.get_text() == used_unit


def test_flowbox_has_one_card_per_non_hidden_mount(overview_page) -> None:  # type: ignore[no-untyped-def]
    cards = _all_cards(overview_page)
    assert set(cards) == {"/boot/efi", "/", "/home", "/mnt/data"}
    assert "/snap/core22/2411" not in cards
    assert "/dev/mqueue" not in cards

    flowboxes = [
        child
        for group in overview_page.groups_box.get_children()
        for child in group.get_children()
        if isinstance(child, Gtk.FlowBox)
    ]
    total_children = sum(len(fb.get_children()) for fb in flowboxes)
    assert total_children == 4


def test_scan_button_click_calls_window_request_scan(
    overview_page, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    monkeypatch.setattr(
        overview_page.window, "request_scan", lambda path, force=False: calls.append(path)
    )

    card = _all_cards(overview_page)["/home"]
    card.scan_button.clicked()

    assert calls == ["/home"]


def test_refresh_scan_history_updates_card_label(overview_page) -> None:  # type: ignore[no-untyped-def]
    overview_page.window.scan_history["/home"] = "2026-09-14 18:41"

    overview_page.refresh_scan_history()

    card = _all_cards(overview_page)["/home"]
    assert card.scanned_label.get_text() == "scanned 2026-09-14 18:41"
    assert overview_page.kpi_scanned.value_label.get_text() == "1"


def test_list_view_rows_and_switching(overview_page, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """List view: one row per mount under its disk row; double-click scans; switch back."""
    page = overview_page
    page.set_view("list")
    assert page.current_view == "list" and page.mount_list is not None
    store = page.mount_list.store
    mount_rows = 0
    parent = store.get_iter_first()
    while parent is not None:
        assert store.get_value(parent, 0) == "disk"
        child = store.iter_children(parent)
        while child is not None:
            mount_rows += 1
            child = store.iter_next(child)
        parent = store.iter_next(parent)
    assert mount_rows == 4  # /, /boot/efi, /home, /mnt/data (hidden mounts off)
    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        page.window, "request_scan", lambda mp, force=False: calls.append((mp, force))
    )
    first_mount = store.iter_children(store.get_iter_first())
    page.mount_list.view.row_activated(
        store.get_path(first_mount), page.mount_list.view.get_column(0)
    )
    assert calls and calls[0][1] is True
    # star column toggles the favourite
    fav_calls: list[tuple[str, bool]] = []
    page.mount_list.connect("favorite-toggled", lambda _l, mp, on: fav_calls.append((mp, on)))
    page.mount_list.emit("favorite-toggled", calls[0][0], True)
    assert fav_calls == [(calls[0][0], True)]
    page.set_view("cards")
    assert page.current_view == "cards" and page.mount_list is None and page._cards
