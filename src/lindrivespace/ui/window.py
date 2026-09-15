"""Main application window: HeaderBar + Sidebar + Gtk.Stack of pages.

Merges the starter's dashboard_window.py and content_area.py. Shared file:
edited only by the orchestrator between work-package groups.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from lindrivespace import APP_NAME, logsetup  # noqa: E402
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
        # While the window is being resized the server may expose regions before GTK
        # repaints them; give every GdkWindow in the content our surface colour so
        # they never flash black.
        self.connect("realize", self._on_realize_backgrounds)
        self.connect("size-allocate", self._on_size_allocate_backgrounds)

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
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(outer)
        self._build_error_bar()
        outer.pack_start(self.error_bar, False, False, 0)
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        outer.pack_start(body, True, True, 0)
        self._body_box = body

        self.sidebar = Sidebar(PAGES)
        self.sidebar.connect("page-changed", lambda _sb, pid: self.show_page(pid))
        body.pack_start(self.sidebar, False, False, 0)

        # Content column: the scan banner (top of the content area) above the page stack.
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content.set_hexpand(True)
        content.set_vexpand(True)
        body.pack_start(content, True, True, 0)

        from lindrivespace.ui.widgets.scan_banner import ScanBanner

        self.scan_banner = ScanBanner(self.app.theme, self.app.scan_registry, self.app.format_bytes)
        content.pack_start(self.scan_banner, False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        # Size to the visible page only; otherwise the widest page (Explorer) forces a
        # minimum the window manager may not honour, and the overflow paints black.
        self.stack.set_hhomogeneous(False)
        self.stack.set_vhomogeneous(False)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        self.stack.get_style_context().add_class("content-area")
        content.pack_start(self.stack, True, True, 0)

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

    # ---- error reporting --------------------------------------------------

    def _build_error_bar(self) -> None:
        bar = Gtk.InfoBar()
        bar.set_message_type(Gtk.MessageType.ERROR)
        bar.set_show_close_button(True)
        bar.set_no_show_all(True)
        bar.get_style_context().add_class("error-bar")
        self.error_label = Gtk.Label(label="")
        self.error_label.set_xalign(0.0)
        self.error_label.set_line_wrap(True)
        self.error_label.set_selectable(True)
        bar.get_content_area().pack_start(self.error_label, True, True, 0)
        bar.add_button("Details…", 1)
        bar.add_button("Open log", 2)
        bar.connect("response", self._on_error_bar_response)
        self.error_bar = bar
        self._error_details = ""
        self._error_count = 0

    def report_error(self, headline: str, details: str = "") -> None:
        """Show a dismissable error bar (main thread only)."""
        self._error_count += 1
        self._error_details = details
        prefix = f"{self._error_count} errors · " if self._error_count > 1 else ""
        self.error_label.set_text(f"{prefix}{headline}")
        self.error_bar.show()
        self.error_label.show()
        self.error_bar.get_content_area().show_all()
        self.error_bar.get_action_area().show_all()

    def report_error_threadsafe(self, headline: str, details: str = "") -> None:
        """Safe to call from any thread (used by logsetup's hooks)."""
        GLib.idle_add(self.report_error, headline, details)

    def _on_error_bar_response(self, bar: Gtk.InfoBar, response: int) -> None:
        if response == 1:
            self._show_error_details()
        elif response == 2:
            self.open_log_folder()
        else:
            bar.hide()
            self._error_count = 0

    def _show_error_details(self) -> None:
        dialog = Gtk.Dialog(title="Error details", transient_for=self, modal=True)
        dialog.set_default_size(720, 420)
        dialog.add_button("Copy", 1)
        dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        view = Gtk.TextView()
        view.set_editable(False)
        view.set_monospace(True)
        text = self._error_details or self.error_label.get_text()
        log_file = logsetup.log_path()
        if log_file is not None:
            text += f"\n\nFull log: {log_file}"
        view.get_buffer().set_text(text)
        scrolled.add(view)
        dialog.get_content_area().pack_start(scrolled, True, True, 0)
        dialog.show_all()

        def on_response(d: Gtk.Dialog, response: int) -> None:
            if response == 1:
                clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
                clipboard.set_text(text, -1)
                return
            d.destroy()

        dialog.connect("response", on_response)

    def open_log_folder(self) -> None:
        log_file = logsetup.log_path()
        folder = str(log_file.parent) if log_file is not None else str(logsetup.log_dir())
        try:
            Gio.AppInfo.launch_default_for_uri(GLib.filename_to_uri(folder, None), None)
        except GLib.Error as exc:
            logsetup.get_logger("window").warning("could not open log folder: %s", exc)

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

    def request_scan(self, path: str, force: bool = False) -> None:
        """Open the Explorer on ``path``; reuse a finished scan unless ``force``."""
        self.show_page("explorer")
        explorer = self.pages.get("explorer")
        start = getattr(explorer, "start_scan", None)
        if callable(start):
            start(path, force=force)
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

    # ---- background safety on resize ----------------------------------------

    def _surface_rgba(self) -> Gdk.RGBA:
        r, g, b, a = self.app.theme.rgba("bg_surface_2", 1.0)
        return Gdk.RGBA(red=r, green=g, blue=b, alpha=a)

    def _paint_gdk_windows(self, widget: Gtk.Widget, rgba: Gdk.RGBA) -> None:
        gdk_window = widget.get_window()
        if gdk_window is not None and widget.get_has_window():
            try:
                gdk_window.set_background_rgba(rgba)
            except Exception:  # noqa: BLE001 - deprecated API; best effort
                pass
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children():
                self._paint_gdk_windows(child, rgba)

    def _on_realize_backgrounds(self, _widget: Gtk.Widget) -> None:
        GLib.idle_add(self._apply_backgrounds)

    def _on_size_allocate_backgrounds(self, _widget: Gtk.Widget, _alloc: Gdk.Rectangle) -> None:
        if not getattr(self, "_bg_applied", False):
            self._apply_backgrounds()

    def _apply_backgrounds(self) -> bool:
        rgba = self._surface_rgba()
        gdk_window = self.get_window()
        if gdk_window is not None:
            try:
                gdk_window.set_background_rgba(rgba)
            except Exception:  # noqa: BLE001
                pass
        self._paint_gdk_windows(self.stack, rgba)
        self._bg_applied = True
        return False

    # ---- persistence ------------------------------------------------------

    def _on_delete(self, *_args: object) -> bool:
        width, height = self.get_size()
        self.app.settings.set("window.width", width)
        self.app.settings.set("window.height", height)
        self.app.settings.set("window.maximized", self.is_maximized())
        try:
            self.app.settings.save()
        except OSError as exc:
            logsetup.get_logger("window").warning("could not save settings: %s", exc)
        return False
