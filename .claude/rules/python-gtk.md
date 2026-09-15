---
paths:
  - "src/**/*.py"
  - "tests/**/*.py"
---

# Python + GTK3 Rules (LinDriveSpace)

## Language
- Python 3.12, `from __future__ import annotations` not needed; use built-in generics (`list[str]`).
- Type hints on every public function; `mypy --strict` must pass for `src/lindrivespace/core/`.
- `ruff` (E, F, I, B, UP, N) clean; line length 100; `ruff format` style.
- Dataclasses for value objects; `__slots__` on hot-path classes (`FsNode`).
- No bare `except:`; catch `OSError` for filesystem races, never only `PermissionError`.

## GTK
- `gi.require_version('Gtk', '3.0')` before any `from gi.repository import Gtk`.
- All widget access on the main thread. Workers hand results over through `queue.SimpleQueue`
  drained by `GLib.timeout_add(16, ...)` with an 8 ms budget (`GLib.get_monotonic_time()`).
- Never enable GTK sorting on the tree store; `models/tree_model.py` owns row order.
- All `Gtk.TreeViewColumn`s use `sizing=Gtk.TreeViewColumnSizing.FIXED`; the view runs in fixed-height mode.
- Custom drawing goes through `Gtk.CellRenderer` / `Gtk.DrawingArea` with Cairo; colours come from
  `config/theme.py` tokens, never literals.
- Icons: GTK symbolic names (`folder-symbolic`, `drive-harddisk-symbolic`, `changes-prevent-symbolic`).
- CSS: one `Gtk.CssProvider` at `STYLE_PROVIDER_PRIORITY_APPLICATION`; `tokens.css` is generated from
  `ThemeDefinition`, `data/css/app.css` references tokens only.
- `Gtk.Application` with `application-id com.mensuramedia.lindrivespace`; `--smoke` / `--screenshot`
  runs use `Gio.ApplicationFlags.NON_UNIQUE`.

## Tests
- `tests/core`: pure Python, `tmp_path` fixtures, no display.
- `tests/ui`, `tests/models`: need a display (`DISPLAY=:0` or broadway); `conftest.py` skips them
  when `Gtk.init_check()` fails. Never call `Application.run()` in tests.
- Widgets are verified in a `Gtk.OffscreenWindow` via `get_pixbuf()`.

## Files & ownership
- Shared files (`ui/pages/__init__.py`, `app.py`, `ui/window.py`, `pyproject.toml`, `tests/conftest.py`,
  `core/__init__.py`, `config/theme.py`, `changelog.md`) are edited only by the orchestrator.
- `core/{events,options,fsnode}.py` are frozen contracts; signature changes must be escalated.
- Agents record their work in `.claude/memory/changes/<date>-wpN.md`, never in `changelog.md`.
- Agents never run `git add` / `git commit`.
