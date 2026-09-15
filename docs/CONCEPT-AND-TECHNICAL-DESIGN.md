# LinDriveSpace — Concept & Technical Design

**Project:** https://github.com/MensuraMedia/lindrivespace
**Status:** Concept / pre-build (2026-09-14)
**Target platform:** Linux Mint 22.x (Ubuntu 24.04 base, Debian-family), GTK 3.24, Python 3.12
**Foundation:** optimized fork of `mikesdatawork/gtk-python-dashboard-starter`
**Governance:** `MensuraMedia/universal-instruction-set` (v2026.04)
**Visual system:** Ubuntu type + Ubuntu orange on the "gray-temperature" UI kit

---

## 1. Vision

LinDriveSpace is a native GTK3 desktop application that answers one question fast:
**"What is eating my disk, and where?"**

It shows every mounted filesystem, every partition behind it, and a drill-down tree of
folders and files with size, allocated size, file/folder counts, percent-of-parent bars,
and last-modified dates — the WizTree / TreeSize experience, rebuilt for Linux with
Linux-correct semantics (mount boundaries, hard links, sparse files, block allocation,
bind mounts, snap squashfs, permission-denied subtrees).

### Design pillars

| Pillar | What it means in practice |
|---|---|
| **Instant orientation** | On launch the user sees every mount with used/free at a glance before any scan. |
| **Truthful numbers** | Two sizes always: *apparent* (`st_size`) and *allocated* (`st_blocks × 512`). Hard links counted once. Cross-mount descent is opt-in. |
| **Responsive under load** | Scanning runs off the GTK main thread; the tree fills progressively; cancel is one click. |
| **One visual language** | Ubuntu / Ubuntu Mono type, Ubuntu orange accent, the gray-temperature kit's charcoal-slate surfaces. Numbers are tabular and right-aligned. |
| **Framework discipline** | The starter's sidebar + page-stack model is kept; everything else is tightened (single `Gtk.Application`, token-driven CSS, lazy tree, typed models). |

### Non-goals (v1)

- Not a file manager (no move/copy/rename); "Open in file manager" and "Move to trash" only.
- No root daemon. Elevated scans are an explicit, per-scan `pkexec` action.
- No remote/SSH filesystems in v1 (network mounts are listed but scanning is optional and warned).

---

## 2. Reference analysis

The reference screenshot (`example_drive_space.png`) is a Windows tree-table. The columns
map to Linux as follows:

| Reference column | LinDriveSpace column | Source |
|---|---|---|
| Name (tree, with folder glyph) | **Name** | `os.scandir` entry name; mount root shows `label  device  [fstype]` |
| Size | **Size** (apparent) | Σ `st_size` |
| Allocated | **Allocated** | Σ `st_blocks × 512` (this is what `du` reports and what actually fills the disk) |
| Files | **Files** | Recursive regular-file count |
| Folders | **Folders** | Recursive directory count |
| % of Parent (Size) | **% of Parent** with inline bar | `allocated / parent.allocated` (toggle to apparent) |
| Last Modified | **Modified** | `max(st_mtime)` of subtree (or own mtime, user toggle) |
| *(none)* | **Owner** (optional column) | `pwd.getpwuid(st_uid)` |
| *(none)* | **Type** (files only, optional) | extension / magic class |

Behaviours retained from the reference: expand/collapse arrows, largest-first sort,
bold rows for the top-N children of each parent, right-aligned numbers, and a percent bar
whose fill is the accent colour on a dark track.

---

## 3. Scope & feature set

### 3.1 Mounts & partitions (Overview page)

- Enumerate mounts from `psutil.disk_partitions(all=False)` merged with `/proc/self/mountinfo`
  and `lsblk -J -o NAME,KNAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINT,MODEL,ROTA,TRAN`
  for topology (disk → partition → mount, LVM, LUKS, mdraid, loop/snap).
