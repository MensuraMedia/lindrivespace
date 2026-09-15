"""ScanBanner — the running scan at the top of the content area (variant B, stats panel).

Left: the percent in Ubuntu Light with "of <path> scanned". Middle: a progress
bar, a key/value row (scanning · scanned · of used · rate · elapsed) and the
queue as square chips — finished ones bold green (no checkmark), the running
one accent, queued ones plain. Right: the estimated countdown in large type
with Pause and Stop beneath. Driven by the ScanRegistry's signals plus a 1 s
tick; hidden when nothing is scanning.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from lindrivespace.config.theme import ThemeDefinition  # noqa: E402
from lindrivespace.services.scan_registry import (  # noqa: E402
    STATE_DONE,
    STATE_QUEUED,
    STATE_SCANNING,
    ScanEntry,
    ScanRegistry,
)


def format_countdown(seconds: float | None) -> str:
    """Compact countdown: "1:42", "0:12", "1:02:03"; "…" while estimating."""
    if seconds is None:
        return "…"
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_elapsed(seconds: float) -> str:
    return format_countdown(max(0.0, seconds))


class ScanBanner(Gtk.Box):
    __gtype_name__ = "LdsScanBanner"

    def __init__(
        self, theme: ThemeDefinition, registry: ScanRegistry, fmt_bytes: Callable[[int], str]
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=22)
        self.theme = theme
        self.registry = registry
        self.fmt_bytes = fmt_bytes
        self._tick_id = 0
        self._last_alloc = 0
        self._last_alloc_at = 0.0
        self._rate = 0.0  # bytes/s, smoothed
        self._eta: float | None = None
        self._eta_at = 0.0
        self._chips: dict[str, Gtk.Label] = {}

        self.get_style_context().add_class("scan-banner")
        self.set_no_show_all(True)

        # ---- left: big percent -------------------------------------------------
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        left.set_valign(Gtk.Align.CENTER)
        pct_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.percent_label = Gtk.Label(label="0")
        self.percent_label.get_style_context().add_class("banner-percent")
        self.percent_label.set_xalign(0.0)
        pct_row.pack_start(self.percent_label, False, False, 0)
        self.percent_sign = Gtk.Label(label="%")
        self.percent_sign.get_style_context().add_class("banner-percent-sign")
        self.percent_sign.set_valign(Gtk.Align.END)
        pct_row.pack_start(self.percent_sign, False, False, 0)
        left.pack_start(pct_row, False, False, 0)
        caption_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(12, 12)
        caption_row.pack_start(self.spinner, False, False, 0)
        self.caption_label = Gtk.Label(label="scanning")
        self.caption_label.get_style_context().add_class("dim")
        self.caption_label.set_xalign(0.0)
        caption_row.pack_start(self.caption_label, False, False, 0)
        left.pack_start(caption_row, False, False, 0)
        self.pack_start(left, False, False, 0)

        # ---- middle: bar, key/value row, queue chips ----------------------------
        middle = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        middle.set_valign(Gtk.Align.CENTER)
        self.progress = Gtk.ProgressBar()
        self.progress.set_show_text(False)
        self.progress.get_style_context().add_class("banner-progress")
        middle.pack_start(self.progress, False, False, 0)

        kv = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=22)
        self.path_label = self._kv(kv, "Scanning")
        self.path_label.get_style_context().add_class("mono")
        self.path_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.path_label.set_max_width_chars(36)
        self.stats_label = self._kv(kv, "scanned")
        self.total_label = self._kv(kv, "of")
        self.rate_label = self._kv(kv, "rate")
        self.elapsed_label = self._kv(kv, "elapsed")
        middle.pack_start(kv, False, False, 0)

        self.queue_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        middle.pack_start(self.queue_box, False, False, 0)
        self.pack_start(middle, True, True, 0)

        # ---- right: countdown + buttons -----------------------------------------
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right.set_valign(Gtk.Align.CENTER)
        self.eta_label = Gtk.Label(label="…")
        self.eta_label.get_style_context().add_class("banner-eta")
        self.eta_label.set_xalign(1.0)
        right.pack_start(self.eta_label, False, False, 0)
        eta_caption = Gtk.Label(label="estimated left")
        eta_caption.get_style_context().add_class("dim")
        eta_caption.set_xalign(1.0)
        right.pack_start(eta_caption, False, False, 0)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        buttons.set_halign(Gtk.Align.END)
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
        right.pack_start(buttons, False, False, 0)
        self.pack_start(right, False, False, 0)

        registry.connect("active-changed", lambda _r, _p: self.refresh())
        registry.connect("entry-changed", lambda _r, _p: self.refresh())

    @staticmethod
    def _kv(box: Gtk.Box, key: str) -> Gtk.Label:
        pair = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        k = Gtk.Label(label=key)
        k.get_style_context().add_class("muted")
        pair.pack_start(k, False, False, 0)
        v = Gtk.Label(label="")
        v.get_style_context().add_class("banner-kv")
        v.set_xalign(0.0)
        pair.pack_start(v, False, False, 0)
        box.pack_start(pair, False, False, 0)
        return v

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
        now = time.monotonic()
        if entry.alloc > self._last_alloc and self._last_alloc_at:
            dt = now - self._last_alloc_at
            if dt > 0:
                inst = (entry.alloc - self._last_alloc) / dt
                self._rate = inst if not self._rate else 0.7 * self._rate + 0.3 * inst
        if entry.alloc != self._last_alloc:
            self._last_alloc, self._last_alloc_at = entry.alloc, now

        self.path_label.set_text(entry.path)
        self.caption_label.set_text(f"of {entry.path} scanned")
        self.stats_label.set_text(self.fmt_bytes(entry.alloc))
        self.rate_label.set_text(f"{self.fmt_bytes(int(self._rate))}/s" if self._rate else "—")
        self.elapsed_label.set_text(format_elapsed(entry.elapsed))
        expected = entry.expected_bytes
        if expected:
            fraction = min(0.99, entry.alloc / expected)
            self.progress.set_fraction(fraction)
            self.percent_label.set_text(f"{int(fraction * 100)}")
            self.total_label.set_text(f"{self.fmt_bytes(expected)} used")
            remaining = max(0, expected - entry.alloc)
            eta = remaining / self._rate if self._rate > 0 else None
            if eta is None and fraction > 0 and entry.elapsed > 1:
                eta = entry.elapsed * (1 / fraction - 1)
            self._eta, self._eta_at = eta, now
        else:
            self.progress.pulse()
            self.percent_label.set_text("…")
            self.total_label.set_text("unknown")
            self._eta = None
        self._update_countdown()
        self._update_chips()

    def _update_chips(self) -> None:
        wanted: list[tuple[str, str]] = []
        for path, e in self.registry.entries.items():
            if e.state in (STATE_DONE, STATE_SCANNING, STATE_QUEUED):
                wanted.append((path, e.state))
        for child in list(self.queue_box.get_children()):
            self.queue_box.remove(child)
        self._chips.clear()
        for path, state in wanted:
            chip = Gtk.Label(label=path)
            ctx = chip.get_style_context()
            ctx.add_class("chip")
            if state == STATE_DONE:
                ctx.add_class("chip-done")  # bold green, no checkmark
            elif state == STATE_SCANNING:
                ctx.add_class("chip-now")
            chip.show()
            self.queue_box.pack_start(chip, False, False, 0)
            self._chips[path] = chip
        self.queue_box.show()

    def _update_countdown(self) -> None:
        if self._eta is None:
            self.eta_label.set_text(format_countdown(None))
            return
        left = self._eta - (time.monotonic() - self._eta_at)
        self.eta_label.set_text(format_countdown(max(0.0, left)))

    def _tick(self) -> bool:
        entry = self.entry
        if entry is None:
            self._tick_id = 0
            return False
        if entry.controller.paused:
            self._eta_at = time.monotonic()  # freeze the countdown while paused
        self.elapsed_label.set_text(format_elapsed(entry.elapsed))
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
