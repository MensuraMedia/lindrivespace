# Project Change Log

> Local record of all changes. Does NOT depend on git. Updated every time a change is made.

| Date-Time | Change Description |
|-----------|-------------------|
| 2026-09-14T18:40:00 | Project created. Concept & technical design written to docs/CONCEPT-AND-TECHNICAL-DESIGN.md. |
| 2026-09-14T18:55:00 | Design mockups (Directions A–D + component sheet) written to docs/mockups/lindrivespace-mockups.html and published. |
| 2026-09-14T19:05:00 | Build plan approved (green-light). Direction: B Overview first screen + D insight panel; allocated primary; decimal GB; 150 px sidebar; light theme v1.1; .deb only. |
| 2026-09-14T19:10:00 | WP0: universal-instruction-set v2026.04 deployed (.claude/ agents, skills, roles, hooks, commands, rules, settings), git initialised with origin, dev venv (ruff, mypy, pytest). |
| 2026-09-14T20:30:00 | README.md written (purpose, features, screens, design language, architecture, install, roadmap); mockup boards rendered to docs/mockups/images/*.png; mockup page gained single-board capture mode (#dirA…#sheet). |
| 2026-09-14T21:10:00 | WP1 (M0): Gtk.Application skeleton — header bar, 150 px sidebar with logo + icon nav, Gtk.Stack with 4 stub pages, token-driven CSS (app.css + @define-color), frozen core contracts (fsnode, events, options), settings store, test harness (core headless, ui on DISPLAY), --smoke/--screenshot. Design doc §16 errata added. |
| 2026-09-14T22:40:00 | WP2: core scanner (iterative scandir DFS, pre-order events, mount boundary, hard-link dedupe, cancel/pause, ScanThread), core/units.py formatters, stdlib-only scanner_cli.py (NDJSON, pkexec-ready), 37 tests, bench ≈150k entries/s. |
| 2026-09-14T22:40:00 | WP3: core/mounts.py (psutil + mountinfo + lsblk merge on (maj:min, mountpoint), statvfs usage, group_by_disk, lazy pyudev MountMonitor fd), 27 tests with captured fixtures. Design doc §16 gained the bind-mount merge note. |
| 2026-09-14T22:40:00 | WP5: ui/widgets — PercentBarRenderer (Cairo cell renderer, fixed height), RingGauge, MountCard (+MountCardData, scan-requested/selected signals), KpiTile; 11 offscreen-rendered tests. |
| 2026-09-14T22:40:00 | WP6: models/tree_model.py (3-column lazy TreeStore, draw-time formatting via cell data funcs, LIS move-based model-owned sort, running totals, O(1) prepend inserts) and services/scan_controller.py (16 ms drain with 8 ms budget, GObject signals, FakeProducer); 7 tests incl. real end-to-end scan. |
| 2026-09-14T23:20:00 | WP4: core/treemap.py (squarify, layout_node, hit_test), core/classify.py (FileClass, summarize_top_files), core/snapshot.py (gzip JSON with iterative writer/reader, list, diff); 27 tests. config/settings.py typed for mypy --strict. |
