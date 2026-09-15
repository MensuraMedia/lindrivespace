"""core/ must import with GTK blocked (see .claude/rules/core-purity.md)."""

from __future__ import annotations

import pkgutil
import subprocess
import sys
from pathlib import Path

import lindrivespace.core as core_pkg

SRC = Path(__file__).resolve().parents[2] / "src"


def core_modules() -> list[str]:
    return sorted(
        f"lindrivespace.core.{m.name}"
        for m in pkgutil.iter_modules(core_pkg.__path__)
        if not m.name.startswith("_")
    )


def test_core_imports_without_gtk() -> None:
    modules = core_modules()
    assert modules, "no core modules found"
    blocked = ["gi", "cairo", "gi.repository", "lindrivespace.ui", "lindrivespace.models"]
    script = (
        "import sys\n"
        + "".join(f"sys.modules[{m!r}] = None\n" for m in blocked)
        + "".join(f"import {m}\n" for m in modules)
        + "print('pure')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "pure"