- Per-mount card: label, device, fstype, mountpoint, used/free/total, usage ring, "Scan" button.
- Hotplug awareness through `pyudev` monitor (`block` subsystem) → cards appear/disappear live.
- Hidden by default: `squashfs` snap loops, `tmpfs`, `devtmpfs`, `proc`, `sysfs`, `cgroup*`,
  `overlay` (Docker). A filter chip reveals them.

### 3.2 Scan (Explorer page)

- Start a scan from any mount card or any arbitrary folder (file chooser / drag-drop / CLI arg).
- Tree-table columns per §2, sortable, reorderable, with column visibility menu.
- Progressive population: root row appears immediately; children fill as their subtree totals
  settle; bars re-normalise on each batch.
- Cancel, pause/resume, rescan subtree (right-click), "scan as admin" (pkexec) for
  permission-denied subtrees, which are marked with a lock glyph and excluded from totals
  until re-scanned.
- Options: follow symlinks (off), cross mount boundaries (off), count hard links once (on),
  show hidden files (on), apparent vs allocated as the primary size (allocated).

### 3.3 Insight views (right-hand side panel or tabs)

- **Top Files**: largest N files in current selection with path, size, modified, type.
- **File Types**: grouped by extension class (video, image, archive, package cache, log, other)
  with totals and counts.
- **Treemap**: squarified treemap of the selected subtree drawn with Cairo; hover → tooltip,
  click → select in tree, double-click → zoom.
- **Age**: histogram of allocated bytes by last-modified bucket (7d, 30d, 90d, 1y, older).

### 3.4 Actions

- Open in file manager (`Gio.AppInfo.launch_default_for_uri`), open terminal here,
  copy path, move to trash (`Gio.File.trash`) with confirmation, exclude from scan.
- Export: CSV / JSON of the current tree (flattened with depth), and a PNG of the treemap.
- Snapshots: save a scan to `~/.cache/lindrivespace/scans/<mount-uuid>-<ts>.json.zst` and
  diff two snapshots (grew / shrank / new / deleted).

### 3.5 Settings

- Theme: Gray-Temperature Dark (default), Gray-Temperature Light, System (follow
  `gtk-application-prefer-dark-theme`).
- Units: binary (GiB) vs decimal (GB, default, matches reference).
- Scan defaults (the §3.2 options), exclusion list, thread count.

---

## 4. Architecture

### 4.1 Layered layout

