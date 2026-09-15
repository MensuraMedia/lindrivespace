"""M0 smoke tests: the window builds, pages switch, no GTK warnings."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
GTK_NOISE = ("Gtk-CRITICAL", "Gtk-WARNING", "Theme parsing", "Traceback")


def _run(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONPATH=str(SRC))
    return subprocess.run(
        [sys.executable, "-m", "lindrivespace", *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def test_smoke_run_exits_quietly() -> None:
    result = _run("--smoke")
    assert result.returncode == 0, result.stderr
    for needle in GTK_NOISE:
        assert needle not in result.stderr, result.stderr


def test_screenshot_renders(tmp_path: Path) -> None:
    out = tmp_path / "m0.png"
    result = _run("--screenshot", str(out))
    assert result.returncode == 0, result.stderr
    assert out.exists() and out.stat().st_size > 1000
    with open(out, "rb") as fh:
        assert fh.read(8) == b"\x89PNG\r\n\x1a\n"


def test_pages_register_and_switch(window) -> None:  # type: ignore[no-untyped-def]
    from lindrivespace.ui.pages import PAGES

    assert set(window.pages) == {p.id for p in PAGES}
    window.show_page("overview")
    assert window.current_page_id == "overview"
    assert window.sidebar.active_id == "overview"
    window.show_page("explorer")
    assert window.stack.get_visible_child_name() == "explorer"
    assert window.sidebar.active_id == "explorer"
    assert window.page_title == "Explorer"
    assert "Explorer" in window.title_label.get_text()
    # sidebar click drives the window
    window.sidebar.buttons["settings"].clicked()
    assert window.current_page_id == "settings"


def test_theme_css_loaded(window) -> None:  # type: ignore[no-untyped-def]
    loader = window.app.theme_loader
    assert loader.current is not None and loader.current.id == "gray-temperature-dark"
    css = loader.build_css(loader.current)
    assert "@define-color accent #e95420;" in css
    assert ".nav-button.active" in css
