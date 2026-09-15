"""Base page — the starter's BasePage with a 24 px margin, a reference to the
window, and lifecycle hooks pages can override."""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from lindrivespace.config.layout import Layout  # noqa: E402

if TYPE_CHECKING:
    from lindrivespace.ui.window import MainWindow


class BasePage(Gtk.Box):
    """Vertical box with page margins. Subclasses implement ``build_content``."""

    page_id: str = ""
    title: str = ""

    def __init__(
        self,
        window: MainWindow,
        spacing: int = Layout.dimensions.CONTENT_SPACING,
        margin: int = Layout.dimensions.CONTENT_MARGIN,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
        self.window = window
        self.app = window.app
        self.theme = window.app.theme
        self.settings = window.app.settings
        self.get_style_context().add_class("page")
        # Margins are CSS padding on the page itself (class page-padded), so the page
        # paints its own gutter; widget margins would leave that band to the parent.
        if margin > 0:
            self.get_style_context().add_class("page-padded")
        self.build_content()

    # ---- hooks ------------------------------------------------------------

    def build_content(self) -> None:
        raise NotImplementedError("subclasses must implement build_content()")

    def on_shown(self) -> None:
        """Called each time the page becomes the visible stack child."""

    def on_hidden(self) -> None:
        """Called when another page replaces this one."""

    # ---- helpers (from the starter) --------------------------------------

    def add_title(self, text: str, subtitle: str | None = None) -> Gtk.Label:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label=text)
        title.get_style_context().add_class("page-title")
        title.set_xalign(0.0)
        box.pack_start(title, False, False, 0)
        if subtitle:
            sub = Gtk.Label(label=subtitle)
            sub.get_style_context().add_class("page-subtitle")
            sub.set_xalign(0.0)
            box.pack_start(sub, False, False, 0)
        self.pack_start(box, False, False, 0)
        return title

    def add_section(self, text: str) -> Gtk.Label:
        label = Gtk.Label(label=text)
        label.get_style_context().add_class("section-title")
        label.set_xalign(0.0)
        self.pack_start(label, False, False, 0)
        return label

    def add_paragraph(self, text: str, wrap: bool = True) -> Gtk.Label:
        label = Gtk.Label(label=text)
        label.set_line_wrap(wrap)
        label.set_xalign(0.0)
        label.get_style_context().add_class("paragraph")
        self.pack_start(label, False, False, 0)
        return label

    def add_separator(self) -> Gtk.Separator:
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.pack_start(sep, False, False, 0)
        return sep
