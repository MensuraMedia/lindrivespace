# Change: change-table colours, configurable logging, Scanned column removed, backlog

**Date:** 2026-09-15 · **Type:** feature + fixes + investigation (user request)

- `ui/pages/snapshots.py`: `_change_colour_func` / `change_colour_for(delta)` — Change and
  Difference cells red (theme.danger, bold) for growth/new, green (theme.ok) for reductions/deleted.
- `logsetup.py`: `LEVELS`, `level_value`, `_install_file_handler`, `reconfigure(directory, level)`,
  `current_level`; `setup_logging(level=)`; reporter disabled after its first failure.
  `config/settings.py`: `logging.dir` ("" = default) / `logging.level` ("info").
  `app.py`: `apply_logging_settings()` at construction (skipped under --debug).
  `ui/pages/settings.py`: Diagnostics card (FileChooserButton folder + Default, level combo,
  current log path, Open log folder); About keeps a pointer row.
- `ui/widgets/mount_list.py`: Scanned column removed from view/ids/titles (store column kept for
  the Scan/Rescan label); `restore_state` filters retired ids; star click handles the 2-tuple
  return of `cell_get_position` (root cause of the ValueError storm).
- `ui/window.py`: `report_error` uses no-show-all-safe `show_all()` and cannot raise.
- Tests: colours (history page), `reconfigure` (core), Diagnostics group (settings page).
- `docs/BACKLOG.md`: findings A1–A6 (click delay), B1–B4 (errors), C1–C5 (performance), D1–D2.

Files: src/lindrivespace/{logsetup.py,app.py}, config/settings.py, ui/pages/{snapshots,settings}.py,
ui/widgets/mount_list.py, ui/window.py, tests/{core/test_logsetup.py,ui/test_history_page.py,
ui/test_settings_page.py,ui/test_overview.py}, docs/BACKLOG.md, changelog.md, docs/HANDOFF.md
