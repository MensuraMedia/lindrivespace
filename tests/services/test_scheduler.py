"""Scan scheduler unit files and status (no real systemd changes)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lindrivespace.services import scheduler


def test_unit_texts_describe_the_collector() -> None:
    service = scheduler._service_text(scan=True)
    assert "-m lindrivespace --collect --scan" in service
    assert "Type=oneshot" in service and "IOSchedulingClass=idle" in service
    service = scheduler._service_text(scan=False)
    assert "--scan" not in service
    timer = scheduler._timer_text("daily")
    assert "OnCalendar=daily" in timer and "Persistent=true" in timer


def test_unit_dir_honours_xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert scheduler.unit_dir() == tmp_path / "systemd" / "user"


def test_intervals_have_calendar_specs() -> None:
    keys = [k for k, _l, _c in scheduler.INTERVALS]
    assert keys == ["hourly", "every-6h", "daily", "weekly"]
    assert all(cal for _k, _l, cal in scheduler.INTERVALS)


def test_status_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scheduler.shutil, "which", lambda _n: None)
    st = scheduler.status()
    assert st.available is False and "systemctl" in st.detail
    ok, why = scheduler.enable("daily")
    assert ok is False and why


def test_run_now_falls_back_to_in_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scheduler, "available", lambda: (False, "no systemd"))
    import lindrivespace.collector as collector

    monkeypatch.setattr(collector, "collect", lambda **_kw: 3)
    ok, msg = scheduler.run_now()
    assert ok and "3" in msg
