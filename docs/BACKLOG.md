# LinDriveSpace — Backlog (investigated findings)

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
