"""Shared pytest configuration.

- ``tests/core`` runs headless.
- ``tests/ui`` and ``tests/models`` need a display: GTK3 has no offscreen GDK
  backend, so they are skipped when ``Gtk.init_check()`` fails (run them under
  ``DISPLAY=:0`` or ``broadwayd :9`` + ``GDK_BACKEND=broadway BROADWAY_DISPLAY=:9``).
- Every test gets an isolated XDG config/cache directory.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NEEDS_DISPLAY = ("tests/ui", "tests/models")


def _gtk_available() -> bool:
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk

        ok, _argv = Gtk.init_check([])
        return bool(ok)
    except Exception:  # noqa: BLE001 - any failure means "no display"
        return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _gtk_available():
        return
    skip = pytest.mark.skip(reason="no display for GTK (set DISPLAY or use broadwayd)")
    for item in items:
        rel = str(Path(str(item.fspath)).relative_to(ROOT)).replace(os.sep, "/")
        if rel.startswith(NEEDS_DISPLAY):
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def isolated_xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    cfg = tmp_path / "xdg-config"
    cache = tmp_path / "xdg-cache"
    cfg.mkdir()
    cache.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    yield tmp_path


@pytest.fixture
def project_root() -> Path:
    return ROOT
