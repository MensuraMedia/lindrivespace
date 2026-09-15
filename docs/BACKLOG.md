# LinDriveSpace — Backlog (investigated findings)

> **2026-09-15 walkthrough update:** section E below supersedes the guesses in A5/A6/C1/C3 with measured root causes.

Findings from the 2026-09-15 investigation the user asked for ("slight delay when clicking
each button", "performance problems, some errors"). Each item has the evidence, the likely
cause and a proposed fix. Nothing here is done unless marked **[fixed]**; the rest is for a later
session. Companion documents: `docs/ISSUES-AND-RESOLUTIONS.md` (resolved problems),
`.claude/memory/pending.md` (task list).

## A. Click delay

| # | Finding | Evidence | Proposed fix | Effort |
|---|---|---|---|---|
| A1 | **Every button animates its state change over 200 ms** (theme). Mint-Y sets `button { transition: all 200ms cubic-bezier(…) }` (gtk.css lines 133/248) and our `app.css` button rules inherit it, so the pressed/hover colour fades in and the click *looks* late even though the handler runs at once. Sidebar buttons and toggle chips are affected the same way. | `/usr/share/themes/Mint-Y-Dark-Aqua/gtk-3.0/gtk.css` lines 133, 248, 264–267; `app.css` has no `transition` on `button`. | Add `button, .sidebar button, checkbutton, radiobutton { transition: none; }` (or 50 ms) to `app.css`. One line; verify the Explorer toolbar toggles still show their active colour. | XS |
| A2 | **Glossary page takes ~190 ms to show** (120 expandable rows built on each show). Other pages: 2–8 ms; Hardware ~43 ms (collection kicks off on a thread). | Probe script: `show_page glossary 240 ms` including a 50 ms pump vs 51–58 ms for the others. | Build the glossary rows once (cache) or lazily per category; keep only the filter/search work in `on_shown`. | S |
| A3 | **Settings and History persist on every click**: each period chip / switch calls `settings.save()` (JSON write, fsync-free) — ~2 ms, not the cause, but it is on the click path. | `_persist()` in History and Settings; timed 2 ms. | Debounce saves with a 500 ms `GLib.timeout` (single writer in `Settings`). | XS |
| A4 | **Scheduler status runs three `systemctl` subprocesses** when the Settings page is shown (~18 ms, more on a busy system). | `services/scheduler.status()` timed 18 ms. | Run `status()` on a thread and fill the label via `GLib.idle_add`; cache for 10 s. | S |
| A5 | **Main-loop latency is fine**: idle p95 2.4 ms; during a 580 k-entry `/home` scan p95 6 ms, p99 26 ms, worst 85 ms (one drain tick while the tree store re-sorted a wide folder). The 16 ms drain with its 8 ms budget is not the delay the user sees. | Probe script, 10 ms timeout jitter, n = 588 during the scan. | None now. If needed: lower `LIVE_RESORT_MAX_CHILDREN` or resort only after the scan. | — |
| A6 | **GIL contention during the auto-scan and the snapshot thread** can add a few ms per event (Python switch interval 5 ms). | `sys.setswitchinterval` is default; scanner and snapshot threads are pure Python loops. | `sys.setswitchinterval(0.001)` at startup; run the snapshot serialisation in a `multiprocessing` child (the tree is already JSON-serialisable) instead of a thread. | S |

## B. Errors seen in the log (`~/.cache/lindrivespace/logs/`)

| # | Finding | Evidence | Status |
|---|---|---|---|
| B1 | **Star click on the Overview list raised `ValueError`** ("not enough values to unpack (expected 3, got 2)") on every click: PyGObject 3.48 returns `(x_offset, width)` from `TreeViewColumn.cell_get_position`, not the documented 3-tuple. Favourites could not be starred from the list and the error bar appeared each time. | 5 tracebacks at 08:30, `mount_list.py:591`. | **[fixed]** handles both shapes. |
| B2 | **Error-report storm**: 2 648 identical tracebacks between 06:53:49 and 06:53:51 (5 MB, all five rotated files) — `report_error` raised inside its own `idle_add` callback, PyGObject sent that to `sys.excepthook`, which scheduled `report_error` again. Older code; not seen since 06:53. | Log rotation timestamps; `window.py` `report_error`. | **[fixed]** `report_error` can no longer raise (show_all path), and `logsetup._report` disables the reporter after its first failure. |
| B3 | **`gtk_tree_selection_get_selected: assertion 'priv->tree_view != NULL' failed`** ×21 — a `TreeSelection` used after its view was disposed (most likely the Explorer's selection handler firing during `set_model` while the registry swaps models, or the History change view being rebuilt). | GLib log capture, 21 occurrences. | Open. Reproduce with `--debug` while switching mounts during a scan; guard `selected_path()` with `self.tree.get_realized()` / disconnect before `set_model`. |
| B4 | **Log volume**: the old 5 MB storm means the rotating window (1 MB × 5) lost everything before 06:53. | File sizes. | Open. Raise `_MAX_BYTES` to 5 MB, or add a per-minute duplicate suppressor in the excepthook. |

## C. Performance

| # | Finding | Evidence | Proposed fix | Effort |
|---|---|---|---|---|
| C1 | **Memory grows with retained scans**: RSS 78 MB idle → 186 MB after `/home` (580 k entries). The registry retains one `FsNode` tree + `TreeStore` per mount; on this machine the auto-scan holds `/` (1.06 M), `/home` (0.58 M) and `/mnt/data` (5.1 M entries) at once — well beyond the 250 MB @ 1 M-dir budget. | Probe `ru_maxrss`; log: `/mnt/data` 5 146 047 entries in 118 s. | Keep only the *active* mount's `TreeStore` (rebuild from the `FsNode` tree on demand), cap retained trees (LRU, 2), or skip auto-scanning mounts above N entries unless asked. `FsNode` already uses `__slots__`. | M |
| C2 | **`/mnt/data` scan takes 118 s and `/home` 52 s cold / 18 s warm** — single scanner thread, sequential queue. Rate ≈ 43 k entries/s cold vs ≥ 150 k/s warm (budget). | Log timings 08:17–08:31. | Optional parallel scanner (per-top-level-dir workers feeding the same queue) — deferred in the design doc. Cold cache is I/O-bound; parallelism helps on NVMe. | M |
| C3 | **Snapshot serialisation after every scan** takes 4–11 s of CPU on a thread (GIL) and writes up to tens of MB (`/mnt/data`). | Log: "snapshot saved" 8–11 s after "scan done". | Serialise in a child process (see A6); skip snapshots for trees > 2 M entries or store only depth ≤ 6. | S |
| C4 | **Overview usage refresh runs `lsblk` every 30 s** on the main thread (~14 ms). | `core.mounts.list_mounts` timed 14.5 ms. | Move to a thread; or only `statvfs` on the timer and `lsblk` on udev events. | S |
| C5 | **History store re-reads and sorts all samples per period switch** (≤ 5 000 per path) — fine today (~1 ms); becomes visible with hourly collection over months. | `HistoryStore.buckets/trend` timings. | Pre-bucket per period on load; incremental append. | S |

## D. Governance / tests

| # | Finding | Proposed fix |
|---|---|---|
| D1 | The session-scoped UI window fixture uses the real `~/.config` and `~/.cache`; tests that touch settings must restore them by hand (one test wrote `history.period` into the real file). | Set `XDG_CONFIG_HOME` / `XDG_CACHE_HOME` / `LINDRIVESPACE_LOG_DIR` to a tmp dir in `tests/ui/conftest.py` before the app is built. |
| D2 | `jq` still missing → universal hooks are inert. | `sudo apt install jq`. |

## E. Verified root causes — scripted walkthrough of every feature (2026-09-15)

Method: one window, real startup scan (/ 1.07 M entries, /home 0.58 M, /mnt/data 5.15 M),
every sidebar page, History chips + Change tile, Explorer toggles/expand, Settings switch,
clicked three times (early scan, big scan, idle). A 10 ms heartbeat measured main-loop stalls;
a watchdog recorded every thread's stack whenever the loop was > 150 ms late. Logs in
`~/.cache/lindrivespace/logs/` carry `WALK begin/end` and `STALL` lines for each click.

**What the clicks themselves cost:** every handler is < 10 ms and paints within ~20 ms except
Glossary first show (130 ms handler + 140 ms first paint, 120 wrapped rows laid out at once) and
"expand root" (73 ms). The delay the user feels is *not* in the handlers: it is the main loop being
unavailable, 105 stalls > 150 ms (max 1.8 s) during the walkthrough. Three causes, all measured:

| # | Cause | Evidence | Clean fix | Effort |
|---|---|---|---|---|
| E1 | **History "Change" work holds the GIL.** `list_snapshots()` gunzips and JSON-parses *every* kept snapshot (16 files, 59 MB compressed) just to read `meta`, and is called twice per click plus once per autosave trim; then the two chosen snapshots (up to 7 MB gz / 375 k dirs each) are loaded on a thread. gzip, the C JSON decoder and `_dict_to_node` hold the GIL for 300–1 800 ms at a time. | 184 STALL records with `history-changes @ gzip.read / json.raw_decode / snapshot.list_snapshots / _dict_to_node`; thread-vs-fork experiment: thread load p95 295 ms, forked child max 30 ms. | (a) `list_snapshots` reads only the first ~4 KB of each file (`meta` + root `"a"` are in the first 200 bytes) and `save_snapshot` writes `alloc` into `meta`; (b) run `change_report()` and `autosave_snapshot()` in a **forked child** (`os.fork`, copy-on-write, no pickling of the tree; result back over a pipe via `GLib.io_add_watch`), never on a thread. | S–M |
| E2 | **Cyclic GC full collections with millions of live tree objects.** Each retained scan keeps its `FsNode` tree (parent↔children cycles, `TopFile` tuples). With /, /home and /mnt/data retained there are 2.1 M tracked objects; a full collection takes **343 ms** and is triggered by allocation on whichever thread allocates — the drain (`tree_model._on_started`, 451–580 ms samples) or the scanner (main thread waits for the GIL). | Scan-only watchdog: main-thread stack at `_on_started` 580/451 ms; `gc.collect()` with the three trees loaded 341–349 ms; after `gc.freeze()` 0 ms. Scan speed itself is unaffected (4.9 s vs 5.0 s). | `gc.freeze()` when a scan finishes (retained trees leave the collector); raise `threshold0` to ~50 000 during scans; when a tree is dropped (rescan), break parent/child links and `gc.unfreeze()` before the one collection. | S |
| E3 | **Per-folder "largest files" ring dominates memory and scan time.** Every file enters a 50-entry heap per directory: /home retains 232 644 `TopFile` tuples = 57 MB of an 86 MB tree, and the heap maintenance makes the scan 15.6 s vs 6.3 s without it. RSS after the startup scan is 1.1 GB (1.5 GB once History loaded /mnt/data snapshots). | Per-process scans of /home: top 50 → 86 MB / 15.6 s; top 10 → 69 MB / 8.8 s; none → 29 MB / 6.3 s; **1 MB minimum** → 32 MB / 6.1 s with 4 570 entries retained. | Add `ScanOptions.top_min_bytes` (default 1 MB): files below it never enter the ring (the Explorer lists files live with `scandir`, so nothing visible is lost; the Top-files panel already ranks by size). Frozen-contract change → record in `decisions.md`. Expected: ~60 % less memory, 2× faster scans, smaller snapshots. | S |
| E4 | Glossary first show 270 ms; ~100 ms on later shows. 120 `ListBoxRow`s each with three wrapped labels and a `Revealer` body. | Profile: time is inside `stack.set_visible_child_name` (GTK size allocation), not Python. | Build the revealer body on first expand only; create rows for the visible category lazily. | S |
| E5 | Button press feedback fades over 200 ms (theme transition) — see A1. | Mint-Y gtk.css. | `button { transition: none }` in `app.css`. | XS |

Not causes (ruled out by measurement): scheduler `systemctl` calls (12 ms even under disk load),
settings saves (2 ms), the 16 ms drain budget (p95 6 ms during scans), `lsblk` refresh (14 ms).
