# Change: WP14 — Favorites (star folders/files, list them, jump to their space view)

**Date:** 2026-09-14
**Work package:** WP14 (gtk-ui agent)
**Type:** feature

## Summary

Implements the feature request verbatim: users can favorite folders or files
and find them again from a "Favorites" sidebar page; clicking one opens the
Explorer scanning just that target. Two pieces, both newly added:

- `services/favorites.py` — `FavoritesStore`, a GObject-free-of-GTK wrapper
  over `Settings["favorites"]` shared by any page/widget that needs it.
- `ui/pages/favorites.py` — replaces the M0 `FavoritesPage` stub with a real
  list of "card" rows, empty state, rename, reorder, open-in-file-manager,
  and remove.

## Files

- `src/lindrivespace/services/favorites.py` (new)
- `src/lindrivespace/ui/pages/favorites.py` (replaced stub)
- `tests/services/test_favorites.py` (new, 14 tests, headless)
- `tests/ui/test_favorites_page.py` (new, 5 tests, needs `DISPLAY`)
- `.claude/memory/changes/2026-09-14-wp14-favorites.md` (this file)

Did not touch `ui/window.py`, `ui/pages/__init__.py` (favorites was already
registered there), `ui/pages/explorer.py`, `ui/widgets/*`, `app.py`,
`config/*`, `core/*`, `models/*`, or any other service — only imported/used
`config/settings.py`'s existing `DEFAULTS["favorites"]` contract and
`ui/pages/base.py`'s `BasePage`.

## Public API for the orchestrator's Explorer star action

```python
# services/favorites.py
@dataclass(frozen=True)
class Favorite:
    path: str
    label: str
    added: str
    is_dir: bool          # computed at read time via os.path.isdir, never persisted

class FavoritesStore(GObject.GObject):
    __gsignals__ = {"changed": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def list(self) -> list[Favorite]: ...          # insertion order
    def is_favorite(self, path: str) -> bool: ...
    def get(self, path: str) -> Favorite | None: ...
    def add(self, path: str, label: str | None = None) -> Favorite: ...  # dup-safe
    def remove(self, path: str) -> None: ...
    def toggle(self, path: str) -> bool: ...        # returns the new state
    def rename(self, path: str, label: str) -> None: ...
    def move(self, path: str, new_index: int) -> None: ...
    def scan_target(self, fav: Favorite) -> str: ...  # fav.path if dir, else dirname(fav.path)

def get_store(app: object) -> FavoritesStore: ...   # caches one instance on app.favorites_store
```

Everything mutating persists (`settings.set("favorites", ...)` + `settings.save()`)
and emits `changed` exactly once, synchronously — the Favorites page and the
Explorer's star action share one `FavoritesStore` via `get_store(window.app)`, so
either side toggling a star updates the other without extra plumbing:

```python
from lindrivespace.services.favorites import get_store

store = get_store(window.app)
is_starred = store.is_favorite(node_path)
store.toggle(node_path)          # for a right-click "Add/Remove favorite" action
store.connect("changed", ...)    # e.g. to repaint a star glyph in the tree
```

For the Ctrl+D binding the orchestrator wires up in the Explorer: call
`store.toggle(selected_node.path())` on the currently-selected row; no
Favorites-page code needs to change for that to show up here.

## ui/pages/favorites.py behaviour

- Title "Favorites" + subtitle "Folders and files you starred. Click one to
  see its space view."; empty state is a dim label pointing at "Ctrl+D" /
  the Explorer's context menu (both to be wired by the orchestrator).
