"""Error trapping & logging (headless)."""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

from lindrivespace import logsetup


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_setup_creates_rotating_log(tmp_path: Path) -> None:
    path = logsetup.setup_logging(directory=tmp_path / "logs")
    assert path is not None and path.exists()
    logsetup.get_logger("test").warning("hello %s", "world")
    text = _read(path)
    assert "starting" in text and "hello world" in text
    assert logsetup.log_path() == path
    assert logsetup.log_dir()  # env/XDG based


def test_uncaught_exception_is_logged_and_reported(tmp_path: Path) -> None:
    path = logsetup.setup_logging(directory=tmp_path / "logs")
    assert path is not None
    seen: list[tuple[str, str]] = []
    logsetup.register_error_reporter(lambda h, d: seen.append((h, d)))
    try:
        raise ValueError("boom")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    assert seen and seen[0][0] == "ValueError: boom"
    assert "Traceback" in seen[0][1]
    assert "uncaught exception" in _read(path) and "boom" in _read(path)
    logsetup.register_error_reporter(None)


def test_thread_exception_hook(tmp_path: Path) -> None:
    path = logsetup.setup_logging(directory=tmp_path / "logs")
    seen: list[str] = []
    logsetup.register_error_reporter(lambda h, _d: seen.append(h))

    def bad() -> None:
        raise RuntimeError("thread failed")

    t = threading.Thread(target=bad, name="worker-x")
    t.start()
    t.join()
    assert seen and "RuntimeError in thread worker-x" in seen[0]
    assert path is not None and "thread failed" in _read(path)
    logsetup.register_error_reporter(None)


def test_log_exceptions_decorator_swallows_and_reports(tmp_path: Path) -> None:
    logsetup.setup_logging(directory=tmp_path / "logs")
    seen: list[str] = []
    logsetup.register_error_reporter(lambda h, _d: seen.append(h))

    @logsetup.log_exceptions
    def handler(_w: object) -> int:
        raise KeyError("missing")

    assert handler(None) is None
    assert seen and seen[0].startswith("KeyError")
    logsetup.register_error_reporter(None)


def test_debug_flag_lowers_stderr_level(tmp_path: Path) -> None:
    logsetup.setup_logging(debug=True, directory=tmp_path / "logs")
    root = logging.getLogger(logsetup.LOGGER_NAME)
    streams = [
        h
        for h in root.handlers
        if isinstance(h, logging.StreamHandler) and not hasattr(h, "baseFilename")
    ]
    assert streams and streams[0].level == logging.DEBUG
    logsetup.setup_logging(debug=False, directory=tmp_path / "logs")
    streams = [
        h
        for h in root.handlers
        if isinstance(h, logging.StreamHandler) and not hasattr(h, "baseFilename")
    ]
    assert streams[0].level == logging.WARNING


def test_unwritable_dir_falls_back_to_stderr(tmp_path: Path) -> None:
    blocked = tmp_path / "file-not-dir"
    blocked.write_text("x")
    path = logsetup.setup_logging(directory=blocked / "logs")
    assert path is None  # no file handler, but no exception either
    logsetup.get_logger().warning("still works")


def test_reconfigure_moves_the_log_file_and_level(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import logging

    from lindrivespace import logsetup

    logsetup.setup_logging(directory=tmp_path / "a")
    path = logsetup.reconfigure(directory=tmp_path / "b", level="warning")
    assert path == tmp_path / "b" / logsetup.LOG_FILE_NAME
    assert logsetup.log_path() == path and logsetup.current_level() == "warning"
    log = logsetup.get_logger("t")
    log.info("hidden")
    log.warning("kept")
    for h in logging.getLogger(logsetup.LOGGER_NAME).handlers:
        h.flush()
    text = path.read_text(encoding="utf-8")
    assert "kept" in text and "hidden" not in text
    assert logsetup.level_value("nonsense") == logging.INFO
