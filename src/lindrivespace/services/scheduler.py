"""Scan scheduler: a systemd *user* timer that runs ``lindrivespace --collect``.

Enable → writes ``~/.config/systemd/user/lindrivespace-collect.{service,timer}``
and runs ``systemctl --user enable --now`` on the timer. Everything is best
effort and reports plain-language status; nothing here needs root.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from lindrivespace import logsetup

UNIT_NAME = "lindrivespace-collect"
INTERVALS: tuple[tuple[str, str, str], ...] = (
    ("hourly", "Every hour", "hourly"),
    ("every-6h", "Every 6 hours", "*-*-* 00/6:00:00"),
    ("daily", "Every day", "daily"),
    ("weekly", "Every week", "weekly"),
)

log = logsetup.get_logger("scheduler")


@dataclass(frozen=True)
class SchedulerStatus:
    available: bool  # systemd --user reachable
    enabled: bool
    active: bool
    interval: str
    scan: bool
    next_run: str
    last_run: str
    detail: str


def unit_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "systemd" / "user"


def _systemctl(*args: str, timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def available() -> tuple[bool, str]:
    if shutil.which("systemctl") is None:
        return (False, "systemctl not found")
    try:
        result = _systemctl("--version")
    except (OSError, subprocess.SubprocessError) as exc:
        return (False, f"systemd user session unavailable: {exc}")
    if result.returncode != 0:
        return (False, "systemd user session unavailable")
    return (True, "")


def _launcher_command() -> str:
    """How the timer starts the collector — the same interpreter as the app."""
    return f"{sys.executable} -m lindrivespace --collect"


def _service_text(scan: bool) -> str:
    src = Path(__file__).resolve().parents[2]
    cmd = _launcher_command() + (" --scan" if scan else "")
    return (
        "[Unit]\n"
        "Description=LinDriveSpace background space collector\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"Environment=PYTHONPATH={src}\n"
        f"ExecStart={cmd}\n"
        "Nice=10\n"
        "IOSchedulingClass=idle\n"
    )


def _timer_text(on_calendar: str) -> str:
    return (
        "[Unit]\n"
        "Description=Run the LinDriveSpace collector on a schedule\n\n"
        "[Timer]\n"
        f"OnCalendar={on_calendar}\n"
        "Persistent=true\n"
        "RandomizedDelaySec=5min\n\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )


def enable(interval: str = "daily", *, scan: bool = False) -> tuple[bool, str]:
    ok, why = available()
    if not ok:
        return (False, why)
    calendar = next((cal for key, _label, cal in INTERVALS if key == interval), "daily")
    directory = unit_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{UNIT_NAME}.service").write_text(_service_text(scan), encoding="utf-8")
        (directory / f"{UNIT_NAME}.timer").write_text(_timer_text(calendar), encoding="utf-8")
    except OSError as exc:
        return (False, f"could not write unit files: {exc}")
    for args in (("daemon-reload",), ("enable", "--now", f"{UNIT_NAME}.timer")):
        try:
            result = _systemctl(*args, timeout=15.0)
        except (OSError, subprocess.SubprocessError) as exc:
            return (False, f"systemctl {' '.join(args)} failed: {exc}")
        if result.returncode != 0:
            return (False, (result.stderr or result.stdout).strip() or "systemctl failed")
    log.info("scheduler enabled: %s (scan=%s)", interval, scan)
    labels = {key: label for key, label, _cal in INTERVALS}
    return (True, f"enabled, {labels.get(interval, interval).lower()}")


def disable() -> tuple[bool, str]:
    ok, why = available()
    if not ok:
        return (False, why)
    try:
        _systemctl("disable", "--now", f"{UNIT_NAME}.timer", timeout=15.0)
    except (OSError, subprocess.SubprocessError) as exc:
        return (False, f"systemctl failed: {exc}")
    log.info("scheduler disabled")
    return (True, "disabled")


def run_now() -> tuple[bool, str]:
    """Trigger one collection immediately (through systemd if enabled, else in-process)."""
    ok, _why = available()
    if ok:
        try:
            result = _systemctl("start", f"{UNIT_NAME}.service", timeout=20.0)
            if result.returncode == 0:
                return (True, "collection started in the background")
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        from lindrivespace.collector import collect

        written = collect()
        return (True, f"recorded {written} sample(s)")
    except Exception as exc:  # noqa: BLE001
        return (False, f"collection failed: {exc}")


def _timer_field(name: str) -> str:
    try:
        result = _systemctl("show", f"{UNIT_NAME}.timer", "-p", name, "--value")
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def status() -> SchedulerStatus:
    ok, why = available()
    if not ok:
        return SchedulerStatus(False, False, False, "daily", False, "", "", why)
    enabled = _systemctl("is-enabled", f"{UNIT_NAME}.timer").stdout.strip() == "enabled"
    active = _systemctl("is-active", f"{UNIT_NAME}.timer").stdout.strip() == "active"
    interval, scan = "daily", False
    try:
        timer_text = (unit_dir() / f"{UNIT_NAME}.timer").read_text(encoding="utf-8")
        for key, _label, cal in INTERVALS:
            if f"OnCalendar={cal}" in timer_text:
                interval = key
        service_text = (unit_dir() / f"{UNIT_NAME}.service").read_text(encoding="utf-8")
        scan = "--scan" in service_text
    except OSError:
        pass
    next_run = _timer_field("NextElapseUSecRealtime") if active else ""
    last_run = _timer_field("LastTriggerUSec") if enabled else ""
    detail = "runs in the background even when the app is closed" if active else "not scheduled"
    return SchedulerStatus(True, enabled, active, interval, scan, next_run, last_run, detail)
