"""Persisted user settings: a small JSON file under $XDG_CONFIG_HOME/lindrivespace.

GTK-free on purpose (tests and the CLI use it too). Unknown keys are preserved
so newer versions can add settings without clobbering older files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

from lindrivespace.config.theme import DEFAULT_THEME_ID
from lindrivespace.core.options import DEFAULT_EXCLUDES

APP_DIR_NAME = "lindrivespace"

DEFAULTS: dict[str, Any] = {
    "theme": DEFAULT_THEME_ID,
    "units": "decimal",  # decimal (GB) | binary (GiB)
    "primary_size": "allocated",  # allocated | apparent
    "scan": {
        "follow_symlinks": False,
        "cross_mounts": False,
        "count_hardlinks_once": True,
        "show_hidden": True,
        "excludes": list(DEFAULT_EXCLUDES),
        "top_files": 50,
        "auto_on_start": True,  # scan every visible mount a few seconds after launch
    },
    "mounts": {
        "hidden_fstypes": [
            "squashfs",
            "tmpfs",
            "devtmpfs",
            "proc",
            "sysfs",
            "cgroup",
            "cgroup2",
            "overlay",
            "fuse.portal",
            "efivarfs",
            "autofs",
        ],
        "show_hidden": False,
        # Mountpoints the user cares about most; badged and listed first on the Overview.
        "primary": "",
        "secondary": "",
    },
    "window": {"width": 1200, "height": 800, "maximized": False, "panel_visible": True},
    # Favourite folders/files: [{"path": str, "label": str, "added": "YYYY-MM-DD HH:MM"}]
    "favorites": [],
    "explorer": {
        # Column order is user-reorderable by dragging headers; persisted here.
        "columns": ["name", "size", "alloc", "files", "dirs", "percent", "modified"],
        # Optional columns the user can enable from the header context menu.
        "hidden_columns": ["owner", "type"],
        "widths": {},  # column id -> px, persisted after a drag-resize
        "sort": {"column": "alloc", "descending": True},
        "top_n_bold": 3,
    },
}


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / APP_DIR_NAME


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return Path(base) / APP_DIR_NAME


class Settings:
    """Dictionary-backed settings with dotted-path access and lazy saving."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (config_dir() / "settings.json")
        self._data: dict[str, Any] = _deep_copy(DEFAULTS)
        self.load()

    # ---- persistence ------------------------------------------------------

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                on_disk = json.load(fh)
        except (OSError, ValueError):
            return
        if isinstance(on_disk, dict):
            _deep_update(self._data, on_disk)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    # ---- access -----------------------------------------------------------

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self._data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def as_dict(self) -> dict[str, Any]:
        return _deep_copy(self._data)


def _deep_copy(d: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(json.dumps(d)))


def _deep_update(base: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
