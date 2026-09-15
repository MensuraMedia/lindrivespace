# Change: WP10 — desktop actions, CSV/JSON export, Snapshots page

**Date:** 2026-09-14
**Work package:** WP10
**Type:** feature

## Summary

Three independent pieces from the concept doc §3.4: GTK-free CSV/JSON/top-files
export of a scanned tree, best-effort desktop actions (file manager, terminal,
clipboard, trash, reveal), and the real `SnapshotsPage` (replacing the M0
stub) that saves/lists/deletes snapshots and diffs two of them with a coloured
result table.

## Files

- `src/lindrivespace/services/export.py` (new)
- `src/lindrivespace/services/actions.py` (new)
- `src/lindrivespace/ui/pages/snapshots.py` (replaced stub)
- `tests/services/__init__.py` (new)
- `tests/services/test_export.py` (new)
- `tests/services/test_actions.py` (new)
- `tests/ui/test_snapshots.py` (new)

No `ui/widgets/snapshot_list.py` was added — a plain `Gtk.ListStore` +
`Gtk.TreeView` built directly in the page turned out simple enough (5 static
columns, no custom cell renderer) that a separate widget module would only
have added indirection.

## Public API

```python
# services/export.py
def flatten(root: FsNode, max_depth: int | None) -> Iterator[tuple[int, str, FsNode]]
def export_csv(root: FsNode, path: Path, *, max_depth: int | None = None,
                allocated_primary: bool = True) -> int
def export_json(root: FsNode, path: Path, *, max_depth: int | None = None) -> int
def export_top_files(root: FsNode, path: Path, limit: int = 500) -> int

# services/actions.py
def open_in_file_manager(path: str | Path) -> bool
def open_terminal(path: str | Path) -> bool
def copy_path(path: str | Path) -> None
def move_to_trash(path: str | Path) -> tuple[bool, str]
def confirm_trash(parent_window: Gtk.Window | None, path: str | Path, size_text: str) -> bool
def reveal_in_file_manager(path: str | Path) -> bool

# ui/pages/snapshots.py
class SnapshotsPage(BasePage):
    def save_current(self, root: FsNode, root_path: str) -> Path | None
    def reload(self) -> None
    def delete(self, confirm: bool = True) -> bool
```

## Design notes / defects found while building

- **CSV/JSON schema.** Both use `flatten()`'s own iterative (explicit-stack)
  pre-order walk — not `root.walk()` directly — because it also needs to carry
  a `/`-joined relative path and honour `max_depth` (skip descending past it)
  without extra bookkeeping. Row/node fields: `depth, path, name, size, alloc,
  files, dirs, percent_of_parent, mtime_max (ISO, local time), flags`. The
  root's own relative path is `"."`. `percent_of_parent`/`mtime_max` use the
  same `FsNode` methods the tree model itself uses, so the export always
  agrees with what's on screen.
- **JSON writer never calls `json.dump`/`json.dumps` on the nested tree**,
  same reasoning as `core/snapshot.py`'s `_node_tree_to_json` (see the WP4
  manifest): stdlib `json` recurses per nesting level regardless of how
  iteratively the Python structure was built, and blows the recursion limit
  well before a 5000-deep chain. `export_json` emits JSON text directly with
  an explicit stack (`_JFrame`), calling `json.dumps` only on individual
  scalar fields. Verified with a 5000-deep single-child chain (both
  `export_json` and `export_csv`) in `test_export_json_deep_chain_does_not_recurse`.
- **`export_top_files`** streams `(rel_path, size, alloc, mtime)` tuples from
  every node's `top_files` ring through `heapq.nlargest(limit, ..., key=alloc)`
  rather than sorting a fully materialised list — same "bounded ring, silently
  undercounts a directory with more files than its ring size" caveat as
  `core.classify.summarize_top_files` (WP4 manifest), since it can only see
  what's in each node's ring.
- **`gi.require_version("Gdk", "3.0")` is required before importing `Gdk`,
  even after `gi.require_version("Gtk", "3.0")`.** Discovered the hard way:
  `from gi.repository import Gdk, Gio, GLib, Gtk` (Gdk listed first)
  auto-resolved Gdk to whatever is newest on the system (4.0 here) because
  requiring "Gtk" 3.0 alone doesn't pin "Gdk"'s version — only actually
  *importing* `Gtk` first triggers GTK3's own Gdk-3.0 dependency lock, and
  even then only for imports that happen afterwards. `app.py` and
  `theme_loader.py` already had both `require_version` calls; `actions.py`
  and `snapshots.py` (and their tests) now do too. Left as a flag: any future
  `src/**` file that imports `Gdk` without both calls will intermittently work
  or crash depending on unrelated import order elsewhere in the process.
