# Change: performance fixes E1–E5 (docs/BACKLOG.md)

**Date:** 2026-09-15 · **Type:** performance (user request after the scripted walkthrough)

- core/snapshot.py: `_read_header()` + header-only `list_snapshots()` (full parse fallback); `save_snapshot` writes `alloc` into meta.
- services/forkwork.py (new): `run_in_child(work, on_done)` — fork, pickle result over a pipe, GLib io watch, waitpid; inline fallback if fork fails. Used by app.autosave_snapshot and HistoryPage._refresh_change_panel (thread removed).
- services/scan_registry.py: `_freeze_tree_objects()` every 2 s during a scan and at finish. models/tree_model.py: `reset()` breaks parent/children links.
- core/options.py: `top_min_bytes` (default 65 536); core/fsnode.py: `add_file(..., keep=True)`; core/scanner.py passes `alloc >= top_min`; config/settings.py `scan.top_min_bytes`; app.make_scan_options; Settings › Scanning spin (KB).
- ui/pages/glossary.py: revealer body built on first expand. data/css/app.css: `transition: none` on buttons/nav/check/radio/switch.
- Tests: tests/services/test_forkwork.py (3), test_snapshot header (2), test_scanner threshold, test_tree_model reset, test_glossary_page lazy body; tests/ui/test_insight_panel.py fixture sets the threshold to 0 for its tiny files.
- Docs: decisions.md, BACKLOG (E1–E5, A1, A2, C3 fixed), ISSUES 2.10–2.12, HANDOFF.
