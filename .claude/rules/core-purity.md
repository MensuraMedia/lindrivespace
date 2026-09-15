---
paths:
  - "src/lindrivespace/core/**"
---

# Core Purity Rule

`src/lindrivespace/core/` is the headless engine. It MUST import nothing from `gi`, `Gtk`, `Gdk`,
`GLib`, `Gio`, `cairo` or any `lindrivespace.ui` / `lindrivespace.models` / `lindrivespace.services`
module. Standard library plus `psutil` and `pyudev` only (and `pyudev` only inside `core/mounts.py`,
imported lazily so the module still imports without it).

Why: the scanner also runs as a root helper under `pkexec` with a clean environment, must be unit-
testable without a display, and will back a future CLI. `tests/core/test_purity.py` imports every
core module with `sys.modules["gi"] = None` and fails the build if any import leaks.

Communication with the UI is one-way through the dataclasses in `core/events.py`
(`DirStarted`, `DirDone`, `Progress`, `Finished`, `Error`) placed on a `queue.SimpleQueue`.
