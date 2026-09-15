"""Favorites page — stub; WP14 replaces the body."""

from __future__ import annotations

from lindrivespace.ui.pages.base import BasePage


class FavoritesPage(BasePage):
    title = "Favorites"

    def build_content(self) -> None:
        self.add_title(
            self.title, "Folders and files you starred, one click from their space view."
        )
        self.add_paragraph("This page is being built.")
