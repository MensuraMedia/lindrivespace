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
def window() -> Iterator[object]:
    from lindrivespace.app import LinDriveSpaceApp

    app = LinDriveSpaceApp(smoke=True)
    app.register(None)
    app.do_startup()
    win = app.build_window()
    win.show_all()
    yield win
    win.destroy()
