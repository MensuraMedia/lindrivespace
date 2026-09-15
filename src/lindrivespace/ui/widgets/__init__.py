"""Custom-drawn widgets for LinDriveSpace.

Percent bars, ring gauges, mount cards and KPI tiles. Every widget takes a
``ThemeDefinition`` (constructor argument ``theme``) and draws with Cairo
using ``theme.rgb(token)`` / ``theme.rgba(token, alpha)`` -- never a literal
hex colour. Metrics come from ``lindrivespace.config.layout.Layout.dimensions``.
"""

from __future__ import annotations

from lindrivespace.ui.widgets.bar_gauge import BarGauge
from lindrivespace.ui.widgets.kpi_tile import KpiTile
from lindrivespace.ui.widgets.mount_card import MountCard, MountCardData
from lindrivespace.ui.widgets.percent_bar_renderer import PercentBarRenderer
from lindrivespace.ui.widgets.ring_gauge import RingGauge, colour_token_for_percent

__all__ = [
    "KpiTile",
    "MountCard",
    "MountCardData",
    "PercentBarRenderer",
    "BarGauge",
    "RingGauge",
    "colour_token_for_percent",
]
