"""Ring gauge ``Gtk.DrawingArea``: track + progress arc + centred percent label.

Used on the Overview mount cards (concept doc §7, Direction B mockup). The arc
starts at 12 o'clock and sweeps clockwise; colour escalates accent -> warn ->
danger as usage climbs.
"""

from __future__ import annotations

import math

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import GObject, Gtk, Pango, PangoCairo  # noqa: E402

from lindrivespace.config.layout import Layout  # noqa: E402
from lindrivespace.config.theme import ThemeDefinition  # noqa: E402

_DIMS = Layout.dimensions
_TWO_PI = 2 * math.pi
_TOP = -math.pi / 2  # 12 o'clock in Cairo's y-down coordinate system


def colour_token_for_percent(percent: float) -> str:
    """Pick the semantic colour token for a usage percentage (§7.4 thresholds)."""
    if percent >= 95:
        return "danger"
    if percent >= 85:
        return "warn"
    return "accent"


class RingGauge(Gtk.DrawingArea):
    """A circular percent gauge drawn with Cairo."""

    __gtype_name__ = "LdsRingGauge"

    percent = GObject.Property(type=float, default=0.0, minimum=0.0, maximum=100.0, nick="percent")
    label = GObject.Property(type=str, default="", nick="label")

    def __init__(
        self,
        theme: ThemeDefinition,
        size: int = _DIMS.RING_SIZE,
        stroke: int = _DIMS.RING_STROKE,
    ) -> None:
        super().__init__()
        self._theme = theme
        self._size = size
        self._stroke = stroke
        self.set_size_request(size, size)
        self.connect("draw", self._on_draw)
        self.connect("notify::percent", lambda *_a: self.queue_draw())
        self.connect("notify::label", lambda *_a: self.queue_draw())

    def set_theme(self, theme: ThemeDefinition) -> None:
        """Swap the active theme and redraw immediately."""
        self._theme = theme
        self.queue_draw()

    def set_percent(self, percent: float) -> None:
        """Clamp to 0-100, store, and queue a redraw."""
        self.percent = max(0.0, min(100.0, percent))
        self.queue_draw()

    def _label_text(self) -> str:
        return self.label or f"{round(self.percent)}%"

    def _on_draw(self, _widget: Gtk.Widget, cr) -> bool:
        theme = self._theme
        size = self._size
        stroke = self._stroke
        cx = size / 2
        cy = size / 2
        radius = (size - stroke) / 2
        pct = max(0.0, min(100.0, self.percent))

        cr.set_line_width(stroke)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)

        # Track.
        cr.set_source_rgb(*theme.rgb("bg_sunken"))
        cr.arc(cx, cy, radius, 0, _TWO_PI)
        cr.stroke()

        # Progress arc.
        if pct > 0:
            token = colour_token_for_percent(pct)
            cr.set_source_rgb(*theme.rgb(token))
            end = _TOP + (pct / 100.0) * _TWO_PI
            cr.arc(cx, cy, radius, _TOP, end)
            cr.stroke()

        # Centred label.
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription(f"Ubuntu Medium {size * 0.22:.1f}"))
        layout.set_text(self._label_text(), -1)
        text_w, text_h = layout.get_pixel_size()
        cr.set_source_rgb(*theme.rgb("fg"))
        cr.move_to(cx - text_w / 2, cy - text_h / 2)
        PangoCairo.show_layout(cr, layout)
        return False
