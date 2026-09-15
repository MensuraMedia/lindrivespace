# LinDriveSpace — Issues and Resolutions Log

A record of every notable problem met while building LinDriveSpace (2026-09-14 → 2026-09-15),
what caused it, how it was resolved, and how to recognise it again. Ordered by area, not by
date; the append-only `changelog.md` has the timeline and `.claude/memory/changes/` the per-work-
package manifests. Read this before touching GTK rendering, threading or the scan pipeline.

Legend: **Symptom** what was seen · **Cause** verified root cause · **Fix** what changed ·
**Guard** the test, rule or measurement that keeps it fixed.

---

## 1. Rendering and layout (GTK 3.24, Mint-Y theme)

### 1.1 Black bands around page content on resize (History, Hardware, Settings)
- **Symptom:** the 24 px gutter around scrolled pages turned black while resizing, and stayed black
  until the next full redraw. The Overview page (not scrolled) was unaffected.
- **Cause:** pages set 24 px *widget margins*. A widget's margin belongs to its parent's allocation
  and the parent paints it. Inside `ScrolledWindow → Viewport` the viewport's bin window paints only
  the child's allocation, so the margin band shows the X window's unpainted background (black). A
  runtime CSS query proved the colours were resolved correctly on every node
  (`stack.content-area scrolledwindow.content-scroller viewport box.page`): it was never a CSS
  problem.
- **Fix:** `BasePage` carries the gutter as CSS **padding** on the page box (`.page.page-padded`,
  `data/css/app.css`). The page paints its own gutter. The Explorer stays full-bleed by removing the
  class. Every container between window and page is named in the CSS block so no node falls back
  to a theme colour.
- **Guard:** the resize measurement script (scratchpad `fq_*.png`) counts near-black samples inside
  the stack allocation on every page at 1000 and 1400 px: 0 / 58 092 and 0 / 124 085 on all seven
  pages. Decision recorded in `.claude/memory/decisions.md`.
- **Do not:** reintroduce `GdkWindow.set_background_rgba` — see 1.2.

### 1.2 "Peculiar background colour extended beyond the application window"
- **Symptom:** after an earlier attempt to fix 1.1 by painting every GdkWindow's background, a
  surface-coloured band appeared *outside* the window frame.
- **Cause:** with client-side decorations the toplevel GdkWindow includes the invisible shadow
  margin; painting its background fills that margin.
- **Fix:** the hack was removed; 1.1 is the real fix.

### 1.3 Pages forcing the window wider than the window manager allowed (black overflow)
- **Symptom:** switching to Explorer or Overview made the window request more width than the screen
  gave it; the overflow region painted black.
- **Cause:** `Gtk.Stack` is homogeneous by default, so the stack's minimum was the *widest* page,
  and wide tree views inflated that minimum.
- **Fix:** `stack.set_hhomogeneous(False)` / `set_vhomogeneous(False)`, window minimum 1000 px,
  Explorer tree minimum 380 px, Overview list column widths fit the default 1200 px window.
- **Guard:** resize measurement (1.1) at 1000 px.

### 1.4 Persisted window size skewed every render
- **Symptom:** screenshots and tests ran at 1541 px because the settings file remembered a wide
  window from an earlier session.
- **Fix:** window size reset to 1200 × 800 in settings; screenshots use an explicit `resize`.

### 1.5 Content area not the requested dark colour
- **Symptom:** the content area rendered `#343946` although the token said `#2d323d`.
- **Cause:** Mint-Y's `viewport` rule painted its own background over the stack's.
- **Fix:** the content-background block in `app.css` names `stack`, `scrolledwindow`, `viewport`,
  `viewport.frame` and `.page`, with `background-image: none; border: none`.

### 1.6 `show_all()` did nothing on no-show-all containers (empty strips)
- **Symptom:** the History "Where space changed" card, the Pattern History save row and the Hardware
  "collecting…" spinner rendered as an empty bordered strip.
- **Cause:** `gtk_widget_show_all()` returns immediately when the widget has `no-show-all` set;
  children are never shown.
- **Fix:** lift the flag around the call: `set_no_show_all(False); show_all(); set_no_show_all(True)`.
- **Guard:** tests assert `is_visible()` on a *leaf* (the table, the entry) rather than
  `get_visible()` on the container. Memory note `lindrivespace-gtk-show-all-no-show-all`.