```
lindrivespace/
├── run.sh                         # venv-optional launcher (system PyGObject preferred)
├── pyproject.toml                 # packaging, ruff, pytest config
├── requirements.txt               # PyGObject, pycairo, psutil, pyudev (all apt-available)
├── data/
│   ├── com.mensuramedia.lindrivespace.desktop
│   ├── com.mensuramedia.lindrivespace.metainfo.xml
│   ├── icons/hicolor/scalable/apps/com.mensuramedia.lindrivespace.svg
│   └── css/
│       ├── tokens.css             # colour/spacing/type tokens (generated from theme)
│       └── app.css                # component rules referencing tokens
├── src/lindrivespace/
│   ├── __main__.py                # python -m lindrivespace
│   ├── app.py                     # Gtk.Application, single-instance, CLI args, CSS install
│   ├── config/
│   │   ├── layout.py              # dimensions (sidebar 150, row 24, bar 12 …)
│   │   ├── theme.py               # ThemeDefinition dataclass + Gray-Temperature variants
│   │   └── settings.py            # Gio.Settings-like JSON store in ~/.config/lindrivespace
│   ├── core/                      # NO GTK imports below this line
│   │   ├── fsnode.py              # __slots__ node: name, size, alloc, files, dirs, mtime, children
│   │   ├── scanner.py             # threaded iterative scandir walker, cancel/pause, batches
│   │   ├── mounts.py              # psutil + mountinfo + lsblk topology + pyudev monitor
│   │   ├── units.py               # GB/GiB formatting with tabular padding
│   │   ├── treemap.py             # squarified layout (pure geometry)
│   │   ├── snapshot.py            # save/load/diff scans
│   │   └── classify.py            # extension → type class
│   ├── models/
│   │   ├── tree_model.py          # Gtk.TreeStore adapter, lazy child population, sort
│   │   └── mounts_model.py        # Gio.ListStore of MountItem GObjects
│   ├── ui/
│   │   ├── window.py              # ApplicationWindow: HeaderBar + Sidebar + Stack
│   │   ├── sidebar.py             # kept from starter, tightened
│   │   ├── pages/
│   │   │   ├── base.py
│   │   │   ├── overview.py        # mount cards grid
│   │   │   ├── explorer.py        # tree-table + insight panel
│   │   │   ├── snapshots.py
│   │   │   └── settings.py
│   │   └── widgets/
│   │       ├── mount_card.py      # DrawingArea ring + labels
│   │       ├── percent_bar_renderer.py  # Gtk.CellRenderer subclass (Cairo)
│   │       ├── treemap_view.py    # DrawingArea + hit-testing
│   │       ├── scan_toolbar.py    # progress, cancel, options popover
│   │       └── kpi_tile.py
│   └── services/
│       ├── scan_controller.py     # bridges core.scanner ↔ models via GLib.idle_add
│       ├── actions.py             # open/trash/copy/export
│       └── privilege.py           # pkexec helper (separate scanner process, JSON over pipe)
└── tests/
    ├── core/                      # pure-python, fast, hermetic (tmp_path fixtures)
    └── ui/                        # smoke tests with GTK offscreen backend
```

**Rule:** `core/` imports nothing from `gi`. Every core module is unit-testable headless and
can be reused by a future CLI (`lindrivespace --scan /home --json`).

### 4.2 Runtime flow

```
Gtk.Application.do_activate
  └─ Window ── Sidebar(page-changed) ──► Gtk.Stack
                     │
   Overview page ◄── MountsService (psutil/lsblk; pyudev monitor on a GLib.io_add_watch)
       │ "Scan" click
       ▼
   ScanController.start(path, options)
       ├─ spawns core.Scanner in a threading.Thread (or a pkexec child process)
       ├─ Scanner emits ScanBatch(events) onto a queue every ~100 ms or 5 000 nodes
       └─ GLib.idle_add(drain_queue) → TreeModel.apply(batch) → view re-normalises bars
   Explorer page ◄── TreeModel (lazy: children are appended only when a row is expanded
                      or when the row is in the visible top-N)
```

### 4.3 Threading model

- GTK main thread owns every widget and the `Gtk.TreeStore`.
- Scanner runs in one worker thread per scan (I/O-bound; `os.scandir` releases the GIL
  during syscalls). Optional `ThreadPoolExecutor` fan-out across top-level directories
  for NVMe (configurable, default = min(4, cpu_count)).
- Communication is one-way (worker → main) through `queue.SimpleQueue`; the main loop
  drains with `GLib.idle_add(..., priority=GLib.PRIORITY_DEFAULT_IDLE)` in bounded slices
  (≤ 8 ms per idle callback) to keep 60 fps scrolling.
- Cancellation via `threading.Event`; pause via a second Event polled per directory.

---

## 5. Core algorithms

### 5.1 Walker

