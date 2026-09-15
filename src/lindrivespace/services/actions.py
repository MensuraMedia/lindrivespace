"""Best-effort desktop actions: file manager, terminal, clipboard, trash.

Every function here is best-effort: it catches its own failures, logs them to
stderr, and returns a falsy/empty result -- none of them raise. A single
unavailable desktop integration (no terminal emulator installed, no D-Bus
session, no trash backend) must never crash a click handler. Runs on the main
thread only (touches Gtk/Gdk/Gio).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

# (executable, extra-args template) -- cwd is passed separately via subprocess's
# ``cwd=`` so it always works even for emulators with no working-directory flag.
_TERMINALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("x-terminal-emulator", ()),
    ("gnome-terminal", ("--working-directory={path}",)),
    ("xfce4-terminal", ("--working-directory={path}",)),
    ("mate-terminal", ("--working-directory={path}",)),
    ("konsole", ("--workdir", "{path}")),
    ("alacritty", ("--working-directory", "{path}")),
    ("kitty", ("-d", "{path}")),
)


def open_in_file_manager(path: str | Path) -> bool:
    """Open ``path`` in the desktop's default file manager."""
    try:
        uri = GLib.filename_to_uri(str(path), None)
        return bool(Gio.AppInfo.launch_default_for_uri(uri, None))
    except (GLib.Error, ValueError, TypeError) as exc:
        print(f"actions: open_in_file_manager failed for {path}: {exc}", file=sys.stderr)
        return False


def open_terminal(path: str | Path) -> bool:
    """Open a terminal emulator with its working directory set to ``path``.

    Tries a fixed list of common emulators (in order) via ``shutil.which``;
    returns False if none is found on ``PATH``.
    """
    cwd = str(path)
    for exe, arg_template in _TERMINALS:
        found = shutil.which(exe)
        if not found:
            continue
        args = [found, *(part.format(path=cwd) for part in arg_template)]
        try:
            subprocess.Popen(args, cwd=cwd, start_new_session=True)
            return True
        except OSError as exc:
            print(f"actions: open_terminal failed to launch {exe}: {exc}", file=sys.stderr)
            continue
    print("actions: no terminal emulator found on PATH", file=sys.stderr)
    return False


def copy_path(path: str | Path) -> None:
    """Copy ``path`` (as text) to the system clipboard."""
    try:
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(str(path), -1)
        clipboard.store()
    except (GLib.Error, RuntimeError) as exc:
        print(f"actions: copy_path failed: {exc}", file=sys.stderr)


def move_to_trash(path: str | Path) -> tuple[bool, str]:
    """Move ``path`` to the trash (never permanently deletes)."""
    try:
        Gio.File.new_for_path(str(path)).trash(None)
        return True, ""
    except GLib.Error as exc:
        print(f"actions: move_to_trash failed for {path}: {exc}", file=sys.stderr)
        return False, exc.message


def confirm_trash(parent_window: Gtk.Window | None, path: str | Path, size_text: str) -> bool:
    """Ask "Move <name> (<size>) to the trash?"; True means proceed.

    A function (not a method) so pages can call it directly; tests must never
    call this -- it blocks on a real ``Gtk.MessageDialog``.
    """
    name = Path(path).name or str(path)
    dialog = Gtk.MessageDialog(
        transient_for=parent_window,
        modal=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.OK_CANCEL,
        text=f"Move {name} ({size_text}) to the trash?",
    )
    try:
        response = dialog.run()
    finally:
        dialog.destroy()
    return response == Gtk.ResponseType.OK


def reveal_in_file_manager(path: str | Path) -> bool:
    """Select ``path`` in the file manager via the FileManager1 D-Bus API.

    Nemo (Mint's default) implements ``org.freedesktop.FileManager1.ShowItems``.
    Falls back to opening the containing directory when the D-Bus call fails
    for any reason (no such service, no session bus, timeout, ...).
    """
    try:
        uri = GLib.filename_to_uri(str(path), None)
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        proxy = Gio.DBusProxy.new_sync(
            bus,
            Gio.DBusProxyFlags.NONE,
            None,
            "org.freedesktop.FileManager1",
            "/org/freedesktop/FileManager1",
            "org.freedesktop.FileManager1",
            None,
        )
        proxy.call_sync(
            "ShowItems",
            GLib.Variant("(ass)", ([uri], "")),
            Gio.DBusCallFlags.NONE,
            2000,
            None,
        )
        return True
    except (GLib.Error, ValueError, TypeError) as exc:
        print(f"actions: reveal_in_file_manager D-Bus failed, falling back: {exc}", file=sys.stderr)
        return open_in_file_manager(str(Path(path).parent))
