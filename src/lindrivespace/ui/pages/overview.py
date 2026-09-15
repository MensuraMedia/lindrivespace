"""Mounted filesystems page — M0 stub; the real body lands in its work package."""

from __future__ import annotations

from lindrivespace.ui.pages.base import BasePage


class OverviewPage(BasePage):
    title = "Mounted filesystems"

    def build_content(self) -> None:
        self.add_title(
            self.title,
            "Every mount and partition with used / free. Scan any card to open the Explorer.",
        )
        self.add_paragraph("This page is being built. See docs/CONCEPT-AND-TECHNICAL-DESIGN.md.")