```python
# iterative DFS with an explicit stack; no recursion limits, no os.walk overhead
def scan(root: Path, opts: ScanOptions, emit: Callable[[ScanBatch], None]) -> FsNode:
    root_dev = os.lstat(root).st_dev
    seen_inodes: set[tuple[int, int]] = set()          # (st_dev, st_ino) for nlink > 1
    stack = [(root_node, os.scandir(root))]
    while stack:
        node, it = stack[-1]
        try:
            entry = next(it)
        except StopIteration:
            it.close(); stack.pop(); node.finalize(); emit(node); continue
        except PermissionError:
            node.denied = True; it.close(); stack.pop(); continue
        st = entry.stat(follow_symlinks=False)         # cached d_type when possible
        if entry.is_dir(follow_symlinks=False):
            if st.st_dev != root_dev and not opts.cross_mounts: continue
            child = FsNode(entry.name, parent=node, is_dir=True, mtime=st.st_mtime)
            node.children.append(child)
            try: stack.append((child, os.scandir(entry.path)))
            except PermissionError: child.denied = True
        else:
            if st.st_nlink > 1 and not opts.count_hardlinks_multiple:
                key = (st.st_dev, st.st_ino)
                if key in seen_inodes: continue
                seen_inodes.add(key)
            node.add_file(size=st.st_size, alloc=st.st_blocks * 512, mtime=st.st_mtime)
```

Rules:

- `st_blocks * 512` is the allocated size regardless of filesystem block size (POSIX).
- Symlinks are never followed by default (`follow_symlinks=False` everywhere).
- Mount boundaries: compare `st_dev` to root's; bind mounts of the same device are still
  descended (documented caveat; mountinfo check is an option for v1.1).
- Excluded paths (`/proc`, `/sys`, `/dev`, `/run`, `/snap/*/…`, user list) are pruned
  before `scandir`.
- Files are **not** kept as individual nodes by default beyond a per-directory "top 50 by
  size" ring plus aggregate counts; this caps memory. A "keep all files" option exists for
  small scans and the Top Files view reads from the rings.

### 5.2 Aggregation & finalize

`FsNode.finalize()` sums children into `size`, `alloc`, `files`, `dirs`, `mtime_max`,
then sorts children by `alloc` descending once. Percent-of-parent is computed lazily in
the model from `alloc / parent.alloc` so a toggle to apparent size costs nothing.

### 5.3 Memory budget

`FsNode` uses `__slots__` (`name, size, alloc, files, dirs, mtime, flags, parent, children`).
Target ≤ 160 bytes per directory node plus name. One million directories ≈ 200 MB; typical
home scans are far below. File rings are bounded (50 × 48 bytes per directory).

### 5.4 Squarified treemap

Standard Bruls-Huizing-van Wijk squarify over `children` sorted descending, returning
rects in a flat list with node refs; drawn in one Cairo pass; text only when
rect ≥ 48 × 18 px. Colour = accent hue for directories, desaturated slate for files, luminance
stepped by depth.

---

## 6. GTK implementation notes

| Concern | Decision |
|---|---|
| Application shell | `Gtk.Application` with `application-id` `com.mensuramedia.lindrivespace`, `HANDLES_OPEN` for CLI paths; replaces starter's bare `Gtk.Window` + `Gtk.main()`. |
| Window | `Gtk.ApplicationWindow` + `Gtk.HeaderBar` (title, scan progress pill, search). |
| Sidebar | Starter's `Sidebar` retained: 150 px, logo area, `page-changed` signal; icons added (symbolic SVGs, 16 px). |
| Pages | Starter's `BasePage` + `Gtk.Stack` retained; page registry becomes a list of `(id, label, icon, factory)` tuples in one place (`ui/pages/__init__.py`) instead of hand-wiring three files. |
| Tree-table | `Gtk.TreeView` on a `Gtk.TreeStore` with columns `[obj, name, size_str, alloc_str, files_str, dirs_str, pct_float, mtime_str, weight]`; fixed-height mode, `set_fixed_height_mode(True)` for 100k+ rows. |
| Percent bar | Custom `Gtk.CellRenderer` subclass drawing a rounded track + accent fill + right-aligned label (Cairo); `percent` and `is_selected` properties. |
| Lazy expansion | Rows get a dummy child until `row-expanded`; children are appended then (top-N pre-expanded). |
| Numbers | Pango attribute `font_features="tnum=1"` on numeric columns, right `xalign=1.0`, Ubuntu Mono for the raw bytes tooltip. |
| Styling | Single `Gtk.CssProvider` at `STYLE_PROVIDER_PRIORITY_APPLICATION`; `tokens.css` generated from the `ThemeDefinition` dataclass on theme change and re-loaded with `load_from_data`. |
| Icons | GTK symbolic names (`folder-symbolic`, `drive-harddisk-symbolic`, `media-removable-symbolic`, `changes-prevent-symbolic` for denied) so Mint-Y / Yaru theme them automatically. |
| Drag & drop | Accept `text/uri-list` on the Explorer page to scan a dropped folder. |
| Accessibility | All custom renderers/DrawingAreas expose `Atk` names; contrast ≥ 4.5:1 for text on all surfaces (verified in §7). |

