"""Custom ``Gtk.CellRenderer`` that draws a rounded percent bar with a label.

Used by the Explorer tree-table's "% of Parent" column (see concept doc §6). The
track, fill and label colours all come from :class:`ThemeDefinition` tokens.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import GObject, Gtk, Pango, PangoCairo  # noqa: E402

from lindrivespace.config.layout import Layout  # noqa: E402
from lindrivespace.config.theme import ThemeDefinition  # noqa: E402
from lindrivespace.core.units import format_percent  # noqa: E402

_DIMS = Layout.dimensions
_PADDING = 4
_FONT = "Ubuntu Mono 8.5"


def _rounded_rect(cr, x: float, y: float, width: float, height: float, radius: float) -> None:
    """Trace a rounded-rectangle path (caller fills/strokes/clips it)."""
    radius = max(0.0, min(radius, height / 2, width / 2))
    half_pi = 1.5707963267948966
    cr.new_sub_path()
    cr.arc(x + width - radius, y + radius, radius, -half_pi, 0)
    cr.arc(x + width - radius, y + height - radius, radius, 0, half_pi)
    cr.arc(x + radius, y + height - radius, radius, half_pi, 2 * half_pi)
    cr.arc(x + radius, y + radius, radius, 2 * half_pi, 3 * half_pi)
    cr.close_path()


class PercentBarRenderer(Gtk.CellRenderer):
    """Rounded track + accent fill + centred label, drawn with Cairo.

    Runs inside a fixed-height ``Gtk.TreeView`` (§6), so
    :meth:`do_get_preferred_height` always reports ``Layout.dimensions.ROW_HEIGHT``.
    """

    __gtype_name__ = "LdsPercentBarRenderer"

    percent = GObject.Property(type=float, default=0.0, minimum=0.0, maximum=100.0, nick="percent")
    text = GObject.Property(type=str, default="", nick="text")
    emphasis = GObject.Property(type=bool, default=False, nick="emphasis")

    def __init__(self, theme: ThemeDefinition) -> None:
        super().__init__()
        self._theme = theme

    def set_theme(self, theme: ThemeDefinition) -> None:
        """Swap the active theme; the next render uses the new tokens."""
        self._theme = theme

    def _label_text(self) -> str:
        return self.text or format_percent(self.percent)

    def do_get_preferred_width(self, widget: Gtk.Widget) -> tuple[int, int]:
        width = _DIMS.BAR_WIDTH + 2 * _PADDING
        return width, width

    def do_get_preferred_height(self, widget: Gtk.Widget) -> tuple[int, int]:
        return _DIMS.ROW_HEIGHT, _DIMS.ROW_HEIGHT

    def do_render(
        self,
        cr,
        widget: Gtk.Widget,
        background_area,
        cell_area,
        flags: Gtk.CellRendererState,
    ) -> None:
        theme = self._theme
        pct = max(0.0, min(100.0, self.percent))

        # Never paint outside the cell: a narrowed column shrinks the bar instead.
        cr.save()
        cr.rectangle(cell_area.x, cell_area.y, cell_area.width, cell_area.height)
        cr.clip()
        bar_height = _DIMS.BAR_HEIGHT
        bar_width = max(8.0, cell_area.width - 2 * _PADDING)
        x = cell_area.x + (cell_area.width - bar_width) / 2
        y = cell_area.y + (cell_area.height - bar_height) / 2
        radius = _DIMS.BAR_RADIUS

        # Track.
        _rounded_rect(cr, x, y, bar_width, bar_height, radius)
        cr.set_source_rgb(*theme.rgb("bg_sunken"))
        cr.fill_preserve()
        cr.set_source_rgb(*theme.rgb("line"))
        cr.set_line_width(1)
        cr.stroke()

        # Fill, clipped to the rounded track.
        fill_width = bar_width * (pct / 100.0)
        if fill_width > 0:
            cr.save()
            _rounded_rect(cr, x, y, bar_width, bar_height, radius)
            cr.clip()
            fill_token = "accent_hot" if self.emphasis else "accent"
            cr.set_source_rgb(*theme.rgb(fill_token))
            cr.rectangle(x, y, fill_width, bar_height)
            cr.fill()
            cr.restore()

        # Centred label.
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription(_FONT))
        layout.set_text(self._label_text(), -1)
        text_w, text_h = layout.get_pixel_size()
        text_x = cell_area.x + (cell_area.width - text_w) / 2
        text_y = cell_area.y + (cell_area.height - text_h) / 2
        cr.set_source_rgb(*theme.rgb("fg"))
        cr.move_to(text_x, text_y)
        PangoCairo.show_layout(cr, layout)
        cr.restore()
