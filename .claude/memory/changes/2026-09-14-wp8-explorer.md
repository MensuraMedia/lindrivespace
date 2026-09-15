# Change: WP8 — Explorer page (tree-table, toolbar, breadcrumb, context menu)

**Date:** 2026-09-14
**Work package:** WP8 (gtk-ui agent)
**Type:** feature

## Summary
Replaced the Explorer stub with the full "TreeSize-style" page: a scan toolbar, a
clickable breadcrumb with live totals, the reorderable/resizable/hideable
`Gtk.TreeView` tree-table over `ScanTreeModel`, a right-click context menu, and a
status bar. The page owns the whole scan lifecycle (builds the model/controller,
starts/cancels/pauses scans, drives the header progress pill) and exposes the
public API the later work packages (WP9 insight panel, WP10 snapshots, WP11
privilege escalation) need.

## Files
- `src/lindrivespace/ui/pages/explorer.py` — replaced the M0 stub with `ExplorerPage`.
- `src/lindrivespace/ui/widgets/explorer_tree.py` — new: `ExplorerTree(Gtk.ScrolledWindow)`.
- `src/lindrivespace/ui/widgets/scan_toolbar.py` — new: `ScanToolbar(Gtk.Box)`.
- `src/lindrivespace/ui/widgets/breadcrumb.py` — new: `Breadcrumb(Gtk.Box)`.
- `src/lindrivespace/ui/widgets/tree_context_menu.py` — new: `TreeContextMenu(Gtk.Menu)`.
- `tests/ui/test_explorer.py` — new, 7 tests.
- `.claude/memory/changes/2026-09-14-wp8-explorer.md` — this file.

Did not touch `ui/window.py`, `ui/pages/__init__.py`, `app.py`, `config/*`,
`data/css/app.css`, `core/*`, `models/tree_model.py`, `services/scan_controller.py`,
or the WP5 widgets — only imported/used their existing public API.

## Public API for WP9/WP10/WP11

```python
page = window.pages["explorer"]

page.model        # ScanTreeModel — .root, .primary(node), .fmt_bytes, .percent(node)
page.controller    # ScanController — .start/.cancel/.pause/.resume, .running, .entries, .elapsed
page.start_scan(path: str) -> None   # public; window.request_scan() calls this
page.tree          # ExplorerTree — .get_selected_node(), .select_node(node), .refresh()

page.add_side_panel(widget: Gtk.Widget) -> None     # puts widget in the Paned's 2nd slot,
                                                     # sizes it to Layout.dimensions.PANEL_WIDTH,
                                                     # persists settings["window.panel_visible"]
page.remove_side_panel() -> None
page.has_side_panel -> bool                          # property

# GObject signals on ExplorerPage:
#   "node-selected" (object node_or_None)  — re-emitted from the tree's selection
#   "action-requested" (str name, object node) — fired only for "scan-as-admin" and
#       "show-in-treemap" (the two actions this WP intentionally left as TODOs)
```

`ExplorerTree` (in case WP9/WP11 need lower-level tree access):
`get_column(id)`, `move_column_to(id, index)`, `set_column_visible(id, bool)`,
`save_state()` / `restore_state()`, `refresh()`, signals `"node-selected"` and
`"context-requested"(node, x, y, event)`.

## Design decisions
- **Column table is one tuple** (`COLUMN_DEFS` in `explorer_tree.py`): id, title,
  `cell_data_func` kind, xalign, default width, hideable. Order matches
  `config/settings.py DEFAULTS["explorer"]["columns"]` exactly, with `owner`/`type`
  appended (they're in `hidden_columns` by default, so they need a fixed fallback
  position once unhidden). `_DEFAULT_HIDDEN = {"owner", "type"}` in
  `explorer_tree.py` intentionally mirrors that default rather than importing it,
  to keep the widget importable independent of the settings schema; a drift check
  would be a good follow-up if `config/settings.py`'s defaults ever change.
- **Name column** packs three renderers (icon, muted right-aligned `name_size` at a
  fixed 72 px, then the expanding name text) exactly per the brief. Bug fixed
  during verification: `treeview.set_expander_column()` must be called **after**
  `append_column()` — calling it inside the column-builder (before the column is
  attached) raised `Gtk-CRITICAL: gtk_tree_view_set_expander_column: assertion
  'column == NULL || gtk_tree_view_column_get_tree_view (column) == ...'
  failed` and made `--smoke` noisy. Now done in the `_build_columns()` loop right
  after `append_column`.
- **Sort**: header `"clicked"` (only connected for `SORT_COLUMNS` ids) toggles
  descending on a repeat click of the same column, defaults to descending for
  numeric/date columns and ascending for `name` on first click — matches the
  brief's literal wording. `GtkTreeStore` sorting is never enabled; every sort
  goes through `model.set_sort()`.
