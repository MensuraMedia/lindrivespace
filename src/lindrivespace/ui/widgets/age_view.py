"""AgeView — allocated-bytes-by-age histogram (WP9 insight panel).

Buckets (7 d / 30 d / 90 d / 1 y / older) are computed from every node's
``top_files`` ring across the subtree (``FsNode.walk``) — the same bounded
estimate ``core.classify.summarize_top_files`` uses, so this is an estimate
too; the footnote saying so lives in the panel container, not here, since
this widget is the bare ``Gtk.DrawingArea``.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, Gtk, Pango, PangoCairo  # noqa: E402

from lindrivespace.config.theme import ThemeDefinition  # noqa: E402
from lindrivespace.core import units  # noqa: E402

if TYPE_CHECKING:
    from lindrivespace.core.fsnode import FsNode
    from lindrivespace.models.tree_model import ScanTreeModel

_BUCKET_LABELS = ("7 d", "30 d", "90 d", "1 y", "older")
_BUCKET_BOUNDS = (7 * 86400.0, 30 * 86400.0, 90 * 86400.0, 365 * 86400.0)
_BAR_GAP = 12.0
_AXIS_HEIGHT = 20.0
_VALUE_HEIGHT = 16.0


class AgeView(Gtk.DrawingArea):
    """Histogram of allocated bytes bucketed by last-modified age."""

    __gtype_name__ = "LdsAgeView"

    def __init__(self, theme: ThemeDefinition, now: float | None = None) -> None:
        super().__init__()
        self._theme = theme
        self._now = now  # override for deterministic tests; None = time.time()
        self._node: FsNode | None = None
        self._model: ScanTreeModel | None = None
        self._dirty = True
        self._totals: list[int] = [0] * len(_BUCKET_LABELS)
        self._hover_index: int | None = None

        self.set_size_request(200, 160)
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect("draw", self._on_draw)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("leave-notify-event", self._on_leave)

    # ---- theme / data -----------------------------------------------------

    def set_theme(self, theme: ThemeDefinition) -> None:
        self._theme = theme
        self.queue_draw()

    def set_node(self, node: FsNode | None, model: ScanTreeModel) -> None:
        self._node = node
        self._model = model
        self._dirty = True

    def ensure_fresh(self) -> None:
        if self._dirty:
            self._rebuild()
            self._dirty = False
        self.queue_draw()

    @property
    def bucket_totals(self) -> list[tuple[str, int]]:
        return list(zip(_BUCKET_LABELS, self._totals, strict=True))

    # ---- build --------------------------------------------------------------

    def _rebuild(self) -> None:
        totals = [0] * len(_BUCKET_LABELS)
        node = self._node
        if node is not None:
            now = self._now if self._now is not None else time.time()
            for descendant in node.walk():
                for top_file in descendant.top_files:
                    age = now - top_file.mtime
                    idx = len(_BUCKET_BOUNDS)
                    for i, bound in enumerate(_BUCKET_BOUNDS):
                        if age <= bound:
                            idx = i
                            break
                    totals[idx] += top_file.alloc
        self._totals = totals

    # ---- geometry -------------------------------------------------------------

    def _bar_geometry(self, width: int) -> tuple[float, float]:
        n = len(_BUCKET_LABELS)
        bar_w = max(4.0, (width - _BAR_GAP * (n + 1)) / n)
        return bar_w, _BAR_GAP

    def _bar_index_at(self, x: float) -> int | None:
        width = self.get_allocated_width()
        if width <= 0:
            return None
        bar_w, gap = self._bar_geometry(width)
        for i in range(len(_BUCKET_LABELS)):
            bx = gap + i * (bar_w + gap)
            if bx <= x <= bx + bar_w:
                return i
        return None

    # ---- drawing --------------------------------------------------------------

    def _on_draw(self, _widget: Gtk.Widget, cr) -> bool:
        theme = self._theme
        width = self.get_allocated_width()
        height = self.get_allocated_height()

        cr.set_source_rgb(*theme.rgb("bg_surface_2"))
        cr.rectangle(0, 0, width, height)
        cr.fill()

        if width <= 0 or height <= 0:
            return False

        totals = self._totals
        max_value = max(totals) if totals else 0
        max_index = totals.index(max_value) if max_value > 0 else -1
        plot_h = max(1.0, height - _AXIS_HEIGHT - _VALUE_HEIGHT)
        bar_w, gap = self._bar_geometry(width)

        layout = PangoCairo.create_layout(cr)
        for i, (label, value) in enumerate(zip(_BUCKET_LABELS, totals, strict=True)):
            x = gap + i * (bar_w + gap)
            bar_h = plot_h * (value / max_value) if max_value else 0.0
            y = _VALUE_HEIGHT + (plot_h - bar_h)

            token = "accent" if i == max_index else "aubergine"
            cr.set_source_rgb(*theme.rgb(token))
            cr.rectangle(x, y, bar_w, bar_h)
            cr.fill()

            if i == self._hover_index:
                cr.set_source_rgba(*theme.rgba("fg", 0.18))
                cr.rectangle(x, y, bar_w, bar_h)
                cr.fill()

            layout.set_font_description(Pango.FontDescription("Ubuntu Mono 8"))
            layout.set_text(units.format_bytes(value), -1)
            text_w, text_h = layout.get_pixel_size()
            cr.set_source_rgb(*theme.rgb("fg_muted"))
            cr.move_to(x + (bar_w - text_w) / 2, max(0.0, y - text_h - 2))
            PangoCairo.show_layout(cr, layout)

            layout.set_text(label, -1)
            text_w2, _text_h2 = layout.get_pixel_size()
            cr.set_source_rgb(*theme.rgb("fg_dim"))
            cr.move_to(x + (bar_w - text_w2) / 2, height - _AXIS_HEIGHT + 4)
            PangoCairo.show_layout(cr, layout)
        return False

    # ---- pointer interaction --------------------------------------------------

    def _on_motion(self, _widget: Gtk.Widget, event: Gdk.EventMotion) -> bool:
        index = self._bar_index_at(event.x)
        if index != self._hover_index:
            self._hover_index = index
            self.queue_draw()
        if index is None:
            self.set_tooltip_text(None)
        else:
            self.set_tooltip_text(
                f"{_BUCKET_LABELS[index]}: {units.format_bytes(self._totals[index])}"
            )
        return True

    def _on_leave(self, _widget: Gtk.Widget, _event: Gdk.EventCrossing) -> bool:
        if self._hover_index is not None:
            self._hover_index = None
            self.queue_draw()
        self.set_tooltip_text(None)
        return True
