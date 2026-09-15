# Change: WP6 — lazy tree model + scan controller

**Date:** 2026-09-14
**Work package:** WP6 (main session)
**Type:** feature

## Summary
`models/tree_model.py` turns the scanner's pre-order events into a lazy `Gtk.TreeStore`;
`services/scan_controller.py` drains the event queue on the GTK main loop in 8 ms slices and
exposes GObject signals for the Explorer page.

## Files
- `src/lindrivespace/models/tree_model.py`
- `src/lindrivespace/services/scan_controller.py`
- `tests/models/test_tree_model.py` (7 tests incl. a real end-to-end scan through `ScanThread`)

## Design decisions (measured, not guessed)
- **Three store columns only** (node object, name, dummy flag). Every displayed string, the
  percent value and the bold weight are computed at draw time by `cell_data_func(kind)`.
  Profiling showed a 15-column store spent 90 % of its time in PyGObject GValue conversion
  (4k events/s on a 10k-wide folder); with draw-time formatting it is 92k events/s and 570k
  events/s on nested trees.
- **Inserts use `prepend`**, which is O(1) in GtkTreeStore (`append` walks to the last sibling and
  computes an O(n) path for `row-inserted`). Order is restored by the model's sort anyway.
- **`Gtk.TreeStore.reorder` is not exposed by PyGObject.** Sorting moves only the rows outside a
  longest increasing subsequence with `move_before` (expansion state survives); a wide folder with
  more than 200 out-of-place rows and no expanded children is rebuilt in O(n) instead.
- **Live sorting is throttled** to once per 250 ms per folder during a scan; folders wider than
  500 rows are sorted once when the scan ends.
- **Running totals**: a child's `DirDone` delta is pushed up every not-yet-finalised ancestor, and
  `DirStarted` adds one directory to each open ancestor, so bars and counts are live before the
  parent finishes.
- The model keeps its own `FsNode` tree; `ScanThread.root_node` is redundant for the UI (WP10's
  snapshot save should use `model.root`).

## Controller
- `start(path, options)` spawns `core.scanner.ScanThread`; `consume(path, queue, producer)` drains any
  producer (tests, the WP11 pkexec helper).
- `GLib.timeout_add(16, drain)`; budget measured with `GLib.get_monotonic_time()`; `max_drain_us`
  is recorded for tests. Signals: `scan-started`, `progress`, `batch-applied`, `scan-finished(bool)`,
  `scan-error`.
- `FakeProducer` (paced replay thread) lives here for tests and demos; on cancel it emits
  `Finished(cancelled=True)` like `ScanThread`.

## Verification
`ruff`, `pytest tests/models` (7 passed), profile script in the session scratchpad
(`prof_model.py`): wide 10k = 92k ev/s, worst slice 43 ms; nested 100×100 = 570k ev/s, worst 4 ms.
