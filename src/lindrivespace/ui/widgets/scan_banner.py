"""ScanBanner — the running scan, shown at the top of the content area (variant A).

One line: spinner · "Scanning" + path · progress bar · scanned of used · percent
and rate · estimated countdown · Pause / Stop · "N more queued". Driven entirely
by the ScanRegistry's signals plus a 1 s tick for the countdown; hidden when idle.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from lindrivespace.config.theme import ThemeDefinition  # noqa: E402
from lindrivespace.services.scan_registry import ScanEntry, ScanRegistry  # noqa: E402


def format_countdown(seconds: float | None) -> str:
    """ "≈ 1:42 left", "≈ 12 s left", "estimating…" (None) or "< 5 s left"."""
    if seconds is None:
        return "estimating…"
    if seconds < 5:
        return "< 5 s left"
    if seconds < 60:
        return f"≈ {int(seconds)} s left"
    minutes, secs = divmod(int(seconds), 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"≈ {hours}:{minutes:02d}:{secs:02d} left"
    return f"≈ {minutes}:{secs:02d} left"


class ScanBanner(Gtk.Box):
    __gtype_name__ = "LdsScanBanner"

    def __init__(
        self, theme: ThemeDefinition, registry: ScanRegistry, fmt_bytes: Callable[[int], str]
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        self.theme = theme
        self.registry = registry
        self.fmt_bytes = fmt_bytes
        self._tick_id = 0
        self._last_alloc = 0
        self._last_alloc_at = 0.0
        self._rate = 0.0  # bytes/s, smoothed
        self._eta: float | None = None
        self._eta_at = 0.0

        self.get_style_context().add_class("scan-banner")
        self.set_no_show_all(True)

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(18, 18)
        self.spinner.set_valign(Gtk.Align.CENTER)
        self.pack_start(self.spinner, False, False, 0)

        middle = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        middle.set_valign(Gtk.Align.CENTER)
        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.title_label = Gtk.Label(label="Scanning")
        self.title_label.get_style_context().add_class("banner-title")
        self.title_label.set_xalign(0.0)
        title_row.pack_start(self.title_label, False, False, 0)
        self.path_label = Gtk.Label(label="")
        self.path_label.get_style_context().add_class("mono")
        self.path_label.get_style_context().add_class("muted")
        self.path_label.set_xalign(0.0)
        self.path_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        title_row.pack_start(self.path_label, True, True, 0)
        middle.pack_start(title_row, False, False, 0)
        self.progress = Gtk.ProgressBar()
        self.progress.set_show_text(False)
        self.progress.get_style_context().add_class("banner-progress")
        middle.pack_start(self.progress, False, False, 0)
        self.pack_start(middle, True, True, 0)

        stats = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        stats.set_valign(Gtk.Align.CENTER)
        self.stats_label = Gtk.Label(label="")
        self.stats_label.get_style_context().add_class("banner-stats")
        self.stats_label.set_xalign(1.0)
        stats.pack_start(self.stats_label, False, False, 0)
        self.detail_label = Gtk.Label(label="")
        self.detail_label.get_style_context().add_class("dim")
        self.detail_label.set_xalign(1.0)
        stats.pack_start(self.detail_label, False, False, 0)
        self.pack_start(stats, False, False, 0)

        self.eta_label = Gtk.Label(label="estimating…")
        self.eta_label.get_style_context().add_class("banner-eta")
        self.eta_label.set_valign(Gtk.Align.CENTER)
        self.eta_label.set_width_chars(14)
        self.pack_start(self.eta_label, False, False, 0)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        buttons.set_valign(Gtk.Align.CENTER)
        self.pause_button = Gtk.ToggleButton(label="Pause")
        self.pause_button.set_tooltip_text("Pause the scan")
        self.pause_button.connect("toggled", self._on_pause_toggled)
        buttons.pack_start(self.pause_button, False, False, 0)
        self.stop_button = Gtk.Button()
        self.stop_button.set_image(
            Gtk.Image.new_from_icon_name("process-stop-symbolic", Gtk.IconSize.BUTTON)
        )
        self.stop_button.get_style_context().add_class("banner-stop")
        self.stop_button.set_tooltip_text("Stop this scan")
        self.stop_button.connect("clicked", self._on_stop_clicked)
        buttons.pack_start(self.stop_button, False, False, 0)
        self.queue_label = Gtk.Label(label="")
        self.queue_label.get_style_context().add_class("pill")
        self.queue_label.set_no_show_all(True)
        buttons.pack_start(self.queue_label, False, False, 0)
        self.pack_start(buttons, False, False, 0)

        registry.connect("active-changed", lambda _r, _p: self.refresh())
        registry.connect("entry-changed", lambda _r, _p: self.refresh())

    # ---- state -----------------------------------------------------------------

    @property
    def entry(self) -> ScanEntry | None:
        return self.registry.active_entry

    def refresh(self) -> None:
        entry = self.entry
        if entry is None:
            self._hide()
            return
        if not self.get_visible():
            self._show()
        self.path_label.set_text(entry.path)
        expected = entry.expected_bytes
        now = time.monotonic()
        # smoothed rate from successive progress reports
        if entry.alloc > self._last_alloc and self._last_alloc_at:
            dt = now - self._last_alloc_at
            if dt > 0:
                inst = (entry.alloc - self._last_alloc) / dt
                self._rate = inst if not self._rate else 0.7 * self._rate + 0.3 * inst
        if entry.alloc != self._last_alloc:
            self._last_alloc, self._last_alloc_at = entry.alloc, now

        scanned = self.fmt_bytes(entry.alloc)
        if expected:
            fraction = min(0.99, entry.alloc / expected)
            self.progress.set_fraction(fraction)
            self.stats_label.set_text(f"{scanned} of {self.fmt_bytes(expected)}")
            remaining = max(0, expected - entry.alloc)
            eta = remaining / self._rate if self._rate > 0 else None
            if eta is None and fraction > 0 and entry.elapsed > 1:
                eta = entry.elapsed * (1 / fraction - 1)
            self._eta, self._eta_at = eta, now
            rate_text = f" · {self.fmt_bytes(int(self._rate))}/s" if self._rate else ""
            self.detail_label.set_text(f"{fraction * 100:.0f} %{rate_text}")
        else:
            self.progress.pulse()
            self.stats_label.set_text(scanned)
            rate_text = f"{self.fmt_bytes(int(self._rate))}/s" if self._rate else ""
            self.detail_label.set_text(rate_text)
            self._eta = None
        self._update_countdown()
        queued = len(self.registry.queue)
        if queued:
            self.queue_label.set_text(f"{queued} more queued")
            self.queue_label.show()
        else:
            self.queue_label.hide()

    def _update_countdown(self) -> None:
        if self._eta is None:
            self.eta_label.set_text(format_countdown(None))
            return
        left = self._eta - (time.monotonic() - self._eta_at)
        self.eta_label.set_text(format_countdown(max(0.0, left)))

    def _tick(self) -> bool:
        if self.entry is None:
            self._tick_id = 0
            return False
        if self.entry.controller.paused:
            self._eta_at = time.monotonic()  # freeze the countdown while paused
        self._update_countdown()
        return True

    def _show(self) -> None:
        self.show()
        for child in self.get_children():
            child.show_all()
        self.spinner.start()
        self.pause_button.set_active(False)
        self._last_alloc = 0
        self._last_alloc_at = 0.0
        self._rate = 0.0
        self._eta = None
        if not self._tick_id:
            self._tick_id = GLib.timeout_add_seconds(1, self._tick)

    def _hide(self) -> None:
        self.spinner.stop()
        self.hide()
        if self._tick_id:
            GLib.source_remove(self._tick_id)
            self._tick_id = 0

    # ---- buttons -------------------------------------------------------------------

    def _on_pause_toggled(self, button: Gtk.ToggleButton) -> None:
        entry = self.entry
        if entry is None:
            return
        if button.get_active():
            entry.controller.pause()
            self.spinner.stop()
            button.set_label("Resume")
        else:
            entry.controller.resume()
            self.spinner.start()
            button.set_label("Pause")

    def _on_stop_clicked(self, _button: Gtk.Button) -> None:
        entry = self.entry
        if entry is not None:
            self.registry.cancel(entry.path)