- **Two independent `Gtk.Application` instances with the same application-id
  cannot both `register()` in the same process** ("An object is already
  exported for the interface org.gtk.Application..."), `NON_UNIQUE` or not —
  confirmed independently of `tests/ui/test_overview.py`'s docstring (which
  already documents this exact issue). `tests/ui/test_smoke.py`'s own
  `window` fixture builds a full `LinDriveSpaceApp`, so
  `tests/ui/test_snapshots.py` cannot do the same without colliding when both
  run in one `pytest` invocation (the required verification command runs them
  together). Fixed the same way `test_overview.py` did: a tiny `_FakeWindow`/
  `_FakeApp` double (exposing only `.app.theme`, `.app.settings`,
  `.pages`) hosting the real `SnapshotsPage` inside a bare
  `Gtk.OffscreenWindow` — no `Gtk.Application` at all.
- **Contract concern for the orchestrator, not fixed here (out of my file
  ownership):** `tests/ui/test_explorer.py` still uses the full
  `LinDriveSpaceApp` + `register()` pattern (like `test_smoke.py`), so
  `DISPLAY=:0 pytest tests/ui tests/models` fails with the same
  already-exported-object error whenever both files run in one session
  (reproduced: removing `test_explorer.py` from the run makes the rest of
  `tests/ui`/`tests/models` pass cleanly — 29 passed). Worth converting
  `test_explorer.py`'s fixture to the same fake-window pattern, or adding a
  session-scoped shared `Application` fixture in `tests/conftest.py`.
- **Snapshot list / diff columns are `Gtk.TreeViewColumnSizing.FIXED` with
  explicit pixel widths** (no `expand=True`): an early version gave the
  "Root path"/"Path" columns `expand=True`, which grabbed all the TreeView's
  slack width and pushed "Allocated"/"File" (snapshot list) and the whole
  threshold+Compare control row off the visible page — invisible in a static
  screenshot because GTK3's default theme uses overlay (auto-hiding)
  scrollbars. Caught by literally looking at the rendered screenshot, not by
  any test. Also split the compare row into two rows (pickers row with
  `expand`ed combos; a separate controls row for the Δ spin button + Compare
  button) so the combos' width never competes with those fixed-size controls.
- **`meta.saved_at`** (a full ISO-8601 UTC string with microseconds, e.g.
  `2026-09-14T21:19:01.123456+00:00`, from `core/snapshot.py`) is reformatted
  for display only (`_format_saved_at`, local time, `YYYY-MM-DD HH:MM`) in
  both the snapshot list and the compare combos; the list's "Saved at" column
  still sorts correctly since the reformatted text stays lexicographically
  monotonic. The stored/compared data (`SnapshotMeta.saved_at`, used for
  `list_snapshots`'s newest-first ordering) is untouched.
- **Delete/Open dialogs are not exercised by any test** (`confirm_trash` and
  the page's own delete confirmation `Gtk.MessageDialog`, and the "Open
  snapshot…" `Gtk.FileChooserDialog`, all block on `.run()`); `delete()` takes
  a `confirm: bool = True` parameter specifically so `tests/ui/test_snapshots.py`
  can exercise the real delete logic (selection lookup, file removal, list
  reload) via `confirm=False` without ever opening a dialog.
- **"Open snapshot…"** copies the chosen `*.json.gz` file into
  `default_snapshot_dir()` (via `shutil.copy2`, skipped if it's already
  there) rather than opening it in place, since the page's only way to show a
  snapshot is through its own managed list — this keeps "the file always
  shows up in Saved Snapshots after Open" true regardless of where the user
  picked it from.
- `save_current(root, root_path)`'s `root_path` argument only ever feeds
  `snapshot_filename()` (for a readable slug in the saved filename) — the
  saved metadata's `root_path` field always comes from `core.snapshot.save_snapshot`
  itself (`root.path()`), which the caller cannot override. Not a bug, just
  worth knowing if `root_path` and `root.path()` ever disagree (e.g. a
  relative alias): the filename and the row's displayed "Root path" can differ.

## Verification

```
.venv/bin/ruff format src tests && .venv/bin/ruff check src tests        # clean
.venv/bin/python -m pytest -q tests/services/test_export.py tests/services/test_actions.py
                                                                          # 11 passed
DISPLAY=:0 .venv/bin/python -m pytest -q tests/ui/test_snapshots.py tests/ui/test_smoke.py
                                                                          # 7 passed
```

Screenshot (throwaway render script, two saved snapshots + a compare run):
`/tmp/claude-1000/-home-user-projects-lindrivespace/36b80e19-6d8f-4299-80d4-5be888b2143b/scratchpad/snapshots.png`
(script alongside it: `render_snapshots_page.py`). Confirms the coloured diff
rows (grew=accent, new=warn, deleted=fg_dim; shrank=aubergine not exercised by
the sample data but implemented the same way) and that everything fits the
page width without horizontal scrolling.
