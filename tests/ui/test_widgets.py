"""WP5 widget tests: every widget renders inside a Gtk.OffscreenWindow.

Needs a display; skipped by ``tests/conftest.py`` when GTK can't init.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from lindrivespace.config.layout import Layout  # noqa: E402
from lindrivespace.config.theme import GRAY_TEMPERATURE_DARK  # noqa: E402
from lindrivespace.ui.widgets.kpi_tile import KpiTile  # noqa: E402
from lindrivespace.ui.widgets.mount_card import MountCard, MountCardData  # noqa: E402
from lindrivespace.ui.widgets.percent_bar_renderer import PercentBarRenderer  # noqa: E402
from lindrivespace.ui.widgets.ring_gauge import RingGauge, colour_token_for_percent  # noqa: E402

THEME = GRAY_TEMPERATURE_DARK
DIMS = Layout.dimensions
ACCENT_RGB = (0xE9, 0x54, 0x20)
TOLERANCE = 8


def _pump() -> None:
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)


def _render(widget: Gtk.Widget, width: int = -1, height: int = -1):
    # Deliberately does not destroy the OffscreenWindow: some callers keep
    # interacting with the widget (e.g. clicking a button) after rendering,
    # and Gtk.Widget.destroy() would tear the whole hierarchy down.
    window = Gtk.OffscreenWindow()
    if width > 0 or height > 0:
        widget.set_size_request(max(width, -1), max(height, -1))
    window.add(widget)
    window.show_all()
    _pump()
    return window.get_pixbuf()


def _sample_data(**overrides: object) -> MountCardData:
    base = dict(
        name="/home",
        device="nvme0n1p3",
        fstype="ext4",
        mountpoint="/home",
        used=614_900_000_000,
        total=1_700_000_000_000,
        scanned_at="2026-09-14 18:41",
        kind="nvme",
    )
    base.update(overrides)
    return MountCardData(**base)  # type: ignore[arg-type]


# ---- PercentBarRenderer --------------------------------------------------


def test_percent_bar_preferred_height_is_row_height() -> None:
    renderer = PercentBarRenderer(THEME)
    _min, natural = renderer.do_get_preferred_height(Gtk.Label())
    assert _min == DIMS.ROW_HEIGHT
    assert natural == DIMS.ROW_HEIGHT


def test_percent_bar_renders_accent_fill_at_full_percent() -> None:
    store = Gtk.ListStore(float, str)
    store.append([100.0, ""])
    tree = Gtk.TreeView(model=store)
    tree.set_headers_visible(False)  # keep row 0 flush with the top of the pixbuf

    renderer = PercentBarRenderer(THEME)
    column = Gtk.TreeViewColumn("pct", renderer)
    column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
    padding = 8  # 2 * the renderer's internal 4px padding
    column.set_fixed_width(DIMS.BAR_WIDTH + padding)
    column.add_attribute(renderer, "percent", 0)
    column.add_attribute(renderer, "text", 1)
    tree.append_column(column)
    tree.set_fixed_height_mode(True)

    pixbuf = _render(tree, width=DIMS.BAR_WIDTH + padding, height=DIMS.ROW_HEIGHT * 2)
    assert pixbuf is not None
    assert pixbuf.get_width() > 0
    assert pixbuf.get_height() > 0

    # Sample a pixel inside the bar's fill but off to the side of the centred
    # label text (which, at 100 %, sits in the middle of the bar) so we read
    # pure fill colour rather than a text glyph or anti-aliased edge.
    bar_left = padding // 2
    x = bar_left + 8
    y = DIMS.ROW_HEIGHT // 2
    pixels = pixbuf.get_pixels()
    stride = pixbuf.get_rowstride()
    channels = pixbuf.get_n_channels()
    offset = y * stride + x * channels
    r, g, b = pixels[offset], pixels[offset + 1], pixels[offset + 2]
    assert abs(r - ACCENT_RGB[0]) <= TOLERANCE
    assert abs(g - ACCENT_RGB[1]) <= TOLERANCE
    assert abs(b - ACCENT_RGB[2]) <= TOLERANCE


# ---- RingGauge ------------------------------------------------------------


def test_ring_gauge_colour_thresholds() -> None:
    assert colour_token_for_percent(0) == "accent"
    assert colour_token_for_percent(84.9) == "accent"
    assert colour_token_for_percent(85) == "warn"
    assert colour_token_for_percent(94.9) == "warn"
    assert colour_token_for_percent(95) == "danger"
    assert colour_token_for_percent(100) == "danger"


def test_ring_gauge_percent_clamping() -> None:
    ring = RingGauge(THEME)
    ring.set_percent(150)
    assert ring.percent == 100.0
    ring.set_percent(-20)
    assert ring.percent == 0.0


def test_ring_gauge_renders() -> None:
    ring = RingGauge(THEME)
    ring.set_percent(73)
    pixbuf = _render(ring)
    assert pixbuf is not None
    assert pixbuf.get_width() == DIMS.RING_SIZE
    assert pixbuf.get_height() == DIMS.RING_SIZE


# ---- MountCard --------------------------------------------------------


def test_mount_card_renders() -> None:
    card = MountCard(THEME, _sample_data())
    pixbuf = _render(card)
    assert pixbuf is not None
    assert pixbuf.get_width() > 0
    assert pixbuf.get_height() > 0


def test_mount_card_scan_requested_signal() -> None:
    card = MountCard(THEME, _sample_data(mountpoint="/home"))
    seen: list[str] = []
    card.connect("scan-requested", lambda _card, mountpoint: seen.append(mountpoint))
    _render(card)
    card.scan_button.clicked()
    assert seen == ["/home"]


def test_mount_card_set_selected_toggles_css_class() -> None:
    card = MountCard(THEME, _sample_data())
    ctx = card.get_style_context()
    assert not ctx.has_class("selected")
    card.set_selected(True)
    assert ctx.has_class("selected")
    assert card.scan_button.get_style_context().has_class("primary")
    card.set_selected(False)
    assert not ctx.has_class("selected")
    assert not card.scan_button.get_style_context().has_class("primary")


def test_mount_card_update_refreshes_labels() -> None:
    card = MountCard(THEME, _sample_data(scanned_at=None))
    assert card.scan_button.get_label() == "Scan"
    assert card.scanned_label.get_text() == "not scanned"
    card.update(_sample_data(scanned_at="2026-09-14 18:41"))
    assert card.scan_button.get_label() == "Rescan"
    assert "2026-09-14 18:41" in card.scanned_label.get_text()


# ---- KpiTile --------------------------------------------------------------


def test_kpi_tile_renders() -> None:
    tile = KpiTile(THEME, "Total capacity", "2.77", unit="TB", detail="across 5 mounts")
    pixbuf = _render(tile, width=DIMS.CARD_WIDTH, height=DIMS.KPI_HEIGHT)
    assert pixbuf is not None
    assert pixbuf.get_width() > 0
    assert pixbuf.get_height() > 0


def test_kpi_tile_set_value_updates_labels() -> None:
    tile = KpiTile(THEME, "Used", "1.62", unit="TB", detail="58 %")
    tile.set_value("1.70", unit="TB", detail="60 %")
    assert tile.value_label.get_text() == "1.70"
    assert tile.unit_label.get_text() == "TB"
    assert tile.detail_label.get_text() == "60 %"
    tile.set_value("1.71")
    assert tile.value_label.get_text() == "1.71"
    assert tile.unit_label.get_text() == "TB"  # unchanged when omitted


def test_mount_card_role_badge() -> None:
    from lindrivespace.config.theme import GRAY_TEMPERATURE_DARK
    from lindrivespace.ui.widgets import MountCard, MountCardData

    data = MountCardData("/", "nvme0n1p2", "ext4", "/", 10, 100, None, "nvme")
    card = MountCard(GRAY_TEMPERATURE_DARK, data)
    card.set_role("primary")
    assert card.role == "primary"
    assert card.get_style_context().has_class("role-primary")
    assert card.role_label.get_text() == "PRIMARY"
    card.set_role(None)
    assert card.role is None and not card.get_style_context().has_class("role-primary")