### 1.7 Blue check glyphs on orange (column selector menus)
- **Symptom:** in the Explorer/Overview column menus the checked boxes were orange with a *blue*
  tick.
- **Cause:** Mint-Y paints its checked glyph as a blue bitmap via `-gtk-icon-source` on
  `menu menuitem check:checked`. Our override only covered `checkbutton check`, so menus kept the
  theme glyph on top of our background.
- **Fix:** `menu menuitem check|radio` rules at that specificity: grey sunken when off, accent fill
  with a white `object-select-symbolic` tick when on (radio: white dot), hot accent on hover.
- **Related:** switches, radio and check buttons were made orange the same way earlier (radial-
  gradient dot, symbolic tick) because the theme's bitmaps were blue.

### 1.8 Clipped table headers and values (Hardware)
- **Symptom:** "Read MB/" and "mq-deadlin…" truncated; device names ellipsized.
- **Fix:** column widths widened; Model / Device columns expand instead of the last column; the
  tables reuse the Overview list's classes (`mount-list`, `grid-table`, `mount-list-frame`).

### 1.9 Overview mount cards growing with scan progress
- **Symptom:** cards resized as progress text lengthened.
- **Fix:** fixed 300 × 132 px cards, single-line ellipsized labels; scan progress lives only in the
  strip at the top. (Cards were later removed entirely; the list is the only Overview view.)

### 1.10 `present()` before `show_all()`, `Widget.draw` blank on CSD, `vexpand` logo
- **Symptom:** blank or partial screenshots; logo stretching the sidebar.
- **Fix:** `show_all()` first; screenshots read pixels with `Gdk.pixbuf_get_from_window` (the CSD
  toplevel does not draw through `Widget.draw` into an image surface); logo `vexpand=False`.

### 1.11 `Gtk.Paned` collapsing the tree to zero width
- **Fix:** minimum width on the tree, `pack1/pack2(shrink=False)`.

---

## 2. Scanning pipeline and models

### 2.1 "could not convert type int to gint" once a scan passed 2 GB
- **Cause:** the progress signal declared its byte total as `gint` (32-bit).
- **Fix:** `GObject.TYPE_INT64`. Found through the new error bar and log (see 4.1).
- **Guard:** `tests/models` progress test with a > 2 GB synthetic total.

### 2.2 Slow tree store, slow appends
- **Symptom:** UI stutter while filling large trees.
- **Cause:** a 15-column store formatted every value at insert time; `append` on a `TreeStore`
  is O(n) per row.
- **Fix:** 3-column lazy store (node, name, dummy) with draw-time cell data functions; `prepend`
  inserts (O(1)); running totals on the node; model-owned sorting with an LIS-based `move_before`
  (GTK's `TreeStore.reorder` is not available from Python); rebuild past 200 out-of-place rows.
- **Guard:** `tests/models/test_tree_model.py` (10k-node stream, 8 ms drain budget).

### 2.3 Folders containing only files had no expander
- **Cause:** the dummy child was only added for directories with subdirectories.
- **Fix:** `_needs_expander` considers file counts; file rows (`FileRow`) are created on expand
  with a 2 000-row cap and a summary row.

### 2.4 Recursive `_bind_cell` and a `NameError` for `FsNode` under `TYPE_CHECKING`
- **Fix:** iterative binding; runtime import of `FsNode` where it is used in isinstance checks.

### 2.5 `FsNode.top_limit` not inherited
- **Fix:** children inherit the parent's limit unless given explicitly (frozen contract kept
  compatible).

### 2.6 Path scanning `TypeError` at startup, missing spinner
- **Symptom:** the first auto-scan raised on a path argument type; the user saw no feedback.
- **Fix:** `ScanRegistry` normalises paths; the Overview subtitle shows a spinner and "Scanning…";
  the strip at the top shows percent, bar, rate, countdown and Pause/Stop; the scan state persists
  across pages because the strip belongs to the window, not a page.

### 2.7 Auto-snapshot serialisation would freeze the UI
- **Risk noticed while adding change drill-down:** serialising a `/` scan to `.json.gz` takes
  seconds.
