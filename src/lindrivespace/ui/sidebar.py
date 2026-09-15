"""Fixed 150 px sidebar with logo area and navigation.

Kept from the starter (``ui/sidebar.py``) with three changes: it takes the page
registry instead of a hard-coded list, each button has a symbolic icon, and the
starter's NavigationManager is gone — the window listens to ``page-changed``.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gtk  # noqa: E402

from lindrivespace import APP_ID, APP_NAME  # noqa: E402
from lindrivespace.config.layout import Layout  # noqa: E402
from lindrivespace.ui.pages import PageSpec  # noqa: E402


class Sidebar(Gtk.Box):
    __gtype_name__ = "LdsSidebar"
    __gsignals__ = {"page-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    def __init__(self, pages: list[PageSpec]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        dims = Layout.dimensions
        self.set_size_request(dims.SIDEBAR_WIDTH, -1)
        self.get_style_context().add_class("sidebar")
        self.buttons: dict[str, Gtk.Button] = {}
        self.active_id: str | None = None

        self._build_logo_area()
        self._build_navigation(pages)

    # ---- logo -------------------------------------------------------------

    def _build_logo_area(self) -> None:
        dims = Layout.dimensions
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)  # air between mark and name
        box.set_size_request(dims.SIDEBAR_WIDTH, dims.LOGO_AREA_HEIGHT)
        box.set_valign(Gtk.Align.FILL)
        box.get_style_context().add_class("logo-area")

        # The in-app mark (plain ring) — the desktop/menu icon is the tiled APP_ID icon.
        image = Gtk.Image.new_from_icon_name(f"{APP_ID}-mark", Gtk.IconSize.DIALOG)
        image.set_pixel_size(dims.LOGO_IMAGE_SIZE)
        image.set_valign(Gtk.Align.END)
        box.pack_start(image, True, True, 0)

        label = Gtk.Label(label=APP_NAME.upper())
        label.get_style_context().add_class("logo-text")
        label.set_valign(Gtk.Align.START)
        box.pack_start(label, True, True, 0)
        self.pack_start(box, False, False, 0)

    # ---- navigation -------------------------------------------------------

    def _build_navigation(self, pages: list[PageSpec]) -> None:
        top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        bottom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        first = True
        for spec in pages:
            button = self._make_button(spec, is_top=first and not spec.bottom)
            self.buttons[spec.id] = button
            if spec.bottom:
                button.get_style_context().add_class("nav-button-bottom")
                bottom.pack_start(button, False, False, 0)
            else:
                top.pack_start(button, False, False, 0)
                first = False
        self.pack_start(top, False, False, 0)
        self.pack_start(Gtk.Box(), True, True, 0)  # spacer pushes Settings down
        bottom.set_margin_bottom(Layout.spacing.SM)  # same breathing room as the logo area
        self.pack_start(bottom, False, False, 0)

    def _make_button(self, spec: PageSpec, is_top: bool) -> Gtk.Button:
        dims = Layout.dimensions
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.get_style_context().add_class("nav-button")
        if is_top:
            button.get_style_context().add_class("nav-button-top")
        button.set_size_request(-1, dims.NAV_BUTTON_HEIGHT)
        button.set_tooltip_text(spec.label)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        icon = Gtk.Image.new_from_icon_name(spec.icon, Gtk.IconSize.MENU)
        icon.set_pixel_size(dims.NAV_ICON_SIZE)
        row.pack_start(icon, False, False, 0)
        label = Gtk.Label(label=spec.label)
        label.set_xalign(0.0)
        row.pack_start(label, True, True, 0)
        button.add(row)
        button.connect("clicked", self._on_clicked, spec.id)
        return button

    # ---- state ------------------------------------------------------------

    def set_active(self, page_id: str) -> None:
        if self.active_id and self.active_id in self.buttons:
            self.buttons[self.active_id].get_style_context().remove_class("active")
        if page_id in self.buttons:
            self.buttons[page_id].get_style_context().add_class("active")
            self.active_id = page_id

    def _on_clicked(self, _button: Gtk.Button, page_id: str) -> None:
        if page_id == self.active_id:
            return
        self.set_active(page_id)
        self.emit("page-changed", page_id)
