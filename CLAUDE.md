# Project: LinDriveSpace — CLAUDE.md (v2026.04 — Claude Code Native)

## Overview
GTK3/Python disk-space explorer for Linux Mint: mounts, partitions, folder and file sizes in a
TreeSize-style tree-table (Size, Allocated, Files, Folders, % of Parent, Modified), with an Overview
dashboard of mounts and an insight panel (treemap, top files, types, age). Native GTK 3.24, Python 3.12,
Ubuntu type + Ubuntu orange on the gray-temperature palette. Concept: `docs/CONCEPT-AND-TECHNICAL-DESIGN.md`.

## Architecture
- Language/Framework: Python 3.12 + GTK 3.24 (PyGObject, pycairo)
- Build system: `pyproject.toml` (setuptools); Debian packaging via `debian/` (dh-python)
- Key dependencies: PyGObject, pycairo, psutil, pyudev (all from apt: `python3-gi gir1.2-gtk-3.0 python3-psutil python3-pyudev`), fonts-ubuntu, policykit-1
- Layers: `src/lindrivespace/core` (pure Python engine, no GTK) → `models` (Gtk stores) → `services` (controllers, actions, privilege) → `ui` (window, sidebar, pages, widgets)
- Foundation: fork of `gtk-python-dashboard-starter` (150 px sidebar, `Gtk.Stack` pages, CSS from tokens)

## Build & Runtime Standards (Enforced)
```
# Build (no compile step; editable install for tests)
.venv/bin/pip install -e . --no-deps

# Test
.venv/bin/python -m pytest -q tests/core
DISPLAY=:0 .venv/bin/python -m pytest -q tests/ui tests/models

# Lint
.venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests
.venv/bin/mypy --strict src/lindrivespace/core

# Run
./run.sh                       # system python3 + system PyGObject
python3 -m lindrivespace --smoke
python3 -m lindrivespace --screenshot /tmp/shot.png
```
- Use /plan-first for complex features or multi-file changes
- Use /build-test to run the full pipeline
- Performance budgets: scan ≥ 150 k entries/s warm; first row < 200 ms; drain ≤ 8 ms per tick; ≤ 250 MB RSS at 1 M directories
- `core/` must pass `mypy --strict` and the purity test (`tests/core/test_purity.py`)

## Project Conventions
- `ruff` line length 100; imports sorted; type hints everywhere; dataclasses for values; `__slots__` on `FsNode`
- Colours/metrics only from `config/theme.py` and `config/layout.py`
- Shared files (`ui/pages/__init__.py`, `app.py`, `ui/window.py`, `pyproject.toml`, `tests/conftest.py`, `core/__init__.py`, `config/theme.py`, `changelog.md`) are edited only by the orchestrator between work-package groups
- `core/{events,options,fsnode}.py` are frozen contracts after WP1
- Agents write `.claude/memory/changes/<date>-wpN.md`; only the orchestrator appends `changelog.md` and commits
- Dev venv: `python3 -m venv --system-site-packages .venv && .venv/bin/pip install ruff mypy pytest`

## Sector-Specific Rules
<!-- Path-scoped rules load automatically when editing matching files -->
@.claude/rules/ for all active rules (`python-gtk.md` for `src/**`, `core-purity.md` for `core/**`)

## Memory & Workflow
- Use official Auto Memory (/memory) for Claude's own learnings across sessions
- Human-readable history supplements Auto Memory:
  - Session logs: `.claude/memory/sessions/`
  - Change manifests: `.claude/memory/changes/`
  - Decision log: `.claude/memory/decisions.md`
  - Pending items: `.claude/memory/pending.md`
  - Memory index: `.claude/memory/MEMORY.md`
- End every significant session with /session-end or the session-end checklist
- Update changelog.md as changes are made, not after

## Hooks (Automated)
Lifecycle hooks are configured in `.claude/settings.json`:
- **SessionStart**: Injects pending items, last session log, and recent changelog
- **PreToolUse**: Security gate blocks secret file access and destructive commands (needs `jq`)
- **PostToolUse**: `ruff format` + `ruff check --fix` on edited `.py` files (Python block enabled)
- **SubagentStart/Stop, TeammateIdle, TaskCompleted**: agent lifecycle logging to `.claude/board.md`

## Custom Commands
- `/plan-first` — Plan complex tasks before executing
- `/build-test` — Run full build + test pipeline from CLAUDE.md
- `/session-end` — End-of-session wrap-up and logging
- `/team`, `/route` — agent orchestration and model routing (see `.claude/routing-rules.md`)

## References
- @docs/ for project documentation (concept, mockups)
- @.claude/rules/ for path-scoped rules
- @.claude/memory/decisions.md for architectural decision history
- @.claude/board.md for the collaboration board
