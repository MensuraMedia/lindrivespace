"""KPI tile: uppercase label, large value + unit, dim detail line.

Used in the Overview page's top strip (Total capacity / Used / Free / Scanned
- see ``docs/mockups/images/direction-b-overview-dashboard.png``).
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from lindrivespace.config.layout import Layout  # noqa: E402
from lindrivespace.config.theme import ThemeDefinition  # noqa: E402

_DIMS = Layout.dimensions


class KpiTile(Gtk.Box):
    """A single "card" styled KPI figure: label, big value + unit, detail."""

    __gtype_name__ = "LdsKpiTile"

    def __init__(
        self,
        theme: ThemeDefinition,
        label: str,
        value: str,
        unit: str = "",
        detail: str = "",
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._theme = theme
        self.get_style_context().add_class("card")
        self.set_size_request(-1, _DIMS.KPI_HEIGHT)

        self.label_widget = Gtk.Label(label=label.upper())
        self.label_widget.set_xalign(0.0)
        self.label_widget.get_style_context().add_class("section-title")
        self.pack_start(self.label_widget, False, False, 0)

        value_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        value_row.set_valign(Gtk.Align.BASELINE)
        self.value_label = Gtk.Label(label=value)
        self.value_label.set_xalign(0.0)
        self.value_label.get_style_context().add_class("kpi-value")
        value_row.pack_start(self.value_label, False, False, 0)

        self.unit_label = Gtk.Label(label=unit)
        self.unit_label.set_xalign(0.0)
        self.unit_label.get_style_context().add_class("muted")
        value_row.pack_start(self.unit_label, False, False, 0)
        self.pack_start(value_row, False, False, 0)

        self.detail_label = Gtk.Label(label=detail)
        self.detail_label.set_xalign(0.0)
        self.detail_label.set_line_wrap(True)
        self.detail_label.get_style_context().add_class("dim")
        self.pack_start(self.detail_label, False, False, 0)

    def set_theme(self, theme: ThemeDefinition) -> None:
        """Swap the active theme (kept for API parity; colours come from CSS)."""
        self._theme = theme

    def set_value(self, value: str, unit: str | None = None, detail: str | None = None) -> None:
        """Update the value and, optionally, the unit and/or detail line."""
        self.value_label.set_text(value)
        if unit is not None:
            self.unit_label.set_text(unit)
        if detail is not None:
            self.detail_label.set_text(detail)
