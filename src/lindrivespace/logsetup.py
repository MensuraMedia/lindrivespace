"""Error trapping and logging.

* Rotating log file under ``$XDG_CACHE_HOME/lindrivespace/logs/`` (1 MB × 5),
  DEBUG level; stderr at WARNING (DEBUG with ``--debug``).
* Every uncaught exception — main thread, worker threads, and GTK/GLib
  callbacks (PyGObject routes those through ``sys.excepthook``) — is logged
  with its traceback and handed to a registered UI reporter (the main window
  shows an error bar with a details dialog).
* GTK/GLib/GDK/Pango warnings and criticals (``g_log``) are captured into the
  same log so "Gtk-CRITICAL" lines are never lost.
* ``log_exceptions`` decorates signal handlers so one bad callback cannot
  take down the main loop silently.

GTK-free apart from the optional GLib hook, so the core helper can use it too.
"""

from __future__ import annotations

import functools
import logging
import os
import sys
import threading
import traceback
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, TypeVar

from lindrivespace import APP_NAME, __version__
from lindrivespace.config.settings import cache_dir

LOGGER_NAME = "lindrivespace"
LOG_FILE_NAME = "lindrivespace.log"
_MAX_BYTES = 1_000_000
_BACKUPS = 5

ErrorReporter = Callable[[str, str], None]  # (headline, details)

_state: dict[str, Any] = {"path": None, "reporter": None, "installed": False}
F = TypeVar("F", bound=Callable[..., Any])


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)


def log_dir() -> Path:
    override = os.environ.get("LINDRIVESPACE_LOG_DIR")
    return Path(override) if override else cache_dir() / "logs"


def log_path() -> Path | None:
    return _state["path"]


def register_error_reporter(reporter: ErrorReporter | None) -> None:
    """The UI registers a callable(headline, details) shown on uncaught errors."""
    _state["reporter"] = reporter


def setup_logging(*, debug: bool = False, directory: Path | None = None) -> Path | None:
    """Install file + stderr handlers and the exception hooks. Idempotent."""
    root = logging.getLogger(LOGGER_NAME)
    root.setLevel(logging.DEBUG)
    root.propagate = False
    for handler in list(root.handlers):
        root.removeHandler(handler)

    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    stream = logging.StreamHandler(sys.stderr)
    stream.setLevel(logging.DEBUG if debug else logging.WARNING)
    stream.setFormatter(fmt)
    root.addHandler(stream)

    path: Path | None = None
    target_dir = directory or log_dir()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / LOG_FILE_NAME
        file_handler = RotatingFileHandler(
            path, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError as exc:  # read-only cache dir: keep going with stderr only
        root.warning("log file unavailable (%s): %s", target_dir, exc)
    _state["path"] = path

    if not _state["installed"]:
        _install_hooks()
        _state["installed"] = True

    root.info(
        "%s %s starting (pid %d, python %s)",
        APP_NAME,
        __version__,
        os.getpid(),
        sys.version.split()[0],
    )
    return path


# ---- hooks --------------------------------------------------------------------


def _format_exc(exc_type: type[BaseException], exc: BaseException, tb: Any) -> str:
    return "".join(traceback.format_exception(exc_type, exc, tb))


def _report(headline: str, details: str) -> None:
    reporter = _state.get("reporter")
    if reporter is None:
        return
    try:
        reporter(headline, details)
    except Exception:  # noqa: BLE001 - the reporter must never recurse into the hook
        logging.getLogger(LOGGER_NAME).exception("error reporter failed")


def _excepthook(exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    details = _format_exc(exc_type, exc, tb)
    logging.getLogger(LOGGER_NAME).error("uncaught exception:\n%s", details)
    _report(f"{exc_type.__name__}: {exc}", details)


def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
    if args.exc_type is SystemExit:
        return
    details = _format_exc(args.exc_type, args.exc_value or args.exc_type(), args.exc_traceback)
    name = args.thread.name if args.thread else "?"
    logging.getLogger(LOGGER_NAME).error("uncaught exception in thread %s:\n%s", name, details)
    _report(f"{args.exc_type.__name__} in thread {name}", details)


def _install_hooks() -> None:
    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook
    _install_glib_hook()


_GLIB_DOMAINS = ("Gtk", "Gdk", "GLib", "GLib-GObject", "GLib-GIO", "Pango", "GdkPixbuf", None)


def _install_glib_hook() -> None:
    """Route g_log() warnings/criticals from GTK & friends into our log."""
    try:
        import gi

        gi.require_version("GLib", "2.0")
        from gi.repository import GLib
    except Exception:  # noqa: BLE001 - core helper without GI
        return

    logger = logging.getLogger(f"{LOGGER_NAME}.glib")
    levels = {
        GLib.LogLevelFlags.LEVEL_ERROR: logging.CRITICAL,
        GLib.LogLevelFlags.LEVEL_CRITICAL: logging.ERROR,
        GLib.LogLevelFlags.LEVEL_WARNING: logging.WARNING,
        GLib.LogLevelFlags.LEVEL_MESSAGE: logging.INFO,
        GLib.LogLevelFlags.LEVEL_INFO: logging.INFO,
        GLib.LogLevelFlags.LEVEL_DEBUG: logging.DEBUG,
    }
    mask = (
        GLib.LogLevelFlags.LEVEL_ERROR
        | GLib.LogLevelFlags.LEVEL_CRITICAL
        | GLib.LogLevelFlags.LEVEL_WARNING
        | GLib.LogLevelFlags.LEVEL_MESSAGE
    )

    def handler(domain: str | None, level: Any, message: str, _data: object = None) -> None:
        py_level = logging.WARNING
        for flag, mapped in levels.items():
            if level & flag:
                py_level = mapped
                break
        logger.log(py_level, "%s: %s", domain or "GLib", message)
        if py_level >= logging.ERROR:
            _report(f"{domain or 'GLib'} critical", message)

    for domain in _GLIB_DOMAINS:
        try:
            GLib.log_set_handler(domain, mask, handler, None)
        except TypeError:
            # Some PyGObject builds reject a None domain; the named ones still work.
            continue


# ---- helpers --------------------------------------------------------------------


def log_exceptions(func: F) -> F:
    """Decorator for signal handlers/callbacks: log and report, never propagate."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - deliberately catch-all at the boundary
            details = traceback.format_exc()
            logging.getLogger(LOGGER_NAME).error("error in %s:\n%s", func.__qualname__, details)
            _report(f"{type(exc).__name__}: {exc}", details)
            return None

    return wrapper  # type: ignore[return-value]


def crash_report(headline: str, details: str) -> None:
    """Explicitly log + report a caught error (e.g. a failed scan helper)."""
    logging.getLogger(LOGGER_NAME).error("%s\n%s", headline, details)
    _report(headline, details)