- **Persistence**: order is saved from `columns-changed`, debounced one tick with
  `GLib.idle_add`; widths from `notify::width` on each column, only overwriting
  the previous known width (skips the identical width write our own
  `set_fixed_width` calls produce during `restore_state()`/`reset_columns()`, via
  a `_loading` guard so those don't self-persist); visibility and sort persist
  immediately on user action. `ExplorerTree.__init__` calls `restore_state()` at
  the end; `ExplorerPage.on_hidden()` calls `tree.save_state()` so a full layout
  snapshot lands in settings whenever the user navigates away.
- **Header progress pill**: built lazily (`_ensure_pill`), a `Gtk.Box` with class
  `"pill"` (existing CSS), a flat button whose `process-stop-symbolic` icon is
  recoloured red via a tiny scoped `Gtk.CssProvider` built from `theme.danger`
  (never a literal hex — matches the "colours only from theme.py" rule), a mono
  label, and a `Gtk.ProgressBar` in pulse mode (`set_show_text(False)`,
  `set_size_request(120, -1)`). `window.set_header_widget(pill)` on start,
  `(None)` on finish; `on_shown()` re-installs it if a scan is still running after
  the user navigates back to Explorer, since `on_hidden()` deliberately leaves the
  scan running.
- **Context menu actions** live in `ExplorerPage._on_menu_action`, not in
  `TreeContextMenu` (which only emits `"action"`). "Open terminal here" avoids
  `os.chdir()` (which would race with the rest of the app on the process's
  cwd) — it instead passes `--working-directory=<GLib.shell_quote(path)>` on the
  `x-terminal-emulator` commandline given to
  `Gio.AppInfo.create_from_commandline`, wrapped in `try/except GLib.Error`, per
  the brief's "best effort, catch GLib.Error" instruction. "Scan as
  administrator" and "Show in treemap" print a `TODO (WP11/WP9): ...` line and
  also emit `ExplorerPage`'s own `"action-requested"` signal, exactly as
  specified.
- **Full-bleed layout**: `build_content()` zeroes `BasePage`'s 24 px margin and
  18 px spacing on `self` (the page's own `Gtk.Box`, not the shared
  `ui/pages/base.py`) so the toolbar/tree/status bar touch the window edges like
  both mockup directions, rather than floating in a padded card.
- **Toolbar** exposes Cancel/Pause as plain public buttons plus its own
  `"cancel-requested"`/`"pause-toggled"` signals (not specified verbatim in the
  brief, which only named the four settings-facing signals) — this keeps
  `ScanToolbar` decoupled from `ScanController` while still giving the page a
  single, symmetric signal-connect block.

## Known pre-existing issue (not introduced by this WP, not fixed — those files
are out of scope)
Running `tests/ui` together with more than one module that defines its own
module-scoped `window` fixture (e.g. `test_smoke.py` + `test_snapshots.py`,
verified with `test_explorer.py` uninvolved) intermittently raises
`gi.repository.GLib.GError: An object is already exported for the interface
org.gtk.Application at /com/mensuramedia/lindrivespace` — a D-Bus name
collision because each fixture calls `app.register(None)` with the same
`application-id` and nothing unregisters/quits the previous app object before
the interpreter exits. `tests/ui/test_explorer.py` reuses the same
module-scoped-`window`-fixture pattern the brief asked for
("module-scoped window fixture like test_smoke.py"), so it can trigger the
same pre-existing collision when run alongside the others; it does not add a
new failure mode. This is `tests/conftest.py`/other WPs' test-fixture territory
(not owned by WP8) and would need e.g. `app.quit()` + dropping the reference
before the module tears down, or one shared app fixture across `tests/ui`.

## Verification
```
.venv/bin/ruff format src tests && .venv/bin/ruff check src tests     # clean
DISPLAY=:0 .venv/bin/python -m pytest -q tests/ui tests/models        # 34 passed
                                                                        # (+ the pre-existing
                                                                        # cross-module D-Bus
                                                                        # errors above, unrelated)
DISPLAY=:0 .venv/bin/python -m pytest -q tests/ui/test_explorer.py    # 7 passed, isolated
DISPLAY=:0 ./run.sh --smoke                                            # silent, exit 0
```
Screenshots (scratchpad, reviewed with the Read tool):
- `explorer_start.png` — `./run.sh --screenshot ... /home/user/projects/lindrivespace`
  (finished before the 1.2 s capture — the project folder scans in ~0.1 s): tree
  sorted by allocated desc, right-aligned numeric columns, percent bars
  proportioned and centred, breadcrumb totals, status bar, no header pill (scan
  already done).
- `explorer_scanning.png` — `./run.sh --screenshot ... /usr` (still running at
  capture time): header pill with red stop icon + pulsing progress bar +
  "Scanning /usr · N entries · 1 s", toolbar's Cancel/Pause visible, root row
  showing live running totals. No clipped text, no misaligned bars.

## Open items for WP9/WP10/WP11
- WP9: `add_side_panel`/`remove_side_panel`/`has_side_panel` are implemented and
  tested manually (no dedicated automated test — WP9 owns the panel widget
  itself); `TreeContextMenu`'s "Show in treemap" sensitivity already reads
  `page.has_side_panel`.
- WP11: "Scan as administrator" is wired to emit `action-requested("scan-as-admin",
  node)` on `ExplorerPage`; nothing else calls into privilege escalation yet.
- Settings page (already built) should read/write `explorer.top_n_bold` if it
  wants a user-facing control — the Explorer only reads it at model-construction
  time (matches the settings snapshot at page build, not live-reloaded).