- Each favorite is a `Gtk.ListBoxRow` (`card` CSS class, `Layout.spacing.SM`
  margin-bottom so cards read as separate flat surfaces rather than one
  divided block — see "Design notes" below) with: a `starred-symbolic` icon,
  a bold label (double-click → inline `Gtk.Entry` via a `Gtk.Stack`, commits
  on Enter or focus-out, calls `store.rename`), a `mono`/`dim` path line,
  a right-aligned "last scanned <date>" (from `window.scan_history`, keyed by
  `store.scan_target(fav)`) or "not scanned", a size placeholder ("—" —
  this page never scans on its own), optional move-up/move-down chevron
  buttons (`store.move`), "Open in file manager", and "Remove" (no confirm
  dialog, per spec — undo isn't required).
- `row-activated` → `window.request_scan(store.scan_target(fav))`; for a file
  favorite, also sets `window.pending_reveal = fav.path` (a plain attribute —
  the orchestrator wires the Explorer to consume it for the "reveal this file"
  step after the scan lands).
- `refresh()` (public) rebuilds the row list from `store.list()`; called from
  `on_shown()` and from the store's `changed` signal, so switching to the page
  or a star toggled elsewhere both pick up changes immediately.
- "Open in file manager" imports `services.actions` defensively (bare
  `try/except ImportError` + `getattr(actions, "open_in_file_manager", None)`,
  per the brief — that module was being written concurrently by another
  agent) and falls back to `Gio.AppInfo.launch_default_for_uri` directly when
  it's missing or returns falsy.

## Design notes / defects found while building

- **`Gtk.Widget.show_all()` after `set_visible(False)` silently wins.** First
  draft of `refresh()` did `empty_label.set_visible(...)`,
  `list_box.set_visible(...)`, then `list_box.show_all()` last (to show newly
  built rows) — but `show_all()` recursively shows the widget itself too,
  stomping the `set_visible(False)` just set on an empty list. Fixed by
  calling `show_all()` *before* the two `set_visible()` calls. Caught by
  `test_empty_state_visible_with_no_favorites` failing
  (`list_box.get_visible()` was `True` with zero rows) — worth flagging for
  other WPs building similar "hide this container when its model is empty"
  logic that also calls `show_all()` on rebuild.
- **Drag-and-drop reordering skipped** in favor of small move-up/move-down
  buttons, per the brief's "optional... otherwise skip" — a `Gtk.ListBox`
  drag-reorder implementation (custom `Gtk.TargetList`, `drag-motion` row
  insertion math) was judged not "cheap" relative to two buttons that call
  the same `store.move()`.
- **`FavoritesStore` never imports `Gtk`/`Gdk`/`Gio`** (only `GObject`, via
  `gi.require_version("GLib", "2.0")`), matching the `MountsService`/
  `ScanController` shape — lets `tests/services/test_favorites.py` run fully
  headless (14 tests, no `DISPLAY` needed), same as `test_actions.py`'s
  non-clipboard tests.
- **`tests/ui/test_favorites_page.py` uses the shared session-scoped `window`
  fixture** (`tests/ui/conftest.py`) rather than the `_FakeWindow` pattern in
  `test_overview.py`/`test_snapshots.py` — those predate that fixture and
  work around one `Gtk.Application` id being registrable only once per
  process; `test_explorer.py` already established the shared-fixture pattern
  for pages added after that fixture existed, so this follows suit. Each
  test's `page` fixture clears the store first (`for fav in store.list():
  store.remove(...)`), since the store is shared app-wide state across every
  UI test module running in the same session.

## Verification

```
.venv/bin/ruff format src tests && .venv/bin/ruff check src tests   # clean
.venv/bin/python -m pytest -q tests/services/test_favorites.py       # 14 passed
DISPLAY=:0 .venv/bin/python -m pytest -q tests/ui/test_favorites_page.py tests/ui/test_smoke.py   # 10 passed
DISPLAY=:0 .venv/bin/python -m pytest -q tests/ui tests/models        # 69 passed, 1 pre-existing xfail (test_contrast, unrelated)
DISPLAY=:0 ./run.sh --smoke                                           # exit 0, silent
```

Rendered `ui/pages/favorites.py` standalone (two favorites: one folder
"Projects", one file "budget.ods") via a throwaway script building the app
the same way `tests/ui/conftest.py` does, `show_page("favorites")`, then
`Gdk.pixbuf_get_from_window` — screenshot at
`/tmp/claude-1000/-home-user-projects-lindrivespace/36b80e19-6d8f-4299-80d4-5be888b2143b/scratchpad/favorites.png`.
Fixed the empty-state/`show_all()` bug above from what the first render
showed, then added the `row.set_margin_bottom` gap between cards after the
first version rendered the two rows touching with only a hairline between
them (looked like one merged block, not two "flat cards").

## Open items for the orchestrator

- Explorer star action: call `get_store(window.app).toggle(node.path())` from
  a right-click menu item and from Ctrl+D; repaint on `store.changed`.
- `window.pending_reveal`: consume it after a scan started from this page
  finishes (e.g. in `ExplorerPage`'s scan-finished handler) to select/reveal
  the specific file in the tree, then clear it back to `None`.
