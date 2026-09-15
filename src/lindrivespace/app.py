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
from gi.repository import Gdk, Gio, GLib, GObject, Gtk  # noqa: E402

from lindrivespace import APP_ID, APP_NAME, __version__, logsetup  # noqa: E402
from lindrivespace.config.settings import Settings  # noqa: E402
from lindrivespace.config.theme import get_theme  # noqa: E402
from lindrivespace.core import units  # noqa: E402
from lindrivespace.core.options import DEFAULT_EXCLUDES, ScanOptions  # noqa: E402
from lindrivespace.models.tree_model import ScanTreeModel  # noqa: E402
from lindrivespace.services.scan_registry import ScanRegistry  # noqa: E402
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


class HistorySignal(GObject.GObject):
    """Emits ``changed`` whenever a history sample is recorded (pages redraw)."""

    __gsignals__ = {"changed": (GObject.SignalFlags.RUN_FIRST, None, ())}


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
        self.scan_registry = ScanRegistry(self.make_model, self.make_scan_options)
        self._auto_scan_attempts = 0
        self.history = self._open_history()
        self.history_signal = HistorySignal()
        self._usage_timer = 0

    # ---- history recording (automatic, between runs) ----------------------------

    def _open_history(self):  # type: ignore[no-untyped-def]
        try:
            from lindrivespace.core.history import HistoryStore, default_history_path
        except ImportError:  # the history module ships with WP17
            return None
        try:
            return HistoryStore(default_history_path())
        except Exception as exc:  # noqa: BLE001 - never block startup on the history file
            self.log.error("history store unavailable: %s", exc)
            return None

    def record_usage_samples(self, mounts: list[object]) -> int:
        """Called by the Overview after every mount refresh (throttled by the store)."""
        if self.history is None:
            return 0
        written = 0
        for m in mounts:
            mountpoint = getattr(m, "mountpoint", "")
            total = int(getattr(m, "total", 0) or 0)
            used = int(getattr(m, "used", 0) or 0)
            if not mountpoint or total <= 0 or getattr(m, "hidden", False):
                continue
            try:
                if self.history.add_sample(mountpoint, used=used, total=total, source="usage"):
                    written += 1
            except Exception as exc:  # noqa: BLE001
                self.log.warning("history sample failed for %s: %s", mountpoint, exc)
        if written:
            self.history_signal.emit("changed")
        return written

    def record_scan_sample(self, path: str, alloc: int, entries: int) -> None:
        if self.history is None:
            return
        used = total = 0
        try:
            if os.path.ismount(path):
                st = os.statvfs(path)
                total = st.f_blocks * st.f_frsize
                used = (st.f_blocks - st.f_bfree) * st.f_frsize
        except OSError:
            pass
        try:
            self.history.add_sample(
                path, used=used, total=total, source="scan", alloc=alloc, entries=entries
            )
            self.history_signal.emit("changed")
        except Exception as exc:  # noqa: BLE001
            self.log.warning("history scan sample failed for %s: %s", path, exc)

    # ---- scan factories (shared by the Explorer and the startup queue) -------

    def format_bytes(self, n: int) -> str:
        return units.format_bytes(n, binary=self.settings.get("units", "decimal") == "binary")

    def make_model(self) -> ScanTreeModel:
        return ScanTreeModel(
            fmt_bytes=self.format_bytes,
            allocated_primary=self.settings.get("primary_size", "allocated") == "allocated",
            top_n_bold=int(self.settings.get("explorer.top_n_bold", 3)),
            show_hidden=bool(self.settings.get("scan.show_hidden", True)),
        )

    def make_scan_options(self) -> ScanOptions:
        scan = self.settings.get("scan", {}) or {}
        return ScanOptions(
            follow_symlinks=bool(scan.get("follow_symlinks", False)),
            cross_mounts=bool(scan.get("cross_mounts", False)),
            count_hardlinks_once=bool(scan.get("count_hardlinks_once", True)),
            show_hidden=bool(scan.get("show_hidden", True)),
            excludes=tuple(scan.get("excludes", DEFAULT_EXCLUDES)),
            top_files=int(scan.get("top_files", 50)),
        )

    # ---- startup auto-scan -----------------------------------------------------

    def auto_scan_order(self) -> list[str]:
        """Mountpoints to scan at startup: primary, secondary, /, then the rest."""
        window = self.window
        overview = window.pages.get("overview") if window is not None else None
        known = list(getattr(overview, "known_mountpoints", list)())
        if not known:
            return []
        roles = getattr(overview, "mount_roles", dict)()
        first = [mp for mp, role in roles.items() if role == "primary" and mp in known]
        second = [mp for mp, role in roles.items() if role == "secondary" and mp in known]
        ordered = first + second + (["/"] if "/" in known else [])
        return ordered + [mp for mp in known if mp not in ordered]

    def _on_scan_entry_changed(self, registry: ScanRegistry, path: str) -> None:
        entry = registry.get(path)
        if entry is not None and entry.state == "done" and self.window is not None:
            if self.window.scan_history.get(path) != entry.finished_text:
                self.window.record_scan(path, entry.finished_text)
                self.record_scan_sample(path, entry.alloc, entry.entries)
                self.autosave_snapshot(path, entry)

    KEEP_SNAPSHOTS_PER_PATH = 12

    def autosave_snapshot(self, path: str, entry: object) -> None:
        """Keep a compact snapshot of every finished scan so History can show *where*
        space changed (folder/file diffs between two points in time). Serialising a
        large tree takes seconds, so it runs on a worker thread; the FsNode tree is
        immutable once a scan has finished."""
        model = getattr(entry, "model", None)
        root = getattr(model, "root", None)
        if root is None:
            return
        import threading

        keep = self.KEEP_SNAPSHOTS_PER_PATH
        log = self.log

        def work() -> None:
            try:
                from lindrivespace.core.snapshot import (
                    default_snapshot_dir,
                    list_snapshots,
                    save_snapshot,
                    snapshot_filename,
                )

                directory = default_snapshot_dir()
                directory.mkdir(parents=True, exist_ok=True)
                save_snapshot(root, directory / snapshot_filename(path), {"auto": True})
                mine = sorted(
                    (m for m in list_snapshots(directory) if m.root_path == path),
                    key=lambda m: m.saved_at,
                )
                for old in mine[:-keep]:
                    try:
                        Path(old.path).unlink()
                    except OSError:
                        pass
                log.info("snapshot saved for %s (%d kept)", path, min(len(mine), keep))
            except Exception as exc:  # noqa: BLE001 - bookkeeping must never break the app
                log.warning("auto snapshot failed for %s: %s", path, exc)

        threading.Thread(target=work, name=f"snapshot:{path}", daemon=True).start()

    def _auto_scan_tick(self) -> bool:
        """Wait (up to ~20 s) for the mount list, then queue every mount."""
        self._auto_scan_attempts += 1
        order = self.auto_scan_order()
        if not order:
            return self._auto_scan_attempts < 40  # retry every 500 ms
        self.log.info("auto-scan queue: %s", ", ".join(order))
        self.scan_registry.enqueue(order)
        return False

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
        self.scan_registry.connect("entry-changed", self._on_scan_entry_changed)
        if self.open_paths:
            window.request_scan(self.open_paths[0], force=True)
        elif not self.smoke and bool(self.settings.get("scan.auto_on_start", True)):
            # Screenshot runs stay deterministic unless asked to include the auto-scan.
            if not self.screenshot or os.environ.get("LINDRIVESPACE_SCREENSHOT_AUTOSCAN") == "1":
                GLib.timeout_add(1500, self._auto_scan_tick)
        if self.screenshot:
            delay = int(os.environ.get("LINDRIVESPACE_SCREENSHOT_DELAY_MS", "1200"))
            GLib.timeout_add(delay, self._take_screenshot, self.screenshot)
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
