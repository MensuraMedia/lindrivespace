# Change: Share % = share of the scan; Of parent % optional; review fixes

**Date:** 2026-09-16 · **Type:** semantics fix + bug fixes (user request, adversarial review)

- core/fsnode.py (frozen, additive): `share_of(ancestor, allocated)`; `percent_of_parent` unclamped.
- models/tree_model.py: `FileRow.nlink` + `share_of`; `list_files` attributes 1/nlink; `share()`,
  `_percent_unavailable()` ("—"), display kind "share", DISPLAY_KINDS/SORT_COLUMNS, bar binding
  clamps fill and sets `emphasis` above 100 %, Type column "hard link ×N".
- ui/widgets/explorer_tree.py: columns ("share", "Share %", bar) + ("of_parent", "Of parent %", text,
  hidden by default; a new id so layouts saved before it keep it hidden); tooltips; new columns inserted at their default position for saved layouts.
- ui/widgets/percent_bar_renderer.py: clip to cell, bar shrinks with the column.
- ui/pages/explorer.py: Hidden toggle updates `model.show_hidden`.
- services/export.py: `share_of_root` in CSV/JSON. config/settings.py: hidden_columns default.
- app.py: window-build failure exits --smoke/--screenshot with code 3 instead of hanging.
- Tests: tests/models (3 new), tests/ui/test_widgets (1), tests/services/test_export (assert).
- Docs: decisions, BACKLOG §F, ISSUES 2.13, README, changelog; screenshots re-captured.