- **Fix:** `app.autosave_snapshot` runs on a daemon thread (the `FsNode` tree is immutable once a
  scan finishes); newest 12 snapshots per root are kept.

---

### 2.8 Star click on the Overview list raised `ValueError`
- **Symptom:** every click on the ★ cell showed the error bar; favourites could not be toggled.
- **Cause:** PyGObject 3.48 returns `(x_offset, width)` from `TreeViewColumn.cell_get_position`;
  the code unpacked the documented 3-tuple.
- **Fix:** accept both shapes. **Guard:** Overview list star test.

### 2.9 Error-report storm (2 648 identical tracebacks in two seconds)
- **Cause:** `report_error` raised inside its own `GLib.idle_add` callback; PyGObject routed that
  to `sys.excepthook`, which scheduled `report_error` again — an infinite loop that filled all five
  rotated log files.
- **Fix:** `report_error` can no longer raise (no-show-all-safe `show_all()`), and
  `logsetup._report` unregisters a reporter the first time it fails.

## 3. History, scheduler, collector

### 3.1 Trend chart x-axis labels overlapped at high point density
- **Cause:** floor-division error in the label stepping.
- **Fix:** greedy left-to-right label placement in `TrendChart._draw_x_labels`.

### 3.2 A test wrote into the real settings/cache
- **Cause:** the session-scoped window fixture does not isolate `Settings()`.
- **Fix:** manual verification scripts point `snapshot_dir` / `HistoryStore` at `tmp_path`;
  the stray keys were removed from `~/.config/lindrivespace/settings.json`.
- **Open:** a per-session XDG override for the UI fixture would make this impossible (see
  HANDOFF §6).

### 3.3 Racy UI test for the change panel
- **Symptom:** one intermittent failure of `test_clicking_change_with_one_snapshot_explains`.
- **Cause:** the test waited for the word "scan", which the interim text "Comparing scans…" also
  contains, so it sometimes asserted before the worker thread finished.
- **Fix:** wait until the interim text is gone. Three consecutive full runs green.

### 3.4 Headless collector must not import GTK
- **Fix:** `__main__.py` dispatches `--collect` before importing the GTK app; `collector.py` and
  `core/history.py` are stdlib-only (purity test covers `core/`).

---

## 4. Diagnostics and process

### 4.1 Errors were invisible
- **Fix:** `logsetup.py` — rotating log in `~/.cache/lindrivespace/logs`, `sys.excepthook` +
  `threading.excepthook`, GLib log handler, in-window error bar with Details / Open log, `--debug`.

### 4.2 Governance hooks need `jq`
- **Symptom:** the universal security and session hooks exit silently.
- **Status:** open — the user must run `sudo apt install jq`. Hooks are non-blocking meanwhile.

### 4.3 No node/bun on the machine
- **Effect:** the design-canvas tooling could not run; mockups were built as plain HTML artifacts.

### 4.4 UI tests colliding on one `Gtk.Application`
- **Cause:** each module built its own application → D-Bus "already exported".
- **Fix:** one session-scoped window fixture in `tests/ui/conftest.py`.

### 4.5 Killing the app from a shell whose command line contains "lindrivespace"
- **Symptom:** `pkill -f lindrivespace` killed the calling shell (exit 144) because the pattern
  matched its own command line.
- **Fix:** match with a bracketed pattern: `pkill -f "[-]m lindrivespace"`.

---

## 5. Checklist for similar symptoms

| If you see… | Look at |
|---|---|
| Black or wrong-coloured band at a page edge | §1.1, §1.3, §1.5 — never widget margins on pages, never GdkWindow backgrounds |
| A card, row or spinner that shows as an empty strip | §1.6 — `show_all()` on a no-show-all widget |
| Blue glyphs anywhere | §1.7 — theme bitmap via `-gtk-icon-source`; override at the theme's specificity |
| `gint` conversion errors | §2.1 — declare 64-bit signal parameters |
| UI stutter while a tree fills | §2.2 — draw-time formatting, prepend, model-owned order |
| Intermittent UI test failures | §3.3 — wait for the *final* state, not a substring of the interim one |
| Tests changing your real settings | §3.2 — point stores at `tmp_path` |
