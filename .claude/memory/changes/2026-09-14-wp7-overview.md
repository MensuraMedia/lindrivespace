# Change: WP7 — Overview page (mounts dashboard) + MountsService/MountsModel

**Date:** 2026-09-14
**Work package:** WP7 (gtk-ui agent)
**Type:** feature

## Summary
Replaced the M0 Overview stub with the Direction B "Mounted filesystems" dashboard: a KPI
strip (Total capacity / Used / Free / Scanned), a "Show hidden" checkbox + Refresh button, and
one section per physical disk with a wrapping `Gtk.FlowBox` of `MountCard`s. Backed by two new
headless-testable layers: `MountsService` (background `core.mounts` refresh, coalesced, hot-plug
aware) and `MountsModel` (pure-Python KPI/filtering helpers over one snapshot).

## Files
- `src/lindrivespace/services/mounts_service.py` — new. `MountsService(GObject.GObject)`:
  `mounts-changed`/`refreshing(bool)` signals, coalesced `refresh()` on a worker thread handed
  back via `GLib.idle_add`, `start()`/`stop()` wiring a `MountMonitor` (`GLib.io_add_watch`,
  300 ms debounce) and a 30 s periodic refresh (`GLib.timeout_add_seconds`).
- `src/lindrivespace/models/mounts_model.py` — new. `MountsModel`: `totals()`,
  `scanned_count()`, `most_urgent()`, `card_data()` (the four the brief named) plus
  `counted_mount_count()`, `counted_disk_count()`, `hidden_count()`, `is_visible()` and
  `is_visible_disk()` (see decisions below).
- `src/lindrivespace/ui/pages/overview.py` — replaced the stub body. `OverviewPage(BasePage)`,
  `title` unchanged.
- `tests/services/__init__.py` — new (note: a concurrent WP's `test_privilege.py` landed in the
  same directory during this session and left its own docstring in this file after mine; left
  as-is, harmless).
- `tests/services/test_mounts_service.py` — new, 4 tests (all headless: injected `lister`,
  `threading.Event` to force the coalescing race deterministically, `GLib.MainContext` pumping).
- `tests/ui/test_overview.py` — new, 4 tests.
- `.claude/memory/changes/2026-09-14-wp7-overview.md` — this file.

## Design decisions

- **`MountsService.lister` fetches every mount, always.** The default lister calls
  `core.mounts.list_mounts(hidden_fstypes=..., include_hidden=True)` regardless of the
  `mounts.show_hidden` setting, so `MountInfo.hidden` is always populated correctly. "Show
  hidden" is therefore a pure *display* filter in `MountsModel`/`OverviewPage`, not a re-fetch —
  `MountsModel.totals()`/`hidden_count()` need the always-accurate hidden flags (`totals()` must
  exclude hidden mounts *regardless* of the checkbox state, per the WP7 brief). `show_hidden`'s
  setter still calls `refresh()` (as specified) for parity with a future `hidden_fstypes` change,
  even though today's default lister doesn't need the round trip. Documented in the module
  docstring.
- **Bug found & fixed via the screenshot check: hidden-by-kind, not just hidden-by-fstype.**
  `mounts.hidden_fstypes` (settings default) does not include `hugetlbfs`/`mqueue` etc., so a
  `/dev/hugepages`, `/dev/mqueue`-style mount has `MountInfo.hidden == False` even though it has
  no backing block device (`DiskInfo.kind == "virtual"`). The first screenshot showed a stray
  "other / virtual" card group at the bottom with "Show hidden" unchecked, violating the brief's
  "must show 4 cards and no loops by default". Fixed by adding
  `MountsModel.is_visible_disk(disk, show_hidden=...)` (skips whole `loop`/`virtual` disk groups
  unless `show_hidden`) and calling it in `OverviewPage._rebuild_groups` alongside the per-mount
  `is_visible()` check. Regression-tested in `tests/ui/test_overview.py` with a synthetic
  `kind="virtual"`, `hidden=False` mount.
- **Layout bug found & fixed via the screenshot check: FlowBox dropped to 2 columns, not 3.**
  With the real `data/css/app.css` applied (`.card` padding/border), `MountCard`'s usage line
  (`Gtk.Label.set_line_wrap(True)`, unconstrained) reported a *natural* width of its full
  unwrapped text, pushing the card's natural width just over the threshold for 3 columns to fit
  the default window width, so `Gtk.FlowBox` (homogeneous, `max_children_per_line=4`) rendered
  only 2 wide, CSS-stretched columns instead of the mockup's 3-per-row layout — reproduced and
  measured directly (`card.get_preferred_width()` natural 323 vs the ~327 needed, plus GTK's
  actual column-fit computation being stricter than that back-of-envelope math suggested).
  `mount_card.py` is WP5-owned and not edited; instead `OverviewPage._build_card` calls
  `card.usage_label.set_max_width_chars(20)` — a documented public `MountCard` attribute (see
  `.claude/memory/changes/2026-09-14-wp5-widgets.md`) — which caps the label's *natural* width
  for wrapping purposes. Verified empirically (a scratch script measuring
  `flowchild.get_allocation()`) that this restores 3-per-row at the default 1200 px window width;
  confirmed again in the final `run.sh --screenshot`.
- **`MountsModel._counted_pairs()`** is the single source of truth behind `totals()`,
  `scanned_count()`, `counted_mount_count()`, `counted_disk_count()` and `most_urgent()`: it
  skips loop/virtual disk kinds and bind mounts so a physical disk's capacity is never
  double-counted and pseudo-filesystems never inflate "Total capacity" — matches the brief's
  totals() spec literally ("skip bind mounts and loop/virtual so a disk is not counted twice").
