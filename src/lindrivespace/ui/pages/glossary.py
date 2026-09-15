"""Glossary page — stub; replaced by its work package."""

from __future__ import annotations

from lindrivespace.ui.pages.base import BasePage


class GlossaryPage(BasePage):
    title = "Glossary"

    def build_content(self) -> None:
        self.add_title(
            self.title,
            "Everything you need to know about Linux drives, space, mountpoints and filesystems.",
        )
        self.add_paragraph("This page is being built.")