---

## 7. Visual system — Ubuntu on Gray-Temperature

### 7.1 Type

| Role | Face | Size / weight |
|---|---|---|
| UI text, tree names | **Ubuntu** | 10.5 pt Regular; top-N rows Medium (500) |
| Numeric columns | **Ubuntu** with `tnum` | 10.5 pt Regular, right-aligned |
| Raw bytes, paths, tooltips, snapshot diff | **Ubuntu Mono** | 10 pt |
| Page titles | Ubuntu | 18 pt Medium |
| KPI figures | Ubuntu | 24 pt Light (300) |
| Card captions / column headers | Ubuntu | 9 pt Medium, letter-spacing 0.4 px, uppercase optional |

Fonts are present on Mint 22 (`fonts-ubuntu`, `fonts-ubuntu-mono`); `requirements` documents
the apt package for other distros with `Cantarell, sans-serif` fallback.

### 7.2 Palette (tokens, dark variant = default)

Sampled from `ui-kit-gray-temperature.jpg` and squared with Ubuntu brand values.

| Token | Hex | Use |
|---|---|---|
| `--bg-canvas` | `#495060` | window/canvas ground (slate) |
| `--bg-surface` | `#343946` | cards, sidebar, header |
| `--bg-surface-2` | `#2d323d` | tree body, inputs |
| `--bg-sunken` | `#21252f` | bar tracks, wells, ring tracks |
| `--bg-deep` | `#1b1e29` | selected-row ground, popovers |
| `--line` | `#1c1f28` | 1 px separators (starter's `#1a1a1a` equivalent) |
| `--line-soft` | `#3e414d` | hairlines inside cards |
| `--fg` | `#eeeeee` | primary text |
| `--fg-muted` | `#b9bcc6` | secondary text, column headers |
| `--fg-dim` | `#7d8290` | disabled, placeholders |
| `--accent` | `#e95420` | Ubuntu orange: bars, active nav, rings, focus |
| `--accent-hot` | `#fd5c01` | hover/pressed on accent, treemap peak |
| `--accent-soft` | `#e9542033` | bar glow, selected-row tint |
| `--aubergine` | `#772953` | secondary series (file-type chart), snapshot "shrank" |
| `--warm-grey` | `#aea79f` | Ubuntu warm grey: neutral series, file rects in treemap |
| `--ok` | `#3fb950` | free space, "healthy" |
| `--warn` | `#f5a623` | ≥ 85 % used |
| `--danger` | `#e0362c` | ≥ 95 % used, denied glyph |

Light variant swaps grounds to `#f3f3f1 / #ffffff / #e8e8e6` with `#333333` text and keeps
the same accent set. Neumorphic depth from the kit is expressed with **two** shadows on
cards only (`0 1px 0 #1b1e29 inset-top-highlight #4c505e`), never on rows or table cells.

### 7.3 Spacing & metrics

- Base unit 4 px; page margin 24 px (starter used 40, too generous for a data app).
- Tree row height 24 px; header 28 px; percent bar 12 × 96 px with 3 px radius.
- Mount card 260 × 120 px; ring 64 px, stroke 8 px.
- Sidebar 150 px (unchanged), nav button 32 px with 16 px icon + 8 px gap.

### 7.4 Component states

| Component | Normal | Hover | Selected / Active |
|---|---|---|---|
| Nav button | `--bg-surface`, `--fg-muted` | `--bg-surface-2` | `--accent` ground, `#fff` text, Medium |
| Tree row | `--bg-surface-2` | `--bg-surface` | `--bg-deep` + 2 px `--accent` left edge |
| Percent bar | track `--bg-sunken`, fill `--accent` | fill `--accent-hot` | unchanged, label `--fg` |
| Mount card | `--bg-surface`, ring `--accent` | lift shadow | 1 px `--accent` border |

---

## 8. Mount discovery details

```
psutil.disk_partitions(all=False)      → device, mountpoint, fstype, opts
/proc/self/mountinfo                   → mount id, parent id, bind sources, propagation
lsblk -J -b -o …                       → tree: disk → part → (crypt|lvm|raid) → mount; model, transport, rotational
os.statvfs(mountpoint)                 → total/used/free (frsize × blocks)
pyudev.Monitor.filter_by('block')      → add/remove/change → refresh model (debounced 300 ms)
```

Merge key is `(major:minor)`; fall back to `mountpoint`. Cards are grouped by physical disk
(NVMe, SATA, USB, loop) in the Overview page; a compact list mode exists for many mounts.

---

## 9. Privilege escalation

Denied subtrees are common (`/root`, other users' homes, `/var/lib/docker`). Strategy:

1. Scanner marks the node `denied` and continues.
2. User clicks "Scan as administrator" → `pkexec python3 -m lindrivespace.core.scanner --json <path>`
   runs the **core-only** module as root; results stream as newline-delimited JSON over stdout.
3. Main process merges the subtree into the existing tree. No GTK, no user config is touched as root.
4. A `data/polkit/com.mensuramedia.lindrivespace.policy` allows a friendly prompt string.

---

## 10. Packaging & distribution

- **Dev:** `./run.sh` (uses system `python3-gi`, `python3-psutil`, `python3-pyudev`; creates a
  venv with `--system-site-packages` only if the user asks).
- **Debian package:** `debian/` with `dh-python`/`pybuild`, depends on `python3-gi,
  gir1.2-gtk-3.0, python3-psutil, python3-pyudev, fonts-ubuntu, policykit-1`. Installs
  desktop file, icon, metainfo, polkit policy. Built with `dpkg-buildpackage -us -uc -b`.
- **Flatpak (later):** `org.gnome.Platform` 46 runtime; needs `--filesystem=host` and
  `--talk-name=org.freedesktop.Flatpak` for pkexec, so it is v1.1.

---

## 11. Testing & quality

| Layer | Tooling | What is covered |
|---|---|---|
| core | `pytest` with `tmp_path` fixtures building synthetic trees (sparse files, hard links, symlink loops, denied dirs via `chmod 000`) | sizes, counts, boundaries, cancellation, snapshot diff, treemap geometry |
| models | `pytest` + `gi` with `GDK_BACKEND=offscreen` | lazy population, sort stability, percent normalisation |
| ui | smoke: window builds, pages switch, CSS loads without warnings | regression guard |
| lint | `ruff` (E, F, I, B, UP), `mypy --strict` on `core/` | style, typing |
| perf | `tests/perf/bench_scan.py` on a generated 1 M-entry tree; budget printed in CI log | scan throughput, memory |

Performance targets on the dev machine (NVMe, 100 GB root):

| Metric | Target |
|---|---|
| Scan throughput | ≥ 150 k entries/s warm cache |
| Time-to-first-row | < 200 ms |
| UI frame budget during scan | idle callback ≤ 8 ms |
| Memory, 1 M directories | ≤ 250 MB RSS |

---

## 12. Universal-instruction-set compliance

At build start the repo receives the full v2026.04 layout — copied, never referenced:

- `CLAUDE.md` (project template), `changelog.md`, `.claudeignore`
- `.claude/rules/` → `memory-rules.md`, `token-hygiene.md`, `security.md`, plus project
  rules `python-gtk.md` (path-scoped to `src/**`) and `core-purity.md` (no `gi` in `core/`)
- `.claude/memory/` → `MEMORY.md`, `decisions.md`, `pending.md`, `sessions/`, `changes/`
- `.claude/hooks/` (session-start, pre-tool-use security, post-edit lint with `ruff` enabled)
- `.claude/commands/` (`plan-first`, `build-test`, `session-end`)
- `.claude/agents/` (scout, data-checker, implementer, code-reviewer, architect) with a
  project-specific `gtk-ui` agent; `.claude/skills/`, `.claude/roles/`, `.claude/board.md`
- `.claude/settings.json` (hooks) and `.claude/settings.local.json` (permissions)
- Git verified: `user.name`/`user.email`/credential helper are already configured on this
  machine; remote `origin` → `MensuraMedia/lindrivespace` (currently empty).

Routing for the build follows `routing-rules.md`: scaffolding and search → Haiku scouts;
core modules and widgets → Sonnet implementers in parallel; architecture, the tree model,
and the scan controller → Opus / main session.

---

## 13. Milestones

| # | Milestone | Deliverable | Est. |
|---|---|---|---|
| M0 | Governance & scaffold | `.claude/` standards, repo layout, `run.sh`, empty window with sidebar in Gray-Temperature theme | ½ day |
| M1 | Core scanner | `core/fsnode.py`, `core/scanner.py`, `core/units.py`, tests, bench | 1 day |
| M2 | Mounts | `core/mounts.py`, pyudev monitor, Overview page with cards | 1 day |
| M3 | Explorer | TreeStore adapter, percent-bar renderer, progressive fill, sort, context menu | 2 days |
| M4 | Insights | Top files, file types, treemap, age | 1½ days |
| M5 | Actions & export | open/trash/copy, CSV/JSON, snapshots + diff | 1 day |
| M6 | Privilege & polish | pkexec path, settings page, light theme, a11y pass | 1 day |
| M7 | Package | `debian/`, desktop/metainfo, README, screenshots, tag v1.0.0 | ½ day |

---

## 14. Risks & mitigations

| Risk | Mitigation |
|---|---|
| `Gtk.TreeStore` slow with 500 k+ rows | Lazy population + fixed-height mode; directories only by default; files behind "show files" toggle per node. |
| Bind mounts double-count | `mountinfo` parent/child check (v1.1); document in UI tooltip. |
| btrfs/zfs allocated ≠ real usage (compression, snapshots, reflinks) | Show fs-level used from `statvfs` on the card, subtree `st_blocks` in the tree; footnote on those fstypes. |
| pkexec unavailable (Flatpak, minimal installs) | Feature-detect; fall back to "run with sudo from terminal" instructions. |
| Ubuntu font missing on non-Ubuntu distros | CSS fallback stack; `fonts-ubuntu` in package depends. |
| Hotplug storms (USB hubs) | Debounce udev events 300 ms; refresh model diff-wise. |

---

## 15. Decisions needed before build (green-light checklist)

1. **Preferred mockup direction** (see `docs/mockups/`): A Classic Tree-Table, B Overview
   Dashboard + Explorer, C Gray-Temperature Cards, D Analyst Split with Treemap.
2. Default primary size: **allocated** (recommended, matches `du` and disk reality) or apparent.
3. Units default: decimal GB (matches reference) or binary GiB.
4. Sidebar width: keep starter's 150 px (recommended) or widen to 180 px for labels + icons.
5. Ship the light theme in v1 or defer to v1.1.
6. Package target for v1: `.deb` only (recommended) or `.deb` + Flatpak.
