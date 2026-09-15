"""Overview mount card: ring gauge, identity, usage line, scan button.

Direction B mockup (``docs/mockups/images/direction-b-overview-dashboard.png``):
a 64 px ring on the left, name + device/fstype + usage + scanned-at on the
right, and a Scan/Rescan button bottom-right that turns "primary" when the
card is selected.

:class:`MountCardData` is a small local dataclass so this package stays free
of a dependency on WP3's mount-discovery module; WP7 (the Overview page) is
expected to adapt whatever mount object it has into one of these.
"""

from __future__ import annotations

from dataclasses import dataclass

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, GObject, Gtk  # noqa: E402

from lindrivespace.config.layout import Layout  # noqa: E402
from lindrivespace.config.theme import ThemeDefinition  # noqa: E402
from lindrivespace.core.units import format_bytes  # noqa: E402
from lindrivespace.ui.widgets.bar_gauge import BarGauge  # noqa: E402

_DIMS = Layout.dimensions


@dataclass(slots=True)
class MountCardData:
    """Everything one :class:`MountCard` needs to render one mount."""

    name: str
    device: str
    fstype: str
    mountpoint: str
    used: int
    total: int
    scanned_at: str | None
    kind: str


def _icon_name(kind: str) -> str:
    if kind == "usb":
        return "media-removable-symbolic"
    if kind in ("ssd", "nvme"):
        return "drive-harddisk-solidstate-symbolic"
    return "drive-harddisk-symbolic"


def _percent(data: MountCardData) -> float:
    if data.total <= 0:
        return 0.0
    return max(0.0, min(100.0, (data.used / data.total) * 100.0))


def _usage_text(data: MountCardData) -> str:
    free = max(data.total - data.used, 0)
    return (
        f"{format_bytes(data.used)} used · {format_bytes(free)} free of {format_bytes(data.total)}"
    )


def _scanned_text(data: MountCardData) -> str:
    return f"scanned {data.scanned_at}" if data.scanned_at else "not scanned"


class MountCard(Gtk.Frame):
    """A single mount's card on the Overview page."""

    __gtype_name__ = "LdsMountCard"
    __gsignals__ = {
        "scan-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "selected": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, theme: ThemeDefinition, data: MountCardData) -> None:
        super().__init__()
        self.set_shadow_type(Gtk.ShadowType.NONE)
        self.get_style_context().add_class("card")
        self.set_size_request(_DIMS.CARD_WIDTH, _DIMS.CARD_HEIGHT)

        self._theme = theme
        self._data = data
        self._selected = False

        event_box = Gtk.EventBox()
        event_box.connect("button-press-event", self._on_card_clicked)
        self.add(event_box)

        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        outer.set_border_width(0)
        event_box.add(outer)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        body.set_valign(Gtk.Align.CENTER)
        outer.pack_start(body, True, True, 0)

        name_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.icon = Gtk.Image.new_from_icon_name(_icon_name(data.kind), Gtk.IconSize.MENU)
        name_row.pack_start(self.icon, False, False, 0)
        self.name_label = Gtk.Label()
        self.name_label.set_xalign(0.0)
        name_row.pack_start(self.name_label, True, True, 0)
        self.role_label = Gtk.Label()
        self.role_label.get_style_context().add_class("badge")
        self.role_label.set_no_show_all(True)
        name_row.pack_end(self.role_label, False, False, 0)
        body.pack_start(name_row, False, False, 0)
        self._role: str | None = None

        self.device_label = Gtk.Label()
        self.device_label.set_xalign(0.0)
        self.device_label.get_style_context().add_class("mono")
        self.device_label.get_style_context().add_class("muted")
        body.pack_start(self.device_label, False, False, 0)

        self.usage_label = Gtk.Label()
        self.usage_label.set_xalign(0.0)
        self.usage_label.set_line_wrap(True)
        body.pack_start(self.usage_label, False, False, 0)

        # Usage bar (replaces the ring gauge; same colour thresholds).
        self.gauge = BarGauge(theme)
        self.gauge.set_margin_top(4)
        self.gauge.set_margin_bottom(2)
        body.pack_start(self.gauge, False, False, 0)
        self.ring = self.gauge  # backwards-compatible name

        bottom_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.scanned_label = Gtk.Label()
        self.scanned_label.set_xalign(0.0)
        self.scanned_label.get_style_context().add_class("dim")
        bottom_row.pack_start(self.scanned_label, True, True, 0)

        self.scan_button = Gtk.Button()
        self.scan_button.connect("clicked", self._on_scan_clicked)
        bottom_row.pack_start(self.scan_button, False, False, 0)
        body.pack_start(bottom_row, False, False, 0)

        self._apply_data()

    # ---- rendering ----------------------------------------------------

    def _apply_data(self) -> None:
        data = self._data
        self.name_label.set_markup(f"<b>{GLib.markup_escape_text(data.name)}</b>")
        self.device_label.set_text(f"{data.device} · {data.fstype}")
        self.usage_label.set_text(_usage_text(data))
        self.scanned_label.set_text(_scanned_text(data))
        self.scan_button.set_label("Rescan" if data.scanned_at else "Scan")
        self.icon.set_from_icon_name(_icon_name(data.kind), Gtk.IconSize.MENU)
        self.gauge.set_percent(_percent(data))
        self._update_button_style()

    def set_theme(self, theme: ThemeDefinition) -> None:
        """Swap the active theme (propagated to the ring gauge)."""
        self._theme = theme
        self.gauge.set_theme(theme)

    def update(self, data: MountCardData) -> None:
        """Replace the card's data and refresh every label/glyph."""
        self._data = data
        self._apply_data()

    def set_role(self, role: str | None) -> None:
        """Mark the card as the user's "primary" / "secondary" mountpoint (or neither)."""
        ctx = self.get_style_context()
        for cls in ("role-primary", "role-secondary"):
            ctx.remove_class(cls)
        self._role = role if role in ("primary", "secondary") else None
        if self._role:
            ctx.add_class(f"role-{self._role}")
            self.role_label.set_text(self._role.upper())
            self.role_label.show()
        else:
            self.role_label.hide()

    @property
    def role(self) -> str | None:
        return self._role

    def set_selected(self, selected: bool) -> None:
        """Toggle the "selected" CSS class and the button's emphasis style."""
        self._selected = selected
        ctx = self.get_style_context()
        if selected:
            ctx.add_class("selected")
        else:
            ctx.remove_class("selected")
        self._update_button_style()

    def _update_button_style(self) -> None:
        ctx = self.scan_button.get_style_context()
        if self._selected:
            ctx.add_class("primary")
        else:
            ctx.remove_class("primary")

    # ---- signals --------------------------------------------------------

    def _on_scan_clicked(self, _button: Gtk.Button) -> None:
        self.emit("scan-requested", self._data.mountpoint)

    def _on_card_clicked(self, _widget: Gtk.Widget, _event) -> bool:
        self.emit("selected", self._data.mountpoint)
        return False
