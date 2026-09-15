"""Settings page — M0 stub; the real body lands in its work package."""

from __future__ import annotations

from lindrivespace.ui.pages.base import BasePage


class SettingsPage(BasePage):
    title = "Settings"

    def build_content(self) -> None:
        self.add_title(self.title, "Theme, units and scan defaults.")
        self.add_paragraph("This page is being built. See docs/CONCEPT-AND-TECHNICAL-DESIGN.md.")
