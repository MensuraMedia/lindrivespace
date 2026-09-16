# LinDriveSpace — Handoff (updated 2026-09-16, v0.2.0)

This document is the single place to start from when picking the project up. It says what exists,
how it is built and verified, what was decided and why, and what is still open.

## 1. What the project is

LinDriveSpace is a native GTK 3.24 / Python 3.12 desktop application for Linux Mint (Debian family)
that shows every mount and partition, then lets the user drill from folders down to files with
apparent and allocated sizes, counts, a Share % bar and last-modified dates — TreeSize / WizTree
for Linux. It was built on an optimized fork of `mikesdatawork/gtk-python-dashboard-starter`, follows
the `MensuraMedia/universal-instruction-set` (v2026.04) process, and uses the Ubuntu type family
with Ubuntu orange on the "gray-temperature" palette.

- Repo: https://github.com/MensuraMedia/lindrivespace (branch `main`, 60 commits, all pushed; tag `v0.2.0`)
- Local checkout: `/home/user/projects/lindrivespace`
- Concept & technical design: `docs/CONCEPT-AND-TECHNICAL-DESIGN.md` (§16 lists the errata adopted at build)
- Screen mockups: `docs/mockups/lindrivespace-mockups.html` (published https://claude.ai/artifact/NJkL7nHfQys3V6LeYoNGnv),
  scan-strip variants `docs/mockups/scan-strip-mockups.html` (https://claude.ai/artifact/Bgqf9jYMRiiUBK1Wn6fESY)
- README: `README.md` (features with real screenshots, compatibility table, install: `.deb`, installer script, checkout)
- Licence: `LICENSE.md` — PolyForm Noncommercial 1.0.0 with a plain-words preamble; commercial use needs written consent
- Backlog with evidence: `docs/BACKLOG.md` (A–D original findings, E performance root causes + before/after, F Share % review, G Flathub compliance)
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
| Explorer | done | Tree-table with reorderable/resizable/sortable/hideable columns (header menu, toolbar Columns), live file rows on expand (2,000 cap + summary row; hard links attributed 1/N, "hard link ×N" in Type), **Share %** = share of the whole scan (bar + text, one denominator per screen), **Of parent %** text column hidden by default, breadcrumb, status bar, context menu, Favorites star (toolbar, Ctrl+D, menu), double-click file → file manager. |
| Analysis panel | done | Collapsible (toolbar toggle, F9, collapse button; auto-hide < 1100 px): Treemap (zoom), Top files, Types, Age. |
| Favorites | done | Store in settings; page lists folders/files; click scans that item; file favourites reveal in their folder. |
| History | done | `core/history.py` HistoryStore (usage + scan samples, `~/.cache/lindrivespace/history.json`), TrendChart with Day/Week/Month/Year/All, First/Latest/Change/Growth tiles, Pattern History bookmarks. Clicking **Change** reveals "Where space changed": folder + file diff (`core/changes.py`) between the newest auto-saved scan snapshot and the oldest inside the period (`~/.cache/lindrivespace/scans/`, 12 kept per root, saved in a forked child by `app.autosave_snapshot`; the diff also runs in a forked child; `list_snapshots` reads only the gzip header). Background collector `lindrivespace --collect` + systemd user timer from Settings › Background collection (`services/scheduler.py`). |
| Hardware | done | Disks and live I/O tables first (styled like the Overview list, sortable), then system, DMI board/firmware, CPU/memory, lspci controllers, drive types, filesystems, notes; every card has a Copy icon; Refresh / Copy report. |
| Glossary | done | 120 terms in 7 categories, search, category chips, expandable rows with See-also links. |
| Settings | done | Theme (light = preview), units, primary size, scan defaults, exclusions, background collection (scheduler), hidden fstypes, primary/secondary mountpoints, explorer bold-N / reset columns, auto-scan on startup, Diagnostics (log folder + level, open log), About. |
| Logging & errors | done | `lindrivespace/logsetup.py`: rotating log `~/.cache/lindrivespace/logs/lindrivespace.log` (1 MB × 5), main/thread/GTK-callback exception hooks, GLib warning capture, `--debug`; in-window error bar with Details and Open log. |
| Privileged scan helper | built, not wired | `services/privilege.py`, `data/bin/lindrivespace-scan-helper`, polkit policy exist and are tested; the context-menu item still prints a TODO. |
| Packaging | done (v0.2.0) | `bin/lindrivespace` launcher (checkout or installed), `scripts/install.sh` / `uninstall.sh` (user `~/.local` or `--system /usr/local`), `scripts/build-deb.sh` → `dist/lindrivespace_<ver>_all.deb` (dpkg-deb only; /usr/lib/lindrivespace + /usr/share/lindrivespace + polkit helper), desktop entry + AppStream metainfo (both validate), hicolor icon set 16–512 px + SVG. Licensed under PolyForm Noncommercial 1.0.0 (`LICENSE.md`, shipped as the package copyright file). Flathub: not yet compliant — see BACKLOG §G and the generative-AI disclosure note in §6. |

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
.venv/bin/python -m pytest -q tests/core tests/services            # headless: 258 passed
DISPLAY=:0 .venv/bin/python -m pytest -q tests/ui tests/models     # needs the X display: 127 passed (~8 s)
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
- CPU-heavy background work (snapshot save, History diff) runs in a forked child (`services/forkwork.py`), never a thread; retained trees are `gc.freeze()`d; files < 64 KB stay out of the largest-files ring (`scan.top_min_bytes`).
- Share % is the share of the scan root (adversarial review 2026-09-16); Of parent % is the optional column. `percent_of_parent` is unclamped; the bar renderer clamps only the fill.
- Header bar shows the app name only; sidebar mark is the original ring; card titles are 12 pt headings, KPI labels 9.5 pt small caps.
- Licence: PolyForm Noncommercial 1.0.0 (source-available, noncommercial); version 0.2.0 tagged.

## 6. Known issues and open items (also in `.claude/memory/pending.md`)

1. `sudo apt install jq` — the universal hooks (security gate, session context) need `jq`; until then they exit non-blocking.
2. "Scan as administrator" context-menu action is not yet wired to `services/privilege.py` (and cannot work inside a Flatpak sandbox).
3. Flathub (BACKLOG §G): SPDX id `PolyForm-Noncommercial-1.0.0` in the metainfo, app-id verification or rename to `io.github.MensuraMedia.lindrivespace`, manifest (GNOME runtime, psutil + pyudev modules, bundled Ubuntu fonts), `/run/host` root mapping, udev/lsblk fallbacks, scheduler via `flatpak run`, hide pkexec.
   **Flathub's generative-AI policy** requires disclosing AI-generated code, documentation and packaging with its extent; this project was built almost entirely with an AI assistant directed by the maintainer, so the disclosure must say so. The submission PR, its description and every review reply must be written by the maintainer, never generated; undisclosed or misrepresented AI material risks a ban.
4. Packaging follow-ups: optional `debian/` source package (dh-python) for a PPA; the .deb is built with plain `dpkg-deb` today; no GitHub release published yet (`gh release create v0.2.0 dist/*.deb` when wanted).
5. Light theme is a preview (tokens only, contrast-audited).
6. Bind mounts of the same device are listed but not scanned separately; btrfs/zfs allocated ≠ fs usage (documented in the glossary).
7. Page gutters: every `BasePage` paints its own 24 px gutter as CSS padding (`.page.page-padded`); never reintroduce widget margins on pages or GdkWindow background hacks (both produced black bands on resize).
8. "Where space changed" needs two kept snapshots of a mount; the analysis views (Top files / Types / Age) are estimates from each folder's largest-files ring, which excludes files under `scan.top_min_bytes` (64 KB, Settings › Scanning).
9. Explorer: BACKLOG B5 (first programmatic expand of an unpopulated row ends collapsed), F7 (summary row's Files column), F8 ("Focus here" to renormalise Share % to a sub-folder).
10. Performance items still open: BACKLOG A3/A4 (per-click saves, systemctl on Settings), B3 (tree-selection assertion), B4 (log rotation size), C1/C2 (retained-tree memory cap, parallel scanner), C4 (lsblk off the main thread), C5 (history pre-bucketing).
11. Agents: `.claude/agents/adversarial-reviewer.md` (Opus, read-only) — spawnable by name only in a session started after the file existed; otherwise run a general agent on Opus told to read and follow that file (that is how the Share % review was done).
12. The UI test fixture is isolated (own config/cache/log dirs) since 2026-09-16; earlier test runs had written column layouts into the real settings file — if a layout ever looks odd, reset `explorer.*`/`overview.*` in `~/.config/lindrivespace/settings.json`.

## 7. Process for continuing

- Work is organised in work packages (WP0–WP17 so far, plus dated manifests for smaller user requests). Each has a manifest in `.claude/memory/changes/`.
- For non-trivial packages run the `adversarial-reviewer` agent on the design before building and on the diff before committing (`.claude/routing-rules.md`).
- Shared files (`ui/window.py`, `ui/pages/__init__.py`, `app.py`, `config/*`, `data/css/app.css`) are edited by the orchestrator only; agents own their package's files.
- Every change is appended to `changelog.md` with a timestamp; decisions go to `decisions.md`.
- Commits are made per work package with the session attribution trailer; `main` is pushed after each.
- Before a release: run all suites, `./run.sh --smoke`, take fresh screenshots for the README (scripts in the session scratchpad; use `XDG_CONFIG_HOME` pointing at a scratch dir so nothing is persisted), bump `__version__`/pyproject/metainfo, `scripts/build-deb.sh`, `scripts/install.sh`, tag (`v0.2.0` is the latest).

## 8. Backups

A local tarball is written by `scripts/backup.sh` to `~/backups/lindrivespace-<timestamp>.tar.gz`
(excludes `.venv`, caches and git objects are included so the history travels with it).
Latest backup: `lindrivespace-20260916-062535.tar.gz` (9.1 MB, checkout at `4bea574` with the 0.2.0 .deb in `dist/`); earlier ones from 2026-09-15 remain (see the `.sha256` beside each). Restore: `tar -xzf ~/backups/lindrivespace-<stamp>.tar.gz -C ~/projects`.
