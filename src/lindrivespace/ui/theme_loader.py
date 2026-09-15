"""Turns a ThemeDefinition into GTK CSS and installs it screen-wide.

Adapted from the starter's ``manager_theme_applicator.py`` (one CssProvider at
application priority, re-loaded on theme change). Instead of an f-string with
hard-coded rules, the colour tokens become ``@define-color`` lines and the
component rules live in ``data/css/app.css`` referencing ``@token`` names.
"""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from lindrivespace.config.theme import ThemeDefinition  # noqa: E402


class ThemeLoader:
    def __init__(self, css_path: Path) -> None:
        self.css_path = css_path
        self.provider = Gtk.CssProvider()
        self.current: ThemeDefinition | None = None
        self._installed = False

    def build_css(self, theme: ThemeDefinition) -> str:
        lines = [f"/* tokens: {theme.name} */"]
        for name, value in theme.colour_tokens().items():
            lines.append(f"@define-color {name} {value};")
        lines.append(f"@define-color accent_soft alpha({theme.accent}, 0.22);")
        lines.append("")
        try:
            lines.append(self.css_path.read_text(encoding="utf-8"))
        except OSError as exc:
            lines.append(f"/* app.css not found: {exc} */")
        return "\n".join(lines)

    def apply(self, theme: ThemeDefinition) -> None:
        css = self.build_css(theme)
        self.provider.load_from_data(css.encode("utf-8"))
        if not self._installed:
            screen = Gdk.Screen.get_default()
            if screen is not None:
                Gtk.StyleContext.add_provider_for_screen(
                    screen, self.provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
                self._installed = True
        settings = Gtk.Settings.get_default()
        if settings is not None:
            settings.set_property("gtk-application-prefer-dark-theme", theme.dark)
        self.current = theme
