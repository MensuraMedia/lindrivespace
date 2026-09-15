from __future__ import annotations

from pathlib import Path

from lindrivespace.config.settings import Settings, config_dir
from lindrivespace.config.theme import DEFAULT_THEME_ID, GRAY_TEMPERATURE_DARK, get_theme


def test_defaults_and_roundtrip(isolated_xdg: Path) -> None:
    s = Settings()
    assert s.path.parent == config_dir()
    assert s.get("theme") == DEFAULT_THEME_ID
    assert s.get("explorer.sort.column") == "alloc"
    s.set("units", "binary")
    s.set("explorer.widths.name", 320)
    s.save()

    again = Settings()
    assert again.get("units") == "binary"
    assert again.get("explorer.widths.name") == 320
    assert again.get("scan.top_files") == 50  # defaults survive a partial file


def test_unknown_keys_preserved(isolated_xdg: Path) -> None:
    s = Settings()
    s.set("future.flag", True)
    s.save()
    assert Settings().get("future.flag") is True


def test_theme_tokens() -> None:
    t = get_theme(None)
    assert t is GRAY_TEMPERATURE_DARK
    tokens = t.colour_tokens()
    assert tokens["accent"] == "#e95420"
    assert len(tokens) == 18
    r, g, b = t.rgb("accent")
    assert round(r * 255) == 0xE9 and round(g * 255) == 0x54 and round(b * 255) == 0x20
    assert get_theme("nope") is GRAY_TEMPERATURE_DARK
