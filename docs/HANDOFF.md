# LinDriveSpace — Handoff (2026-09-15, updated 17:50)

This document is the single place to start from when picking the project up. It says what exists,
how it is built and verified, what was decided and why, and what is still open.

## 1. What the project is

LinDriveSpace is a native GTK 3.24 / Python 3.12 desktop application for Linux Mint (Debian family)
that shows every mount and partition, then lets the user drill from folders down to files with
apparent and allocated sizes, counts, a Share % bar and last-modified dates — TreeSize / WizTree
for Linux. It was built on an optimized fork of `mikesdatawork/gtk-python-dashboard-starter`, follows
the `MensuraMedia/universal-instruction-set` (v2026.04) process, and uses the Ubuntu type family
with Ubuntu orange on the "gray-temperature" palette.

- Repo: https://github.com/MensuraMedia/lindrivespace (branch `main`, 41 commits, all pushed)
- Local checkout: `/home/user/projects/lindrivespace`
- Concept & technical design: `docs/CONCEPT-AND-TECHNICAL-DESIGN.md` (§16 lists the errata adopted at build)
- Screen mockups: `docs/mockups/lindrivespace-mockups.html` (published https://claude.ai/artifact/NJkL7nHfQys3V6LeYoNGnv),
  scan-strip variants `docs/mockups/scan-strip-mockups.html` (https://claude.ai/artifact/Bgqf9jYMRiiUBK1Wn6fESY)
- README: `README.md` (features, screens, architecture, install, roadmap)
- Issues & resolutions: `docs/ISSUES-AND-RESOLUTIONS.md` (every problem met, root cause, fix, guard —
  read before touching GTK rendering, threading or the scan pipeline)
- Overview view mockups: `docs/mockups/overview-views-mockups.html` (https://claude.ai/artifact/4rPwMZfBBSPyupdxKK4UTF)
- Governance: `.claude/` (rules, hooks, commands, agents, memory), `changelog.md` (append-only),
  `.claude/memory/decisions.md`, `.claude/memory/changes/*.md` (one manifest per work package),
  `.claude/memory/pending.md`

## 2. Current state: what works

Sidebar: **Overview · Explorer · Favorites · History · Hardware · Glossary · Settings** (bottom).

| Area | Status | Notes |
|---|---|---|
| Startup auto-scan | done | 1.5 s after launch every physical mount is queued (primary, secondary, `/`, rest). `services/scan_registry.py` keeps one model per root; one scanner thread at a time. Switch off in Settings › Scanning. |
| Scan strip | done | Variant B stats panel at the top of the content area on every page: percent, bar (scanned ÷ mount used bytes), scanned/of/rate/elapsed, square queue chips (done = bold green), countdown, Pause/Stop. `ui/widgets/scan_banner.py`. |
| Overview | done | KPI tiles and a list view (`ui/widgets/mount_list.py`): disk section rows, one row per mount with inline Used % bar, PRIMARY/SECONDARY badge, star, Scan/Rescan; columns reorderable/hideable/resizable (persisted); udev hot-plug refresh, 30 s usage refresh. Cards view removed. |
| Explorer | done | Tree-table with reorderable/resizable/sortable/hideable columns (header menu, toolbar Columns), live file rows on expand (2,000 cap + summary row), Share % bars, breadcrumb, status bar, context menu, Favorites star (toolbar, Ctrl+D, menu), double-click file → file manager. |
| Analysis panel | done | Collapsible (toolbar toggle, F9, collapse button; auto-hide < 1100 px): Treemap (zoom), Top files, Types, Age. |
| Favorites | done | Store in settings; page lists folders/files; click scans that item; file favourites reveal in their folder. |
| History | done | `core/history.py` HistoryStore (usage + scan samples, `~/.cache/lindrivespace/history.json`), TrendChart with Day/Week/Month/Year/All, First/Latest/Change/Growth tiles, Pattern History bookmarks. Clicking **Change** reveals "Where space changed": folder + file diff (`core/changes.py`) between the newest auto-saved scan snapshot and the oldest inside the period (`~/.cache/lindrivespace/scans/`, 12 kept per root, saved on a worker thread by `app.autosave_snapshot`). Background collector `lindrivespace --collect` + systemd user timer from Settings › Background collection (`services/scheduler.py`). |
| Hardware | done | Disks and live I/O tables first (styled like the Overview list, sortable), then system, DMI board/firmware, CPU/memory, lspci controllers, drive types, filesystems, notes; every card has a Copy icon; Refresh / Copy report. |
| Glossary | done | 120 terms in 7 categories, search, category chips, expandable rows with See-also links. |
| Settings | done | Theme (light = preview), units, primary size, scan defaults, exclusions, hidden fstypes, primary/secondary mountpoints, explorer bold-N / reset columns, auto-scan on startup, About with log path. |
| Logging & errors | done | `lindrivespace/logsetup.py`: rotating log `~/.cache/lindrivespace/logs/lindrivespace.log` (1 MB × 5), main/thread/GTK-callback exception hooks, GLib warning capture, `--debug`; in-window error bar with Details and Open log. |
| Privileged scan helper | built, not wired | `services/privilege.py`, `data/bin/lindrivespace-scan-helper`, polkit policy exist and are tested; the context-menu item still prints a TODO. |
| Packaging | not started | WP13: `debian/`, desktop entry, AppStream metainfo, LICENSE. `run.sh` from a checkout is the only launch path. |

## 3. How to run and verify

```
./run.sh                    # system python3 + system PyGObject; auto-scan starts after 1.5 s
./run.sh /some/folder       # open the Explorer on a folder
./run.sh --debug            # verbose log on stderr
./run.sh --smoke            # build the window and exit 0 (must be silent)
./run.sh --screenshot x.png # render the window (env LINDRIVESPACE_SCREENSHOT_DELAY_MS, LINDRIVESPACE_SCREENSHOT_AUTOSCAN=1)

# dev venv (ruff, mypy, pytest) — created once with: python3 -m venv --system-site-packages .venv && .venv/bin/pip install ruff mypy pytest
.venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests
.venv/bin/mypy --strict src/lindrivespace/core
.venv/bin/python -m pytest -q tests/core tests/services            # headless: 251 passed
DISPLAY=:0 .venv/bin/python -m pytest -q tests/ui tests/models     # needs the X display: 118 passed
```
GTK3 has no offscreen backend: UI tests need `DISPLAY=:0` (or `broadwayd`). `tests/ui/conftest.py`
holds one session-scoped application window; UI test modules must not build their own
`Gtk.Application` (D-Bus "already exported").

## 4. Architecture in one screen

```
src/lindrivespace/
  app.py            Gtk.Application, CLI, logging, scan registry, startup auto-scan queue
  logsetup.py       rotating log, exception hooks, GLib warning capture
  config/           layout.py (metrics) · theme.py (18 tokens, dark + light) · settings.py (JSON store)
  core/             PURE PYTHON (no GTK; tests/core/test_purity.py enforces it)
    fsnode.py       __slots__ node; events.py DirStarted/DirDone/Progress/Finished/ScanError (frozen contract)
    scanner.py      iterative scandir DFS, mount boundary, hard-link dedupe, cancel/pause, ScanThread
    scanner_cli.py  stdlib-only NDJSON scanner (pkexec helper); event_codec.py round trip
    mounts.py       psutil + mountinfo + lsblk merge, statvfs, DiskInfo grouping, udev MountMonitor fd
    treemap.py · classify.py · snapshot.py · units.py · hardware.py · glossary.py
  models/           tree_model.py (3-column lazy TreeStore, draw-time formatting via cell data funcs,
                    model-owned LIS move sort, running totals, file rows) · mounts_model.py
  services/         scan_controller.py (16 ms drain, 8 ms budget) · scan_registry.py (one model per root,
                    queue, expected bytes) · mounts_service.py · favorites.py · actions.py · export.py · privilege.py
  ui/               window.py (header, error bar, scan banner, sidebar, page stack) · sidebar.py · theme_loader.py
    pages/          __init__.py registry · overview · explorer · favorites · snapshots · hardware · glossary · settings
    widgets/        explorer_tree · scan_toolbar · breadcrumb · tree_context_menu · percent_bar_renderer ·
                    bar_gauge · ring_gauge (kept for colour rule) · mount_card · kpi_tile · insight_panel ·
                    treemap_view · top_files_view · file_types_view · age_view · scan_banner · settings_rows
data/               css/app.css (rules over @define-color tokens) · icons · bin/lindrivespace-scan-helper · polkit
```
Key runtime rules: one scanner thread; events flow worker → `queue.SimpleQueue` → `GLib.timeout_add(16)`
drain with an 8 ms budget; the tree store never uses GTK sorting; inserts are `prepend` (O(1) in
GtkTreeStore); everything displayed is formatted at draw time.

## 5. Decisions that shape the code (full log in `.claude/memory/decisions.md`)

- Direction B (Overview) as first screen + Direction D panel inside the Explorer; Direction C dropped.
- Allocated size is primary (`st_blocks × 512`); decimal GB default; 150 px sidebar; light theme CSS deferred to v1.1; `.deb` only for v1.
- Errata adopted at build start: pre-order scan events, timeout drain, model-owned sort, pkexec helper process, gzip snapshots, no offscreen backend, venv tooling, no NavigationManager, NON_UNIQUE for smoke/screenshot.
- Scan strip: variant B chosen by the user; no "entries" wording; square chips; bold green when done.
- Startup auto-scan of all physical mounts, results retained per mount in the registry.
- Overview is a list (user's pick), no Cards or Map view; columns reorderable/hideable like the Explorer.
- Page gutters are CSS padding, never widget margins; no GdkWindow background hacks (docs/ISSUES-AND-RESOLUTIONS.md §1).
- Every finished scan is auto-saved as a snapshot (12 per root) so History can show *where* space changed.
- Menu check/radio items, switches, radios and checks are accent orange when on, grey when off (theme bitmaps overridden).
- An adversarial-reviewer agent (Opus, read-only) red-teams designs and diffs and collaborates with other agents.

## 6. Known issues and open items (also in `.claude/memory/pending.md`)

1. `sudo apt install jq` — the universal hooks (security gate, session context) need `jq`; until then they exit non-blocking.
2. No LICENSE file (README inherits the starter's "free for personal and educational use").
3. "Scan as administrator" context-menu action is not yet wired to `services/privilege.py`.
4. WP13 packaging (`debian/`, desktop entry, AppStream, README screenshots of the real app).
5. Light theme is a preview (tokens only, contrast-audited).
6. Bind mounts of the same device are listed but not scanned separately; btrfs/zfs allocated ≠ fs usage (documented in the glossary).
7. Page gutters: every `BasePage` paints its own 24 px gutter as CSS padding (`.page.page-padded`); never reintroduce widget margins on pages or GdkWindow background hacks (both produced black bands on resize).
8. "Where space changed" needs two kept snapshots of a mount; file rows come from each folder's 50 largest files, so smaller files are attributed to their folder only.
10. The UI test fixture does not isolate `Settings()`/XDG dirs; tests must point stores at `tmp_path` (ISSUES §3.2). A per-session XDG override in `tests/ui/conftest.py` would close this.
9. Agents: `.claude/agents/adversarial-reviewer.md` (Opus, read-only) red-teams designs and diffs and collaborates with implementer/code-reviewer agents via SendMessage; see `.claude/routing-rules.md`.

## 7. Process for continuing

- Work is organised in work packages (WP0–WP17 so far, plus dated manifests for smaller user requests). Each has a manifest in `.claude/memory/changes/`.
- For non-trivial packages run the `adversarial-reviewer` agent on the design before building and on the diff before committing (`.claude/routing-rules.md`).
- Shared files (`ui/window.py`, `ui/pages/__init__.py`, `app.py`, `config/*`, `data/css/app.css`) are edited by the orchestrator only; agents own their package's files.
- Every change is appended to `changelog.md` with a timestamp; decisions go to `decisions.md`.
- Commits are made per work package with the session attribution trailer; `main` is pushed after each.
- Before a release: run all suites, `./run.sh --smoke`, take fresh screenshots for the README, tag `v1.0.0`.

## 8. Backups

A local tarball is written by `scripts/backup.sh` to `~/backups/lindrivespace-<timestamp>.tar.gz`
(excludes `.venv`, caches and git objects are included so the history travels with it).
Backups taken: `lindrivespace-20260915-064256.tar.gz` and the one written at the end of this session
(see the `.sha256` beside each). Restore: `tar -xzf ~/backups/lindrivespace-<stamp>.tar.gz -C ~/projects`.
