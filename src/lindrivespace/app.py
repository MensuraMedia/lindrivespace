"""Gtk.Application for LinDriveSpace.

Replaces the starter's bare ``Gtk.Window`` + ``Gtk.main()``. Our own CLI options
are parsed with argparse *before* GTK sees argv, so ``--smoke`` and
``--screenshot`` can flip the application to NON_UNIQUE (a second instance must
not merely activate a running one when a test or agent launches it).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from lindrivespace import APP_ID, APP_NAME, __version__, logsetup  # noqa: E402
from lindrivespace.config.settings import Settings  # noqa: E402
from lindrivespace.config.theme import get_theme  # noqa: E402
from lindrivespace.ui.theme_loader import ThemeLoader  # noqa: E402
from lindrivespace.ui.window import MainWindow  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def data_path(*parts: str) -> Path:
    """Locate a file under data/ (checkout) or the installed share directory."""
    candidates = [
        DATA_DIR.joinpath(*parts),
        Path("/usr/share/lindrivespace").joinpath(*parts),
        Path("/usr/local/share/lindrivespace").joinpath(*parts),
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


class LinDriveSpaceApp(Gtk.Application):
    """Application object. ``build_window()`` is public so tests can construct the
    window without entering the main loop."""

    def __init__(
        self,
        *,
        open_paths: list[str] | None = None,
        smoke: bool = False,
        screenshot: str | None = None,
        theme_id: str | None = None,
        settings: Settings | None = None,
        debug: bool = False,
    ) -> None:
        flags = Gio.ApplicationFlags.HANDLES_OPEN
        if smoke or screenshot:
            flags |= Gio.ApplicationFlags.NON_UNIQUE
        super().__init__(application_id=APP_ID, flags=flags)
        self.debug = debug
        self.log = logsetup.get_logger("app")
        self.open_paths = list(open_paths or [])
        self.smoke = smoke
        self.screenshot = screenshot
        self.settings = settings or Settings()
        self.theme = get_theme(theme_id or self.settings.get("theme"))
        self.theme_loader = ThemeLoader(css_path=data_path("css", "app.css"))
        self.window: MainWindow | None = None

    # ---- lifecycle --------------------------------------------------------

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        GLib.set_application_name(APP_NAME)
        self.theme_loader.apply(self.theme)
        icon_dir = data_path("icons")
        if icon_dir.exists():
            Gtk.IconTheme.get_default().append_search_path(str(icon_dir))

    def do_activate(self) -> None:
        window = self.build_window()
        window.show_all()
        window.present()
        # Uncaught errors anywhere (main loop callbacks, threads) surface in the window.
        logsetup.register_error_reporter(window.report_error_threadsafe)
        if self.open_paths:
            window.request_scan(self.open_paths[0])
        if self.screenshot:
            GLib.timeout_add(1200, self._take_screenshot, self.screenshot)
        elif self.smoke:
            GLib.timeout_add(400, self._quit_after_smoke)

    def do_open(self, files: list[Gio.File], n_files: int, hint: str) -> None:
        self.open_paths = [f.get_path() for f in files if f.get_path()]
        self.do_activate()

    def build_window(self) -> MainWindow:
        if self.window is None:
            self.window = MainWindow(self)
        return self.window

    # ---- smoke / screenshot helpers --------------------------------------

    def _quit_after_smoke(self) -> bool:
        self.quit()
        return False

    def _take_screenshot(self, path: str) -> bool:
        """Grab the mapped window from the display server (CSD frame included).

        ``Gtk.Widget.draw`` on a CSD toplevel paints only the frame, so we read
        the pixels back through Gdk instead; it needs a real display.
        """
        assert self.window is not None
        gdk_window = self.window.get_window()
        if gdk_window is None:
            print("screenshot failed: window not realised", file=sys.stderr)
            self.quit()
            return False
        width, height = gdk_window.get_width(), gdk_window.get_height()
        pixbuf = Gdk.pixbuf_get_from_window(gdk_window, 0, 0, width, height)
        if pixbuf is None:
            self.log.error("screenshot failed: could not read window pixels")
            self.quit()
            return False
        pixbuf.savev(path, "png", [], [])
        print(f"screenshot written: {path} ({width}x{height})")
        self.quit()
        return False


# ---- CLI --------------------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="lindrivespace", description=APP_NAME)
    parser.add_argument("paths", nargs="*", help="folder(s) to open and scan")
    parser.add_argument("--smoke", action="store_true", help="build the window, then exit")
    parser.add_argument("--screenshot", metavar="PNG", help="render the window to PNG, then exit")
    parser.add_argument("--theme", help="theme id (gray-temperature-dark | gray-temperature-light)")
    parser.add_argument("--debug", action="store_true", help="verbose logging on stderr")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    log_file = logsetup.setup_logging(debug=args.debug)
    if args.debug and log_file is not None:
        print(f"log file: {log_file}", file=sys.stderr)
    app = LinDriveSpaceApp(
        open_paths=[os.path.abspath(p) for p in args.paths],
        smoke=args.smoke,
        screenshot=args.screenshot,
        theme_id=args.theme,
        debug=args.debug,
    )
    # GTK must not see our options: pass only argv[0].
    return int(app.run([sys.argv[0]]))
