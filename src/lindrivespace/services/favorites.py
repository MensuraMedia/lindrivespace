"""FavoritesStore: persisted list of user-starred folders/files.

A thin ``GObject.GObject`` wrapper around ``Settings["favorites"]`` (a list of
``{"path", "label", "added"}`` dicts, see ``config/settings.py``'s
``DEFAULTS``) so the Favorites page and the Explorer (star action) can share
one instance and react to a ``changed`` signal. ``Favorite.is_dir`` is
computed at read time via ``os.path.isdir`` -- never persisted -- so it always
reflects the current filesystem state rather than what it was when starred.

GTK-free except for ``GObject`` itself (no ``Gtk``/``Gdk`` import), so it can
be constructed and unit-tested without a display.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GObject  # noqa: E402

from lindrivespace.config.settings import Settings  # noqa: E402


@dataclass(frozen=True)
class Favorite:
    path: str
    label: str
    added: str
    is_dir: bool


def _default_label(path: str) -> str:
    """Basename of ``path``, or ``path`` itself when that's empty (e.g. "/")."""
    return os.path.basename(path.rstrip(os.sep)) or path


class FavoritesStore(GObject.GObject):
    """Owns the favorites list; every mutation persists and emits ``changed``."""

    __gtype_name__ = "LdsFavoritesStore"
    __gsignals__ = {"changed": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    # ---- reads --------------------------------------------------------

    def _records(self) -> list[dict[str, str]]:
        raw = self._settings.get("favorites", [])
        return list(raw) if isinstance(raw, list) else []

    def list(self) -> list[Favorite]:
        """Favorites in insertion (persisted) order."""
        return [self._to_favorite(rec) for rec in self._records()]

    def is_favorite(self, path: str) -> bool:
        norm = os.path.abspath(path)
        return any(rec.get("path") == norm for rec in self._records())

    def get(self, path: str) -> Favorite | None:
        norm = os.path.abspath(path)
        for rec in self._records():
            if rec.get("path") == norm:
                return self._to_favorite(rec)
        return None

    # ---- mutations ------------------------------------------------------

    def add(self, path: str, label: str | None = None) -> Favorite:
        """Add ``path`` (normalised via ``os.path.abspath``); a no-op returning the
        existing entry when it's already a favorite (duplicates are ignored)."""
        norm = os.path.abspath(path)
        records = self._records()
        for rec in records:
            if rec.get("path") == norm:
                return self._to_favorite(rec)
        record = {
            "path": norm,
            "label": label or _default_label(norm),
            "added": time.strftime("%Y-%m-%d %H:%M"),
        }
        records.append(record)
        self._persist(records)
        return self._to_favorite(record)

    def remove(self, path: str) -> None:
        norm = os.path.abspath(path)
        records = [rec for rec in self._records() if rec.get("path") != norm]
        self._persist(records)

    def toggle(self, path: str) -> bool:
        """Add or remove ``path``; returns the new favorite state."""
        if self.is_favorite(path):
            self.remove(path)
            return False
        self.add(path)
        return True

    def rename(self, path: str, label: str) -> None:
        norm = os.path.abspath(path)
        records = self._records()
        for rec in records:
            if rec.get("path") == norm:
                rec["label"] = label
                break
        self._persist(records)

    def move(self, path: str, new_index: int) -> None:
        """Reorder ``path`` to ``new_index`` (clamped) in the persisted list."""
        norm = os.path.abspath(path)
        records = self._records()
        idx = next((i for i, rec in enumerate(records) if rec.get("path") == norm), None)
        if idx is None:
            return
        record = records.pop(idx)
        records.insert(max(0, min(new_index, len(records))), record)
        self._persist(records)

    # ---- helpers --------------------------------------------------------

    def scan_target(self, fav: Favorite) -> str:
        """The directory to scan for ``fav``: itself for a folder, its parent for a file."""
        return fav.path if fav.is_dir else os.path.dirname(fav.path)

    def _to_favorite(self, rec: dict[str, str]) -> Favorite:
        path = rec.get("path", "")
        return Favorite(
            path=path,
            label=rec.get("label") or _default_label(path),
            added=rec.get("added", ""),
            is_dir=os.path.isdir(path),
        )

    def _persist(self, records: list[dict[str, str]]) -> None:
        self._settings.set("favorites", records)
        self._settings.save()
        self.emit("changed")


_STORE_ATTR = "favorites_store"


def get_store(app: object) -> FavoritesStore:
    """Return ``app``'s shared :class:`FavoritesStore`, creating it on first use.

    Cached as a plain attribute on the application object (``app.favorites_store``)
    so the Favorites page and the Explorer's star action share one instance and
    see each other's ``changed`` emissions.
    """
    store = getattr(app, _STORE_ATTR, None)
    if store is None:
        store = FavoritesStore(app.settings)  # type: ignore[attr-defined]
        setattr(app, _STORE_ATTR, store)
    return store
