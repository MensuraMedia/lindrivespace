# Change: WP1 — application skeleton (M0)

**Date:** 2026-09-14
**Work package:** WP1 (main session)
**Type:** feature

## Summary
Runnable GTK3 application shell in the gray-temperature theme: `Gtk.Application`, HeaderBar,
150 px sidebar with logo and icon navigation, `Gtk.Stack` with four stub pages, token-driven CSS,
frozen core contracts, settings store, test harness.

## Files
- `pyproject.toml`, `requirements.txt`, `run.sh`
- `src/lindrivespace/{__init__,__main__,app}.py`
- `src/lindrivespace/config/{__init__,layout,theme,settings}.py`
- `src/lindrivespace/core/{__init__,fsnode,events,options}.py` (frozen contracts)
- `src/lindrivespace/ui/{__init__,window,sidebar,theme_loader}.py`
- `src/lindrivespace/ui/pages/{__init__,base,overview,explorer,snapshots,settings}.py`
- `src/lindrivespace/{models,services,ui/widgets}/__init__.py`
- `data/css/app.css`, `data/icons/hicolor/scalable/apps/com.mensuramedia.lindrivespace.svg`
- `tests/conftest.py`, `tests/core/{test_purity,test_fsnode,test_settings}.py`, `tests/ui/test_smoke.py`
- `docs/CONCEPT-AND-TECHNICAL-DESIGN.md` §16 errata

## Starter disposition
Kept (adapted): `Sidebar` (page registry, icons, no NavigationManager), `BasePage` (margin 24),
layout constants, CssProvider-at-screen pattern. Rewritten: `main.py` → `app.py`
(`Gtk.Application`, `--smoke`, `--screenshot`, NON_UNIQUE), `dashboard_window.py` +
`content_area.py` → `ui/window.py`, `config_themes.py` → `config/theme.py` (18 tokens,
dark + light). Dropped: `manager_navigation.py`, demo pages, theme selector, `style.css`.

## Defects found and fixed while verifying
- `present()` without `show_all()` left the window empty (screenshot was a blank canvas).
- `Gtk.Widget.draw()` on a CSD toplevel paints only the frame → screenshot now uses
  `Gdk.pixbuf_get_from_window`.
- `vexpand` on the logo image propagated to the sidebar and doubled the logo area height.
- `FsNode.top_limit` was not inherited from the parent (ring size ignored for children).
- Second `Gtk.Application.register()` in the same process raises "already exported" → module-scoped fixture.

## Verification
`ruff check`, `ruff format --check`, `mypy --strict core`, `pytest tests/core` (11 passed),
`DISPLAY=:0 pytest tests/ui` (4 passed), `./run.sh --screenshot` inspected.
