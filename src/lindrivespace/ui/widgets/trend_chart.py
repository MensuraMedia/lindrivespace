"""TrendChart — a themed line/area chart of disk usage over time (WP17).

Pure ``Gtk.DrawingArea``: geometry is computed here from the ``(ts, used)``
points the History page hands it (already bucketed and period-filtered by
``core.history.HistoryStore``), colours come from theme tokens only, same
approach as ``age_view.py``/``treemap_view.py``.
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from datetime import datetime

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, Gtk, Pango, PangoCairo  # noqa: E402

from lindrivespace.config.theme import ThemeDefinition  # noqa: E402
from lindrivespace.core import units  # noqa: E402

_MIN_WIDTH = 320
_MIN_HEIGHT = 180

_LEFT_MARGIN = 60.0
_RIGHT_MARGIN = 16.0
_TOP_MARGIN = 12.0
_BOTTOM_MARGIN = 22.0
_TICK_HEIGHT = 6.0
_GRID_LINES = 4
_EMPTY_TEXT = "No history yet — data is recorded automatically as the app runs"


def _x_label(ts: float, period: str) -> str:
    dt = datetime.fromtimestamp(ts)
    if period == "day":
        return dt.strftime("%H:%M")
    if period == "week":
        return dt.strftime("%a")
    return dt.strftime("%Y-%m-%d")


def _tooltip_text(ts: float, used: int) -> str:
    dt = datetime.fromtimestamp(ts)
    return f"{dt.strftime('%Y-%m-%d %H:%M')} · {units.format_bytes(used)}"


class TrendChart(Gtk.DrawingArea):
    """Area/line chart of ``used`` bytes over time, with a ``total`` guide line."""

    __gtype_name__ = "LdsTrendChart"

    def __init__(self, theme: ThemeDefinition) -> None:
        super().__init__()
        self._theme = theme
        self._points: list[tuple[float, int]] = []
        self._total = 0
        self._scans: tuple[float, ...] = ()
        self._period = "week"
        self._hover_index: int | None = None

        self.set_size_request(_MIN_WIDTH, _MIN_HEIGHT)
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect("draw", self._on_draw)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("leave-notify-event", self._on_leave)

    # ---- theme / data -----------------------------------------------------

    def set_theme(self, theme: ThemeDefinition) -> None:
        self._theme = theme
        self.queue_draw()

    def set_series(
        self,
        points: Sequence[tuple[float, int]],
        *,
        total: int = 0,
        scans: Sequence[float] = (),
        period: str = "week",
    ) -> None:
        self._points = list(points)
        self._total = total
        self._scans = tuple(scans)
        self._period = period
        self._hover_index = None
        self.set_tooltip_text(None)
        self.queue_draw()

    # ---- geometry -----------------------------------------------------------

    def _plot_rect(self, width: int, height: int) -> tuple[float, float, float, float]:
        x0 = _LEFT_MARGIN
        y0 = _TOP_MARGIN
        w = max(1.0, width - _LEFT_MARGIN - _RIGHT_MARGIN)
        h = max(1.0, height - _TOP_MARGIN - _BOTTOM_MARGIN)
        return x0, y0, w, h

    def _scale(self) -> float:
        values = [used for _ts, used in self._points]
        top = max([*values, self._total, 1])
        return top * 1.08

    def _x_of(self, ts: float, x0: float, w: float) -> float:
        points = self._points
        if len(points) < 2:
            return x0 + w / 2.0
        t_min, t_max = points[0][0], points[-1][0]
        span = t_max - t_min
        if span <= 0:
            return x0 + w / 2.0
        return x0 + (ts - t_min) / span * w

    def _y_of(self, value: int, y0: float, h: float, scale: float) -> float:
        return y0 + h - (value / scale * h)

    def _point_index_at(self, x: float, y0: float, h: float) -> int | None:
        width = self.get_allocated_width()
        if not self._points or width <= 0:
            return None
        x0, _y0, w, _h = self._plot_rect(width, self.get_allocated_height())
        xs = [self._x_of(ts, x0, w) for ts, _used in self._points]
        idx = bisect.bisect_left(xs, x)
        if idx <= 0:
            return 0
        if idx >= len(xs):
            return len(xs) - 1
        return idx if (x - xs[idx - 1]) > (xs[idx] - x) else idx - 1

    # ---- drawing --------------------------------------------------------------

    def _on_draw(self, _widget: Gtk.Widget, cr) -> bool:  # noqa: ANN001 - Cairo context
        theme = self._theme
        width = self.get_allocated_width()
        height = self.get_allocated_height()

        cr.set_source_rgb(*theme.rgb("bg_surface_2"))
        cr.rectangle(0, 0, width, height)
        cr.fill()

        if width <= 0 or height <= 0:
            return False

        if not self._points:
            self._draw_empty(cr, width, height)
            return False

        x0, y0, w, h = self._plot_rect(width, height)
        scale = self._scale()

        self._draw_grid(cr, x0, y0, w, h, scale)
        self._draw_x_labels(cr, x0, y0, w, h)
        self._draw_scan_ticks(cr, x0, y0, w, h)
        self._draw_area_and_line(cr, x0, y0, w, h, scale)
        self._draw_total_line(cr, x0, y0, w, h, scale)
        self._draw_last_point(cr, x0, y0, w, h, scale)
        self._draw_hover(cr, x0, y0, w, h, scale)
        return False

    def _draw_empty(self, cr, width: int, height: int) -> None:  # noqa: ANN001
        theme = self._theme
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription("Ubuntu 9"))
        layout.set_width(Pango.units_from_double(max(0.0, width - 32)))
        layout.set_alignment(Pango.Alignment.CENTER)
        layout.set_wrap(Pango.WrapMode.WORD)
        layout.set_text(_EMPTY_TEXT, -1)
        _text_w, text_h = layout.get_pixel_size()
        cr.set_source_rgb(*theme.rgb("fg_dim"))
        cr.move_to(16, max(0.0, (height - text_h) / 2))
        PangoCairo.show_layout(cr, layout)

    def _draw_grid(self, cr, x0: float, y0: float, w: float, h: float, scale: float) -> None:  # noqa: ANN001
        theme = self._theme
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription("Ubuntu Mono 8"))
        for i in range(_GRID_LINES + 1):
            value = scale * i / _GRID_LINES
            y = self._y_of(int(value), y0, h, scale)
            cr.set_source_rgb(*theme.rgb("line_soft"))
            cr.set_line_width(1)
            cr.move_to(x0, round(y) + 0.5)
            cr.line_to(x0 + w, round(y) + 0.5)
            cr.stroke()

            layout.set_text(units.format_bytes(int(value)), -1)
            text_w, text_h = layout.get_pixel_size()
            cr.set_source_rgb(*theme.rgb("fg_dim"))
            cr.move_to(x0 - text_w - 8, y - text_h / 2)
            PangoCairo.show_layout(cr, layout)

    def _draw_x_labels(self, cr, x0: float, y0: float, w: float, h: float) -> None:  # noqa: ANN001
        theme = self._theme
        points = self._points
        if not points:
            return

        # Greedy left-to-right placement: only draw a label once there is
        # enough horizontal room since the last one, so labels never overlap
        # regardless of how many points are bucketed for this period.
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription("Ubuntu Mono 8"))
        cr.set_source_rgb(*theme.rgb("fg_dim"))
        min_gap = 16.0
        next_allowed_x = -1e18
        last_index = len(points) - 1
        for i, (ts, _used) in enumerate(points):
            x = self._x_of(ts, x0, w)
            layout.set_text(_x_label(ts, self._period), -1)
            text_w, _text_h = layout.get_pixel_size()
            label_x = min(max(x - text_w / 2.0, x0), x0 + w - text_w)
            if label_x < next_allowed_x and i != last_index:
                continue
            label_x = max(label_x, next_allowed_x) if i == last_index else label_x
            cr.move_to(label_x, y0 + h + 6)
            PangoCairo.show_layout(cr, layout)
            next_allowed_x = label_x + text_w + min_gap

    def _draw_scan_ticks(self, cr, x0: float, y0: float, w: float, h: float) -> None:  # noqa: ANN001
        if not self._scans or not self._points:
            return
        theme = self._theme
        t_min, t_max = self._points[0][0], self._points[-1][0]
        cr.set_source_rgb(*theme.rgb("aubergine"))
        for ts in self._scans:
            if ts < t_min or ts > t_max:
                continue
            x = self._x_of(ts, x0, w)
            cr.rectangle(x - 1.5, y0 + h, 3, _TICK_HEIGHT)
            cr.fill()

    def _draw_area_and_line(
        self,
        cr,
        x0: float,
        y0: float,
        w: float,
        h: float,
        scale: float,  # noqa: ANN001
    ) -> None:
        theme = self._theme
        points = self._points
        xs = [self._x_of(ts, x0, w) for ts, _used in points]
        ys = [self._y_of(used, y0, h, scale) for _ts, used in points]

        cr.set_source_rgba(*theme.rgba("accent", 0.25))
        cr.move_to(xs[0], y0 + h)
        for x, y in zip(xs, ys, strict=True):
            cr.line_to(x, y)
        cr.line_to(xs[-1], y0 + h)
        cr.close_path()
        cr.fill()

        cr.set_source_rgb(*theme.rgb("accent"))
        cr.set_line_width(2)
        cr.move_to(xs[0], ys[0])
        for x, y in zip(xs[1:], ys[1:], strict=True):
            cr.line_to(x, y)
        cr.stroke()

    def _draw_total_line(
        self,
        cr,
        x0: float,
        y0: float,
        w: float,
        h: float,
        scale: float,  # noqa: ANN001
    ) -> None:
        if self._total <= 0:
            return
        theme = self._theme
        y = self._y_of(self._total, y0, h, scale)
        if y < y0 - 1:
            return
        cr.save()
        cr.set_source_rgb(*theme.rgb("warn"))
        cr.set_line_width(1.5)
        cr.set_dash([4.0, 3.0])
        cr.move_to(x0, y)
        cr.line_to(x0 + w, y)
        cr.stroke()
        cr.restore()

    def _draw_last_point(
        self,
        cr,
        x0: float,
        y0: float,
        w: float,
        h: float,
        scale: float,  # noqa: ANN001
    ) -> None:
        theme = self._theme
        ts, used = self._points[-1]
        x = self._x_of(ts, x0, w)
        y = self._y_of(used, y0, h, scale)

        cr.set_source_rgb(*theme.rgb("accent"))
        cr.arc(x, y, 3.5, 0, 2 * 3.141592653589793)
        cr.fill()

        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription("Ubuntu Mono 8"))
        layout.set_text(units.format_bytes(used), -1)
        text_w, text_h = layout.get_pixel_size()
        label_x = x - text_w - 6 if x + text_w + 6 > x0 + w else x + 6
        label_y = max(y0, y - text_h - 4)
        cr.set_source_rgb(*theme.rgb("fg"))
        cr.move_to(label_x, label_y)
        PangoCairo.show_layout(cr, layout)

    def _draw_hover(
        self,
        cr,
        x0: float,
        y0: float,
        w: float,
        h: float,
        scale: float,  # noqa: ANN001
    ) -> None:
        if self._hover_index is None or self._hover_index >= len(self._points):
            return
        theme = self._theme
        ts, used = self._points[self._hover_index]
        x = self._x_of(ts, x0, w)
        y = self._y_of(used, y0, h, scale)

        cr.set_source_rgba(*theme.rgba("fg", 0.35))
        cr.set_line_width(1)
        cr.move_to(x, y0)
        cr.line_to(x, y0 + h)
        cr.stroke()

        cr.set_source_rgb(*theme.rgb("fg"))
        cr.arc(x, y, 3.0, 0, 2 * 3.141592653589793)
        cr.fill()

    # ---- pointer interaction --------------------------------------------------

    def _on_motion(self, _widget: Gtk.Widget, event: Gdk.EventMotion) -> bool:
        height = self.get_allocated_height()
        _x0, y0, _w, h = self._plot_rect(self.get_allocated_width(), height)
        index = self._point_index_at(event.x, y0, h)
        if index != self._hover_index:
            self._hover_index = index
            self.queue_draw()
        if index is None:
            self.set_tooltip_text(None)
        else:
            ts, used = self._points[index]
            self.set_tooltip_text(_tooltip_text(ts, used))
        return True

    def _on_leave(self, _widget: Gtk.Widget, _event: Gdk.EventCrossing) -> bool:
        if self._hover_index is not None:
            self._hover_index = None
            self.queue_draw()
        self.set_tooltip_text(None)
        return True
