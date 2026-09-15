"""Hardware page — stub; replaced by its work package."""

from __future__ import annotations

from lindrivespace.ui.pages.base import BasePage


class HardwarePage(BasePage):
    title = "Hardware"

    def build_content(self) -> None:
        self.add_title(
            self.title,
            "Motherboard, CPU, memory, storage controllers, disks and live I/O from local system queries.",
        )
        self.add_paragraph("This page is being built.")