- **KPI value/unit split**: `format_bytes()` returns `"1.62 TB"`; `_split_value_unit()` in
  `overview.py` splits that into `(value, unit)` for `KpiTile.set_value(value, unit=..., ...)`
  rather than hand-formatting, so KPI text always matches `core.units.format_bytes` exactly
  (asserted directly in `tests/ui/test_overview.py`).
- **Used-tile detail is `"NN %"` only** (no "+X GB this week" trend, unlike the mockup's
  decorative text) — there is no historical-usage data source in this work package to compute a
  week-over-week delta from; flagging as a nice-to-have for whichever WP later adds a usage
  history log.
- **Disk header line**: `"<model> · <TRANSPORT> · <rotational|kind>"` (e.g. "Samsung SSD 870 EVO
  1TB · SATA · ssd"), per the brief's literal wording ("model · transport · rotational/ssd/nvme")
  rather than the mockup's cosmetic "just attached" hotplug text (no hotplug-recency state is
  tracked anywhere to support that).
- **Selection**: `MountCard` "selected" signal drives `OverviewPage._on_card_selected`, which
  calls `set_selected` on every card so only one is ever selected; the selected mountpoint is
  remembered across a group rebuild (`_rebuild_groups` re-applies it if the mountpoint is still
  present after a refresh/hidden-toggle).
- **Loading state**: a dim "Reading mounts…" label (also the initial subtitle text) is shown
  until the first `mounts-changed` fires, then hidden permanently (`_loaded` flag) — matches
  "before the first refresh completes" in the brief; it does not reappear on later refreshes.
- **`on_shown()`** re-triggers `service.refresh()` if never loaded or if
  `last_refresh_monotonic` is more than 30 s old.

## Test-infra decision: `tests/ui/test_overview.py` does NOT build a full `LinDriveSpaceApp` window

The brief said to build the window "like `tests/ui/test_smoke.py`'s fixture". Reproduced directly
(outside any test, via a two-line repro script) that **two sequential
`LinDriveSpaceApp(smoke=True)` instances calling `.register(None)` in the same process reliably
raise** `gi.repository.GLib.GError: ... An object is already exported for the interface
org.gtk.Application at /com/mensuramedia/lindrivespace`, even with
`Gio.ApplicationFlags.NON_UNIQUE`, and even after explicit `del`/`gc.collect()` — the D-Bus object
export is tied to the application id's fixed object path, not to how many live Python references
remain. Skipping `.register()` entirely segfaults (`g_application_list_actions: assertion
'application->priv->is_registered' failed`), so `.register()` is not optional.

This is a pre-existing latent problem in the test suite's shared `LinDriveSpaceApp`+`MainWindow`
fixture pattern (only `tests/ui/test_smoke.py` used it at M0); other WPs' UI test files
(`test_explorer.py`, `test_snapshots.py`) independently hit the exact same conflict once more than
one such module runs in one `pytest -q tests/ui` session — confirmed by running the *existing*
suite with `tests/ui/test_overview.py` excluded entirely and seeing the identical
`test_smoke.py` vs `test_snapshots.py` collision (not something this work package introduced).

**Fix scoped to this file only**: `tests/ui/test_overview.py`'s `window` fixture does not create a
`Gtk.Application` at all. `BasePage`/`OverviewPage` only ever touch `window.app.settings`,
`window.app.theme`, `window.scan_history` and `window.request_scan` — a tiny `_FakeApp`/
`_FakeWindow` double provides exactly those, and the page is rendered inside a bare
`Gtk.OffscreenWindow`, the same pattern `tests/ui/test_widgets.py` already uses for widgets. This
keeps the test correct and fast, and — importantly — means it never contends for the shared
D-Bus application object, so it does not make the suite-wide flakiness worse. By the final
verification run in this session the sibling files' conflict had also been resolved (by their own
agents); `DISPLAY=:0 pytest -q tests/ui` now passes with 29/29 green.

## Verification (all green at hand-off)
```
.venv/bin/ruff format src tests && .venv/bin/ruff check src tests     # clean
.venv/bin/python -m pytest -q tests/services                          # 31 passed
DISPLAY=:0 .venv/bin/python -m pytest -q tests/ui                     # 29 passed
DISPLAY=:0 timeout 30 ./run.sh --screenshot .../overview.png          # 1252x897 PNG
```
Screenshot reviewed at full size: 4 mount cards (nvme0n1 p1/p2/p3 + sda1), 3-per-row FlowBox
layout matching the Direction B mockup, no snap-loop/tmpfs/hugepages/mqueue cards by default,
KPI row all four tiles equal height with no clipped text, subtitle reads "4 mounts on 2 disks ·
24 hidden (snap loops, tmpfs) · udev monitor live". Toggling "Show hidden" in a scratch script
confirmed all 42 mounts across 13 groups (real machine's ~10 snap loops + tmpfs/hugepages/mqueue/
etc.) appear when checked.

## Open items for other WPs
- `OverviewPage` never calls `service.stop()` (no `on_hidden` override) — the periodic refresh
  and udev watch keep running even when another page is visible. Matches how `MainWindow`
  instantiates all pages up front and keeps them alive in the `Gtk.Stack`; revisit only if a
  future WP wants pages to be lazily torn down.
- The Used KPI's detail line omits a "+X GB this week" trend (no historical usage log exists
  yet) — noted above.
