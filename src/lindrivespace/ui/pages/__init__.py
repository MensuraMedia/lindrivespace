"""Page registry.

The starter wired pages by hand in three files (sidebar, content_area, nav
manager). Here one list drives the sidebar buttons and the Gtk.Stack. Page
modules are imported lazily by the factory so a broken page never prevents the
window from opening.

Shared file: edited only by the orchestrator (see .claude/rules/python-gtk.md).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lindrivespace.ui.pages.base import BasePage
    from lindrivespace.ui.window import MainWindow


@dataclass(frozen=True)
class PageSpec:
    id: str
    label: str
    icon: str  # symbolic icon name
    factory: Callable[[MainWindow], BasePage]
    scrolled: bool = True  # wrap in a ScrolledWindow (False for pages that scroll themselves)
    bottom: bool = False  # pinned to the bottom of the sidebar


def _overview(window: MainWindow) -> BasePage:
    from lindrivespace.ui.pages.overview import OverviewPage

    return OverviewPage(window)


def _explorer(window: MainWindow) -> BasePage:
    from lindrivespace.ui.pages.explorer import ExplorerPage

    return ExplorerPage(window)


def _favorites(window: MainWindow) -> BasePage:
    from lindrivespace.ui.pages.favorites import FavoritesPage

    return FavoritesPage(window)


def _snapshots(window: MainWindow) -> BasePage:
    from lindrivespace.ui.pages.snapshots import SnapshotsPage

    return SnapshotsPage(window)


def _hardware(window: MainWindow) -> BasePage:
    from lindrivespace.ui.pages.hardware import HardwarePage

    return HardwarePage(window)


def _glossary(window: MainWindow) -> BasePage:
    from lindrivespace.ui.pages.glossary import GlossaryPage

    return GlossaryPage(window)


def _settings(window: MainWindow) -> BasePage:
    from lindrivespace.ui.pages.settings import SettingsPage

    return SettingsPage(window)


PAGES: list[PageSpec] = [
    PageSpec("overview", "Overview", "go-home-symbolic", _overview),
    PageSpec("explorer", "Explorer", "view-list-symbolic", _explorer, scrolled=False),
    PageSpec("favorites", "Favorites", "starred-symbolic", _favorites),
    PageSpec("snapshots", "Snapshots", "document-save-symbolic", _snapshots),
    PageSpec("hardware", "Hardware", "computer-symbolic", _hardware),
    PageSpec("glossary", "Glossary", "accessories-dictionary-symbolic", _glossary, scrolled=False),
    PageSpec("settings", "Settings", "emblem-system-symbolic", _settings, bottom=True),
]

DEFAULT_PAGE = "overview"
