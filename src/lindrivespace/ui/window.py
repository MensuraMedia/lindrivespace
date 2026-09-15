"""Main application window: HeaderBar + Sidebar + Gtk.Stack of pages.

Merges the starter's dashboard_window.py and content_area.py. Shared file:
edited only by the orchestrator between work-package groups.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from lindrivespace import APP_NAME  # noqa: E402
from lindrivespace.config.layout import Layout  # noqa: E402
from lindrivespace.ui.pages import DEFAULT_PAGE, PAGES, PageSpec  # noqa: E402
from lindrivespace.ui.pages.base import BasePage  # noqa: E402
from lindrivespace.ui.sidebar import Sidebar  # noqa: E402

if TYPE_CHECKING:
    from lindrivespace.app import LinDriveSpaceApp


class MainWindow(Gtk.ApplicationWindow):
    __gtype_name__ = "LdsMainWindow"

    def __init__(self, app: LinDriveSpaceApp) -> None:
        super().__init__(application=app, title=APP_NAME)
        self.app = app
        dims = Layout.dimensions
        self.set_default_size(
            int(app.settings.get("window.width", dims.WINDOW_DEFAULT_WIDTH)),
            int(app.settings.get("window.height", dims.WINDOW_DEFAULT_HEIGHT)),
        )
        self.set_size_request(dims.WINDOW_MIN_WIDTH, dims.WINDOW_MIN_HEIGHT)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.get_style_context().add_class("lds-window")

        self.pages: dict[str, BasePage] = {}
        self.specs: dict[str, PageSpec] = {s.id: s for s in PAGES}
        self.current_page_id: str | None = None
        # mountpoint/path -> ISO "YYYY-MM-DD HH:MM" of the last completed scan (session only)
        self.scan_history: dict[str, str] = {}

        self._build_headerbar()
        self._build_body()
        self.show_page(DEFAULT_PAGE)
        self.connect("delete-event", self._on_delete)

    # ---- header -----------------------------------------------------------

    def _build_headerbar(self) -> None:
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.get_style_context().add_class("lds-header")

        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.title_label = Gtk.Label(label=APP_NAME)
        self.title_label.get_style_context().add_class("header-title")
        self.subtitle_label = Gtk.Label(label="")
        self.subtitle_label.get_style_context().add_class("header-subtitle")
        title_box.pack_start(self.title_label, False, False, 0)
        title_box.pack_start(self.subtitle_label, False, False, 0)
        header.pack_start(title_box)

        # Pages may place a widget here (scan progress pill, filter entry).
        self.header_center = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_custom_title(self.header_center)

        self.header_end = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.pack_end(self.header_end)

        self.set_titlebar(header)
        self.headerbar = header

    def set_header_widget(self, widget: Gtk.Widget | None) -> None:
        for child in self.header_center.get_children():
            self.header_center.remove(child)
        if widget is not None:
            self.header_center.pack_start(widget, True, True, 0)
            widget.show_all()

    # ---- body -------------------------------------------------------------

    def _build_body(self) -> None:
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.add(body)

        self.sidebar = Sidebar(PAGES)
        self.sidebar.connect("page-changed", lambda _sb, pid: self.show_page(pid))
        body.pack_start(self.sidebar, False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        self.stack.get_style_context().add_class("content-area")
        body.pack_start(self.stack, True, True, 0)

        for spec in PAGES:
            self._instantiate_page(spec)

    def _instantiate_page(self, spec: PageSpec) -> None:
        page = spec.factory(self)
        page.page_id = spec.id
        self.pages[spec.id] = page
        child: Gtk.Widget = page
        if spec.scrolled:
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scrolled.add(page)
            child = scrolled
        self.stack.add_named(child, spec.id)

    # ---- navigation -------------------------------------------------------

    def show_page(self, page_id: str) -> None:
        if page_id not in self.pages or page_id == self.current_page_id:
            return
        if self.current_page_id:
            self.pages[self.current_page_id].on_hidden()
        self.current_page_id = page_id
        self.stack.set_visible_child_name(page_id)
        self.sidebar.set_active(page_id)
        self.subtitle_label.set_text(self.specs[page_id].label)
        self.pages[page_id].on_shown()

    def request_scan(self, path: str) -> None:
        """Open the Explorer on ``path`` and start scanning (ExplorerPage.start_scan)."""
        self.show_page("explorer")
        explorer = self.pages.get("explorer")
        start = getattr(explorer, "start_scan", None)
        if callable(start):
            start(path)
        else:
            print(f"scan requested for {path} (explorer not yet implemented)")

    def record_scan(self, path: str, when: str | None = None) -> None:
        """Called by the Explorer when a scan finishes; the Overview shows it on the card."""
        import time

        self.scan_history[path] = when or time.strftime("%Y-%m-%d %H:%M")
        overview = self.pages.get("overview")
        refresh = getattr(overview, "refresh_scan_history", None)
        if callable(refresh):
            refresh()

    # ---- persistence ------------------------------------------------------

    def _on_delete(self, *_args: object) -> bool:
        width, height = self.get_size()
        self.app.settings.set("window.width", width)
        self.app.settings.set("window.height", height)
        self.app.settings.set("window.maximized", self.is_maximized())
        try:
            self.app.settings.save()
        except OSError as exc:
            print(f"could not save settings: {exc}")
        return False
