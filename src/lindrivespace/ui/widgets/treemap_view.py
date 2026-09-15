"""TreemapView — squarified treemap of a subtree's allocation (WP9 insight panel).

Pure ``Gtk.DrawingArea``: geometry comes from ``core.treemap.layout_node`` (see
``core/treemap.py``), colours from theme tokens only. A node's item list is
cached by ``(view root id, width, height, model.version)`` and recomputed on
``size-allocate``/model change/zoom.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GObject, Gtk, Pango, PangoCairo  # noqa: E402

from lindrivespace.config.theme import ThemeDefinition  # noqa: E402
from lindrivespace.core.treemap import Rect, TreemapItem, hit_test, layout_node  # noqa: E402

if TYPE_CHECKING:
    from lindrivespace.core.fsnode import FsNode
    from lindrivespace.models.tree_model import ScanTreeModel

_MIN_AREA = 24.0
_PADDING = 2.0
_MAX_DEPTH = 2
_LABEL_MIN_W = 48.0
_LABEL_MIN_H = 18.0

_RGB = tuple[float, float, float]


def _blend(a: _RGB, b: _RGB, t: float) -> _RGB:
    t = max(0.0, min(1.0, t))
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


class TreemapView(Gtk.DrawingArea):
    """Nested squarified treemap for the node passed to :meth:`set_node`."""

    __gtype_name__ = "LdsTreemapView"
    __gsignals__ = {
        # Emitted on every click (single selects; double-click also zooms).
        "item-activated": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self, theme: ThemeDefinition) -> None:
        super().__init__()
        self._theme = theme
        self._node: FsNode | None = None
        self._model: ScanTreeModel | None = None
        self._view_root: FsNode | None = None
        self._zoom_stack: list[FsNode] = []
        self._items: list[TreemapItem] = []
        self._colors: list[_RGB] = []
        self._items_key: tuple[int, int, int, int] | None = None
        self._hover_item: TreemapItem | None = None

        self.set_size_request(220, 160)
        self.add_events(
            Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        self.connect("draw", self._on_draw)
        self.connect("size-allocate", lambda *_a: self.queue_draw())
        self.connect("motion-notify-event", self._on_motion)
        self.connect("button-press-event", self._on_button_press)
        self.connect("leave-notify-event", self._on_leave)

    # ---- theme / data -----------------------------------------------------

    def set_theme(self, theme: ThemeDefinition) -> None:
        self._theme = theme
        self._items_key = None  # colours depend on theme; force a recompute
        self.queue_draw()

    def set_node(self, node: FsNode | None, model: ScanTreeModel) -> None:
        self._node = node
        self._model = model
        self._view_root = node
        self._zoom_stack = []
        self._items_key = None
        self._hover_item = None
        self.set_tooltip_text(None)

    def ensure_fresh(self) -> None:
        self._ensure_items()
        self.queue_draw()

    @property
    def items(self) -> list[TreemapItem]:
        self._ensure_items()  # lay out on demand (cached by size/version)
        return list(self._items)

    @property
    def is_zoomed(self) -> bool:
        return bool(self._zoom_stack)

    def set_root(self, node: FsNode) -> None:
        """Zoom into ``node`` (must be a descendant of the current view)."""
        if self._view_root is not None and node is not self._view_root:
            self._zoom_stack.append(self._view_root)
        self._view_root = node
        self._items_key = None
        self.queue_draw()

    def zoom_out(self) -> None:
        """Pop one level of zoom, if any."""
        if self._zoom_stack:
            self._view_root = self._zoom_stack.pop()
            self._items_key = None
            self.queue_draw()

    # ---- layout -------------------------------------------------------------

    def _ensure_items(self) -> None:
        model = self._model
        root = self._view_root
        if model is None or root is None:
            self._items = []
            self._colors = []
            self._items_key = None
            return
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        if width <= 0 or height <= 0:
            return
        key = (root.id, width, height, model.version)
        if key == self._items_key:
            return
        rect = Rect(0.0, 0.0, float(width), float(height))
        self._items = layout_node(
            root,
            rect,
            max_depth=_MAX_DEPTH,
            min_area=_MIN_AREA,
            padding=_PADDING,
            allocated=model.allocated_primary,
        )
        self._items_key = key
        self._compute_colors()

    def _compute_colors(self) -> None:
        theme = self._theme
        accent = theme.rgb("accent")
        accent_hot = theme.rgb("accent_hot")
        warm_grey = theme.rgb("warm_grey")
        bg_deep = theme.rgb("bg_deep")

        colors: list[_RGB] = []
        prev_group: object = object()
        rank = -1
        for item in self._items:
            group: object = item.node.parent.id if item.node is not None else item.key[1]
            rank = 0 if group != prev_group else rank + 1
            prev_group = group

            if item.node is None:  # synthetic "files here" item
                base = warm_grey
            elif rank == 0:
                base = accent
            elif rank == 1:
                base = accent_hot
            else:
                base = _blend(accent_hot, bg_deep, min(1.0, (rank - 1) * 0.22))

            shaded = _blend(base, bg_deep, min(0.4, item.depth * 0.15))
            colors.append(shaded)
        self._colors = colors

    # ---- drawing --------------------------------------------------------------

    def _on_draw(self, _widget: Gtk.Widget, cr) -> bool:
        self._ensure_items()
        theme = self._theme
        width = self.get_allocated_width()
        height = self.get_allocated_height()

        cr.set_source_rgb(*theme.rgb("bg_surface_2"))
        cr.rectangle(0, 0, width, height)
        cr.fill()

        for item, color in zip(self._items, self._colors, strict=True):
            r = item.rect
            if r.w <= 0 or r.h <= 0:
                continue
            cr.set_source_rgb(*color)
            cr.rectangle(r.x, r.y, r.w, r.h)
            cr.fill()

            cr.set_source_rgb(*theme.rgb("bg_deep"))
            cr.set_line_width(1)
            cr.rectangle(r.x + 0.5, r.y + 0.5, max(0.0, r.w - 1), max(0.0, r.h - 1))
            cr.stroke()

            if item is self._hover_item:
                cr.set_source_rgba(*theme.rgba("fg", 0.18))
                cr.rectangle(r.x, r.y, r.w, r.h)
                cr.fill()

            if r.w >= _LABEL_MIN_W and r.h >= _LABEL_MIN_H and not self._will_recurse(item):
                self._draw_label(cr, item, r)
        return False

    def _will_recurse(self, item: TreemapItem) -> bool:
        """True if ``layout_node`` laid out further items on top of ``item``.

        Mirrors ``layout_node``'s own recursion gate exactly (see
        ``core/treemap.py``) so a directory whose interior is fully tiled by
        its own children/"files" portion doesn't draw a label that would just
        be painted over — the deeper (visible) item gets the label instead.
        """
        if item.node is None or item.depth + 1 > _MAX_DEPTH:
            return False
        if item.rect.area < _MIN_AREA:
            return False
        inset_w = max(0.0, item.rect.w - 2 * _PADDING)
        inset_h = max(0.0, item.rect.h - 2 * _PADDING)
        return inset_w * inset_h >= _MIN_AREA

    def _draw_label(self, cr, item: TreemapItem, rect: Rect) -> None:
        theme = self._theme
        model = self._model
        name = item.node.name if item.node is not None else "Files"
        size_text = model.fmt_bytes(int(item.value)) if model is not None else ""

        cr.save()
        cr.rectangle(rect.x, rect.y, rect.w, rect.h)
        cr.clip()

        name_layout = PangoCairo.create_layout(cr)
        name_layout.set_width(Pango.units_from_double(max(0.0, rect.w - 8)))
        name_layout.set_ellipsize(Pango.EllipsizeMode.END)
        name_layout.set_font_description(Pango.FontDescription("Ubuntu 8.5"))
        name_layout.set_text(name, -1)
        cr.set_source_rgb(*theme.rgb("fg"))
        cr.move_to(rect.x + 4, rect.y + 3)
        PangoCairo.show_layout(cr, name_layout)

        size_layout = PangoCairo.create_layout(cr)
        size_layout.set_width(Pango.units_from_double(max(0.0, rect.w - 8)))
        size_layout.set_ellipsize(Pango.EllipsizeMode.END)
        size_layout.set_font_description(Pango.FontDescription("Ubuntu Mono 8"))
        size_layout.set_text(size_text, -1)
        cr.set_source_rgb(*theme.rgb("fg_muted"))
        cr.move_to(rect.x + 4, rect.y + 16)
        PangoCairo.show_layout(cr, size_layout)

        cr.restore()

    # ---- pointer interaction --------------------------------------------------

    def _tooltip_for(self, item: TreemapItem) -> str:
        model = self._model
        if item.node is not None:
            path = item.node.path()
            alloc = model.fmt_bytes(model.primary(item.node)) if model is not None else ""
            percent = model.percent(item.node) if model is not None else 0.0
            return f"{path}\n{alloc} · {percent:.1f} %"
        root_path = self._view_root.path() if self._view_root is not None else ""
        alloc = model.fmt_bytes(int(item.value)) if model is not None else ""
        return f"{root_path} (files here)\n{alloc}"

    def _on_motion(self, _widget: Gtk.Widget, event: Gdk.EventMotion) -> bool:
        item = hit_test(self._items, event.x, event.y)
        if item is not self._hover_item:
            self._hover_item = item
            self.queue_draw()
        self.set_tooltip_text(self._tooltip_for(item) if item is not None else None)
        return True

    def _on_leave(self, _widget: Gtk.Widget, _event: Gdk.EventCrossing) -> bool:
        if self._hover_item is not None:
            self._hover_item = None
            self.queue_draw()
        self.set_tooltip_text(None)
        return True

    def _on_button_press(self, _widget: Gtk.Widget, event: Gdk.EventButton) -> bool:
        item = hit_test(self._items, event.x, event.y)
        if item is None:
            return False
        if event.button == 3:
            self.zoom_out()
            return True
        if event.type == Gdk.EventType._2BUTTON_PRESS:  # noqa: SLF001 - Gdk's own name
            if item.node is not None and item.node.children:
                self.set_root(item.node)
            return True
        if event.type == Gdk.EventType.BUTTON_PRESS and item.node is not None:
            self.emit("item-activated", item.node)
        return True
