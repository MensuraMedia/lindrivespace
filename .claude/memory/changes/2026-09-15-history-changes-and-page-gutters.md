# Change: History "Change" drill-down, page gutters, adversarial-reviewer agent

**Date:** 2026-09-15
**Type:** feature + bug fix + governance

## Where space changed (History → Change tile)
User request: "for the 'Change' make the card clickable so the user can see where the
change has occurred; ... a table of the folder or files and where the growth changes were."

- `core/changes.py` (new, pure): `diff_trees()` = `snapshot.diff_snapshots()` folder diff
  plus file-level diff of each matched directory's recorded largest files (`FsNode.top_files`);
  `pick_snapshots()` chooses the newest snapshot and the oldest one inside the selected
  period (falls back to the previous run); `change_report()` loads and diffs; helpers
  `snapshot_count()`, `format_saved_at()`.
- `app.py::autosave_snapshot()` saves a compact `.json.gz` snapshot of every finished scan
  under `~/.cache/lindrivespace/scans/` on a worker thread (tree is immutable once
  finished), keeping the newest 12 per root path. Hooked from `_on_scan_entry_changed`.
- `ui/pages/snapshots.py` (HistoryPage): the Change KPI tile is wrapped in a flat
  `Gtk.Button` (class `kpi-button`, accent border on hover/focus, detail "Click to see
  where" / "Click to hide"). Clicking reveals a "Where space changed" card: summary line
  (delta, the two scan stamps, count), sortable grid table (folder/file icon + relative
  path, Change kind, Before, After, Difference; sorted by |difference| desc; 300-row cap),
  Copy button, hint. Diffing runs on a thread with a generation counter; empty states for
  0 / 1 kept snapshots. Double-click on a row opens the root in the Explorer and reveals
  the path (falls back to its folder).
- Bug found while rendering: `show_all()` is a no-op on a `no-show-all` widget, so the card
  (and WP17's Pattern-History save row) showed as an empty strip. Fixed by lifting
  no-show-all around the `show_all()` call. Tests now assert `is_visible()` on the leaf.

## Page gutters rendering black on scrolled pages (root cause)
Pages set 24 px *widget margins*; a margin is painted by the parent, and the parent chain
(`ScrolledWindow` → `Viewport` bin window) does not paint the child's margin band, so it
showed the X window's unpainted (black) background on resize. Fix: `BasePage` puts the
gutter as CSS **padding** on the page box itself (class `page-padded`, `data/css/app.css`),
so the page paints it; Explorer keeps full-bleed. The earlier GdkWindow
`set_background_rgba` hack (which also painted the CSD shadow margin) is gone.
Measured: 0 near-black samples inside the stack on every page at 1000 and 1400 px.

## Governance
- `.claude/agents/adversarial-reviewer.md` (Opus, read-only): red-teams designs/methods/
  diffs, ranks risks with evidence, proposes fixes, collaborates with implementer/reviewer
  agents through SendMessage. Registered in `.claude/routing-rules.md` and `/team`.

## Files
src/lindrivespace/core/changes.py, src/lindrivespace/app.py, src/lindrivespace/ui/pages/snapshots.py,
src/lindrivespace/ui/pages/base.py, src/lindrivespace/ui/pages/explorer.py, src/lindrivespace/ui/window.py,
data/css/app.css, tests/core/test_changes.py, tests/ui/test_history_page.py,
.claude/agents/adversarial-reviewer.md, .claude/routing-rules.md, .claude/commands/team.md,
changelog.md, docs/HANDOFF.md, README.md, .claude/memory/decisions.md
