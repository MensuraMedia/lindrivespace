# Decision Log — LinDriveSpace

Format: date, decision, context, consequences. Newest first.

## 2026-09-14 — Document corrections adopted at build start
Context: pre-build review of `docs/CONCEPT-AND-TECHNICAL-DESIGN.md` against the machine and GTK 3.24.
1. No `GDK_BACKEND=offscreen` in GTK3 → UI tests run on `DISPLAY=:0` (or `broadwayd`) using `Gtk.OffscreenWindow`; `tests/conftest.py` skips them when `Gtk.init_check()` fails.
2. Progressive fill needs pre-order events → `core/events.py` with `DirStarted / DirDone / Progress / Finished / Error`; int ids only; catch `OSError`. Single scanner thread in v1.
3. Drain loop uses `GLib.timeout_add(16, …)` with an 8 ms budget, not idle priority.
4. GTK sorting disabled; `models/tree_model.py` owns order; all columns FIXED sizing; fixed-height mode.
5. pkexec runs a stdlib-only helper (`core/scanner_cli.py` via `data/bin/lindrivespace-scan-helper`), NDJSON over stdout, merged through the same queue.
6. Snapshots use stdlib `gzip` (`.json.gz`), not zstd.
7. Lint/type tooling lives in `.venv` (`ruff`, `mypy`, `pytest`); `run.sh` uses system Python + system PyGObject.
8. Starter's `NavigationManager` dropped; window handles `page-changed`. `Gtk.Application` uses `NON_UNIQUE` for `--smoke`/`--screenshot`.

## 2026-09-14 — Build green-light decisions
1. Direction: **B (Overview Dashboard) as first screen + D's insight panel in the Explorer**. A's tree-table is the Explorer core; C's neumorphic depth only on mount cards/rings.
2. Primary size column: allocated (`st_blocks*512`), toggle to apparent.
3. Units: decimal GB by default, toggle to GiB.
4. Sidebar: 150 px (starter), icons + labels.
5. Light theme: tokens designed now, CSS shipped in v1.1.
6. Packaging: `.deb` only for v1; Flatpak later.

## 2026-09-14 — Architecture
- Layered: `core/` (pure Python) → `models/` (GTK stores) → `services/` (controllers) → `ui/` (window, pages, widgets). Core purity is enforced by rule and test.
- Foundation: `gtk-python-dashboard-starter` — keep `Sidebar` + `BasePage` + CssProvider pattern; replace `Gtk.Window`/`Gtk.main()` with `Gtk.Application`; one theme (gray-temperature) generated from a dataclass instead of seven hard-coded themes.
- Visual system: Ubuntu / Ubuntu Mono; accent `#e95420`; surfaces `#495060 / #343946 / #2d323d / #21252f / #1b1e29`.
- Governance: universal-instruction-set v2026.04 copied into `.claude/`; `memory-rules.md` name per the master CLAUDE.md step 2; example sector rules replaced by `python-gtk.md` and `core-purity.md`.
