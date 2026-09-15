"""Explorer page — M0 stub; the real body lands in its work package."""

from __future__ import annotations

from lindrivespace.ui.pages.base import BasePage


class ExplorerPage(BasePage):
    title = "Explorer"

    def build_content(self) -> None:
        # This page is NOT wrapped in a ScrolledWindow (PageSpec.scrolled=False):
        # the tree view below will own its own scrolling in WP8.
        self.add_title(self.title, "Scan a folder or a mount to see folders and files by size.")
        self.add_paragraph("This page is being built. See docs/CONCEPT-AND-TECHNICAL-DESIGN.md.")
