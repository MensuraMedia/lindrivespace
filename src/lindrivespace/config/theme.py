"""Theme tokens.

One frozen dataclass holds the 18 colour tokens from the concept document §7.2.
The UI turns it into GTK ``@define-color`` declarations (see ui/theme_loader.py);
Cairo widgets read RGB tuples through :meth:`ThemeDefinition.rgb`.
This module is GTK-free so it can be unit-tested and reused by the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class ThemeDefinition:
    id: str
    name: str
    dark: bool

    # surfaces
    bg_canvas: str
    bg_surface: str
    bg_surface_2: str
    bg_sunken: str
    bg_deep: str
    line: str
    line_soft: str
    highlight: str  # 1 px top highlight on raised cards

    # text
    fg: str
    fg_muted: str
    fg_dim: str

    # accent
    accent: str
    accent_hot: str
    aubergine: str
    warm_grey: str

    # semantic
    ok: str
    warn: str
    danger: str

    # type (fixed across themes)
    font_ui: str = "Ubuntu, Cantarell, sans-serif"
    font_mono: str = "Ubuntu Mono, DejaVu Sans Mono, monospace"

    def colour_tokens(self) -> dict[str, str]:
        """All colour tokens as ``{token_name: '#rrggbb'}``."""
        out: dict[str, str] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, str) and value.startswith("#"):
                out[f.name] = value
        return out

    def rgb(self, token: str) -> tuple[float, float, float]:
        """Colour token as 0–1 floats for Cairo."""
        return hex_to_rgb(getattr(self, token))

    def rgba(self, token: str, alpha: float) -> tuple[float, float, float, float]:
        r, g, b = self.rgb(token)
        return (r, g, b, alpha)


def hex_to_rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    r, g, b = (int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (r, g, b)


GRAY_TEMPERATURE_DARK = ThemeDefinition(
    id="gray-temperature-dark",
    name="Gray Temperature (Dark)",
    dark=True,
    bg_canvas="#495060",
    bg_surface="#343946",
    bg_surface_2="#2d323d",
    bg_sunken="#21252f",
    bg_deep="#1b1e29",
    line="#1c1f28",
    line_soft="#3e414d",
    highlight="#4c505e",
    fg="#eeeeee",
    fg_muted="#b9bcc6",
    fg_dim="#7d8290",
    accent="#e95420",
    accent_hot="#fd5c01",
    aubergine="#772953",
    warm_grey="#aea79f",
    ok="#3fb950",
    warn="#f5a623",
    danger="#e0362c",
)

# Tokens designed now; the light CSS pass ships in v1.1 (decision 2026-09-14 #5).
GRAY_TEMPERATURE_LIGHT = ThemeDefinition(
    id="gray-temperature-light",
    name="Gray Temperature (Light)",
    dark=False,
    bg_canvas="#f3f3f1",
    bg_surface="#ffffff",
    bg_surface_2="#f8f8f6",
    bg_sunken="#e8e8e6",
    bg_deep="#fbe6de",
    line="#dcdcd8",
    line_soft="#e6e6e2",
    highlight="#ffffff",
    fg="#333333",
    fg_muted="#5f6368",
    fg_dim="#9a9ea6",
    accent="#e95420",
    accent_hot="#fd5c01",
    aubergine="#772953",
    warm_grey="#aea79f",
    ok="#2e9e44",
    warn="#d98c0c",
    danger="#c92f26",
)

THEMES: dict[str, ThemeDefinition] = {
    GRAY_TEMPERATURE_DARK.id: GRAY_TEMPERATURE_DARK,
    GRAY_TEMPERATURE_LIGHT.id: GRAY_TEMPERATURE_LIGHT,
}
DEFAULT_THEME_ID = GRAY_TEMPERATURE_DARK.id


def get_theme(theme_id: str | None) -> ThemeDefinition:
    return THEMES.get(theme_id or DEFAULT_THEME_ID, GRAY_TEMPERATURE_DARK)
