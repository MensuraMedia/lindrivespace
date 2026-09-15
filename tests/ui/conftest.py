"""One application window per test session.

A ``Gtk.Application`` with an application id can be registered only once per
process (D-Bus export), so every UI test module shares this fixture instead of
building its own. Tests must leave the window on a sane page; they may switch
pages freely.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session")
def window(tmp_path_factory: pytest.TempPathFactory) -> Iterator[object]:
    """The shared window uses its own config/cache/log directories for the whole
    session, whatever the per-test ``isolated_xdg`` fixture does later: the app is
    built once, and it must never read or write the developer's real settings."""
    import os

    from lindrivespace.app import LinDriveSpaceApp
    from lindrivespace.config.settings import Settings

    base = tmp_path_factory.mktemp("lds-session")
    for var, sub in (("XDG_CONFIG_HOME", "config"), ("XDG_CACHE_HOME", "cache")):
        (base / sub).mkdir()
        os.environ[var] = str(base / sub)
    os.environ["LINDRIVESPACE_LOG_DIR"] = str(base / "logs")
    settings = Settings(base / "config" / "lindrivespace" / "settings.json")
    app = LinDriveSpaceApp(smoke=True, settings=settings)
    app.register(None)
    app.do_startup()
    win = app.build_window()
    win.show_all()
    yield win
    win.destroy()
