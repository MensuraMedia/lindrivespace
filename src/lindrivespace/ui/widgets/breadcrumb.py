"""Breadcrumb bar: clickable path segments for the selected node, plus a
right-aligned totals readout ("allocated X · N % of parent · entries M").
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gtk  # noqa: E402

from lindrivespace.config.theme import ThemeDefinition  # noqa: E402
from lindrivespace.core.units import format_count  # noqa: E402

if TYPE_CHECKING:
    from lindrivespace.core.fsnode import FsNode
    from lindrivespace.models.tree_model import ScanTreeModel


class Breadcrumb(Gtk.Box):
    """Shows the selected node's ancestry as clickable segments."""

    __gtype_name__ = "LdsBreadcrumb"
    __gsignals__ = {
        "segment-activated": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self, theme: ThemeDefinition) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._theme = theme
        self._node: FsNode | None = None
        self.get_style_context().add_class("crumbs")

        self.segments_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.pack_start(self.segments_box, True, True, 0)

        self.totals_label = Gtk.Label(label="")
        self.totals_label.set_xalign(1.0)
        self.totals_label.get_style_context().add_class("mono")
        self.totals_label.get_style_context().add_class("muted")
        self.pack_end(self.totals_label, False, False, 0)

    def set_theme(self, theme: ThemeDefinition) -> None:
        self._theme = theme

    @property
    def node(self) -> FsNode | None:
        return self._node

    def set_node(self, node: FsNode | None, model: ScanTreeModel) -> None:
        self._node = node
        self._clear_segments()
        if node is None:
            self.totals_label.set_text("")
            return

        chain: list[FsNode] = []
        cur: FsNode | None = node
        while cur is not None:
            chain.append(cur)
            cur = cur.parent
        chain.reverse()

        for i, ancestor in enumerate(chain):
            if i == 0:
                icon = Gtk.Image.new_from_icon_name("drive-harddisk-symbolic", Gtk.IconSize.MENU)
                self.segments_box.pack_start(icon, False, False, 0)
                label_text = ancestor.path()
            else:
                sep = Gtk.Label(label="›")
                sep.get_style_context().add_class("dim")
                self.segments_box.pack_start(sep, False, False, 0)
                label_text = ancestor.name
            button = Gtk.Button(label=label_text)
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.connect("clicked", self._on_segment_clicked, ancestor)
            self.segments_box.pack_start(button, False, False, 0)
        self.segments_box.show_all()

        alloc_text = model.fmt_bytes(model.primary(node))
        percent = model.percent(node)
        entries = node.files + node.dirs
        self.totals_label.set_text(
            f"allocated {alloc_text} · {percent:.1f} % of parent · entries {format_count(entries)}"
        )

    def _clear_segments(self) -> None:
        for child in list(self.segments_box.get_children()):
            self.segments_box.remove(child)

    def _on_segment_clicked(self, _button: Gtk.Button, node: FsNode) -> None:
        self.emit("segment-activated", node)
