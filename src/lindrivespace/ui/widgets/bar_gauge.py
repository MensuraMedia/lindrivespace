"""BarGauge — a horizontal usage bar with a percent label (replaces the ring gauge).

Same colour rules as the ring: accent below 85 %, warn from 85 %, danger from
95 % (``colour_token_for_percent`` in ring_gauge.py). Track and fill are drawn
with Cairo from theme tokens; the label sits to the right of the bar.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import GObject, Gtk, Pango, PangoCairo  # noqa: E402

from lindrivespace.config.layout import Layout  # noqa: E402
from lindrivespace.config.theme import ThemeDefinition  # noqa: E402
from lindrivespace.ui.widgets.ring_gauge import colour_token_for_percent  # noqa: E402

_DIMS = Layout.dimensions
_LABEL_W = 40  # px reserved for the "23%" label
_GAP = 8


class BarGauge(Gtk.DrawingArea):
    """Horizontal bar: ``percent`` 0–100, optional ``label`` override."""

    __gtype_name__ = "LdsBarGauge"

    percent = GObject.Property(type=float, default=0.0, minimum=0.0, maximum=100.0)
    label = GObject.Property(type=str, default="")

    def __init__(
        self,
        theme: ThemeDefinition,
        height: int = _DIMS.BAR_HEIGHT,
        radius: int = _DIMS.BAR_RADIUS,
        show_label: bool = True,
    ) -> None:
        super().__init__()
        self._theme = theme
        self._height = height
        self._radius = radius
        self._show_label = show_label
        self.set_size_request(_DIMS.BAR_WIDTH + (_LABEL_W + _GAP if show_label else 0), height + 6)
        self.set_hexpand(True)
        self.set_valign(Gtk.Align.CENTER)
        self.connect("draw", self._on_draw)
        self.connect("notify::percent", lambda *_a: self.queue_draw())
        self.connect("notify::label", lambda *_a: self.queue_draw())

    # ---- API ----------------------------------------------------------------

    def set_percent(self, percent: float) -> None:
        self.percent = max(0.0, min(100.0, float(percent)))

    def set_theme(self, theme: ThemeDefinition) -> None:
        self._theme = theme
        self.queue_draw()

    @property
    def colour_token(self) -> str:
        return colour_token_for_percent(self.percent)

    # ---- drawing ------------------------------------------------------------

    def _rounded_rect(self, cr, x: float, y: float, w: float, h: float, r: float) -> None:
        r = max(0.0, min(r, h / 2, w / 2))
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -1.5708, 0)
        cr.arc(x + w - r, y + h - r, r, 0, 1.5708)
        cr.arc(x + r, y + h - r, r, 1.5708, 3.14159)
        cr.arc(x + r, y + r, r, 3.14159, 4.71239)
        cr.close_path()

    def _on_draw(self, _widget: Gtk.Widget, cr) -> bool:
        theme = self._theme
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        bar_w = width - (_LABEL_W + _GAP if self._show_label else 0)
        y = (height - self._height) / 2.0

        # track
        self._rounded_rect(cr, 0.5, y + 0.5, max(1.0, bar_w - 1), self._height - 1, self._radius)
        cr.set_source_rgb(*theme.rgb("bg_sunken"))
        cr.fill_preserve()
        cr.set_source_rgb(*theme.rgb("line"))
        cr.set_line_width(1)
        cr.stroke()

        # fill, clipped to the rounded track
        pct = max(0.0, min(100.0, float(self.percent)))
        fill_w = (bar_w - 2) * pct / 100.0
        if fill_w > 0:
            cr.save()
            self._rounded_rect(cr, 1, y + 1, max(1.0, bar_w - 2), self._height - 2, self._radius)
            cr.clip()
            cr.set_source_rgb(*theme.rgb(self.colour_token))
            cr.rectangle(1, y + 1, fill_w, self._height - 2)
            cr.fill()
            cr.restore()

        if self._show_label:
            text = self.label or f"{round(pct)}%"
            layout = PangoCairo.create_layout(cr)
            layout.set_font_description(Pango.FontDescription("Ubuntu Medium 9"))
            layout.set_text(text, -1)
            _ink, logical = layout.get_pixel_extents()
            cr.set_source_rgb(*theme.rgb("fg"))
            cr.move_to(width - logical.width, (height - logical.height) / 2.0)
            PangoCairo.show_layout(cr, layout)
        return False
