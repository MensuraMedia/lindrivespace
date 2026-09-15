# Change: WP9 — collapsible insight panel (Analysis view)

**Date:** 2026-09-15
**Work package:** WP9 (agent, finished by the orchestrator after a rate-limit stop)
**Type:** feature

## Summary
Direction D's right-hand panel inside the Explorer: tabs Treemap / Top files / Types / Age fed by
the selected folder; collapsible via the toolbar toggle, the panel's collapse button and F9; state
persisted in `window.panel_visible`; auto-hides below 1100 px window width.

## Files
- `src/lindrivespace/ui/widgets/{insight_panel,treemap_view,top_files_view,file_types_view,age_view}.py`
- `src/lindrivespace/ui/pages/explorer.py` (panel slot, toggle, F9, auto-hide), `ui/widgets/scan_toolbar.py` (panel button)
- `tests/ui/test_insight_panel.py` (10 tests)

## Orchestrator fixes after the agent stopped
- `Gtk.Paned` clamped the divider to 0 on its first tiny allocation, hiding the tree behind the
  panel: fixed with a 420 px minimum on the tree, `pack1(resize=True, shrink=False)` and
  `pack2(resize=False, shrink=False)` (the panel keeps its PANEL_WIDTH request), no `set_position`.
- `TreemapView.items` now lays out on demand (cached by size/version) so consumers never see a
  stale empty list before the first draw.
- The panel test fixture re-attaches the panel after the collapse tests.
