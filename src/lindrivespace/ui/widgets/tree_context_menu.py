"""Right-click context menu for a row in the Explorer tree-table.

The menu only emits ``action(name, node)``; the page (which owns settings,
the scan controller and the clipboard) interprets the action names.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gtk  # noqa: E402

if TYPE_CHECKING:
    from lindrivespace.core.fsnode import FsNode


class TreeContextMenu(Gtk.Menu):
    """Built fresh for each right-click, bound to the row's node."""

    __gtype_name__ = "LdsTreeContextMenu"
    __gsignals__ = {
        "action": (GObject.SignalFlags.RUN_FIRST, None, (str, object)),
    }

    def __init__(
        self,
        node: FsNode | None = None,
        has_side_panel: bool = False,
        is_favorite: bool = False,
    ) -> None:
        super().__init__()
        self._node = node

        self._add_item(
            "Remove from favorites" if is_favorite else "Add to favorites  (Ctrl+D)",
            "toggle-favorite",
        )
        self.append(Gtk.SeparatorMenuItem())
        self._add_item("Open in file manager", "open-file-manager")
        self._add_item("Open terminal here", "open-terminal")
        self._add_item("Copy path", "copy-path")
        self.append(Gtk.SeparatorMenuItem())
        self._add_item("Rescan this folder", "rescan")
        self._add_item("Exclude from scan", "exclude")
        self.append(Gtk.SeparatorMenuItem())

        admin_item = self._add_item("Scan as administrator", "scan-as-admin")
        admin_item.set_sensitive(bool(node is not None and getattr(node, "denied", False)))

        treemap_item = self._add_item("Show in treemap", "show-in-treemap")
        treemap_item.set_sensitive(bool(has_side_panel))
        self.append(Gtk.SeparatorMenuItem())
        self._add_item("Columns…", "columns")

        self.show_all()

    def _add_item(self, label: str, name: str) -> Gtk.MenuItem:
        item = Gtk.MenuItem(label=label)
        item.connect("activate", self._on_activate, name)
        self.append(item)
        return item

    def _on_activate(self, _item: Gtk.MenuItem, name: str) -> None:
        self.emit("action", name, self._node)
