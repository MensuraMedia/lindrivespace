"""Glossary page (WP15) -- brief, searchable explanations of Linux disks,
partitions, filesystems, mounting, space accounting, the directory tree,
storage subsystems and best practices.

Content lives in ``core.glossary`` (pure Python, no GTK). This page is a
search entry plus a row of category chips over a scrolling ``Gtk.ListBox``
of "card" rows; activating a row expands a ``Gtk.Revealer`` holding its full
body text and "See also" links to related terms. Only one row is expanded
at a time.

The page is registered with ``scrolled=False`` in ``ui/pages/__init__.py``,
so it owns its own ``Gtk.ScrolledWindow`` around the term list rather than
being wrapped by the window.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from lindrivespace.config.layout import Layout  # noqa: E402
from lindrivespace.core import glossary  # noqa: E402
from lindrivespace.core.glossary import Term  # noqa: E402
from lindrivespace.ui.pages.base import BasePage  # noqa: E402

_SPACING = Layout.spacing


class GlossaryPage(BasePage):
    title = "Glossary"

    def build_content(self) -> None:
        self._current_query = ""
        self._current_category = "all"
        self._category_guard = False
        self._expanded_key: str | None = None
        self._rows_by_key: dict[str, Gtk.ListBoxRow] = {}

        self.add_title(
            self.title,
            "Linux drives, space, mountpoints and filesystems, explained briefly.",
        )

        self._build_search_row()
        self._build_category_chips()

        self.count_label = Gtk.Label()
        self.count_label.set_xalign(0.0)
        count_ctx = self.count_label.get_style_context()
        count_ctx.add_class("mono")
        count_ctx.add_class("dim")
        self.pack_start(self.count_label, False, False, 0)

        self._build_list()
        self._rebuild_rows()

    # ---- construction -----------------------------------------------------

    def _build_search_row(self) -> None:
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search terms…")
        self.search_entry.get_accessible().set_name("Search glossary terms")
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.search_entry.connect("key-press-event", self._on_search_key_press)
        self.pack_start(self.search_entry, False, False, 0)

    def _build_category_chips(self) -> None:
        chips_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        chips_box.get_style_context().add_class("linked")

        self.category_buttons: dict[str, Gtk.ToggleButton] = {}

        all_button = Gtk.ToggleButton(label="All")
        all_button.set_active(True)
        all_button.get_accessible().set_name("Category: All")
        all_button.connect("toggled", self._on_category_toggled, "all")
        chips_box.pack_start(all_button, False, False, 0)
        self.category_buttons["all"] = all_button

        for cat_id, label in glossary.CATEGORIES:
            button = Gtk.ToggleButton(label=label)
            button.get_accessible().set_name(f"Category: {label}")
            button.connect("toggled", self._on_category_toggled, cat_id)
            chips_box.pack_start(button, False, False, 0)
            self.category_buttons[cat_id] = button

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        scroller.set_shadow_type(Gtk.ShadowType.NONE)
        scroller.add(chips_box)
        self.pack_start(scroller, False, False, 0)

    def _build_list(self) -> None:
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.set_activate_on_single_click(True)
        self.list_box.get_style_context().add_class("card")
        self.list_box.connect("row-activated", self._on_row_activated)
        self.list_box.get_accessible().set_name("Glossary terms")

        scroller.add(self.list_box)
        self.pack_start(scroller, True, True, 0)

    def _build_row(self, term: Term) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.term_key = term.key  # type: ignore[attr-defined]

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        outer.set_margin_top(_SPACING.SM)
        outer.set_margin_bottom(_SPACING.SM)
        outer.set_margin_start(_SPACING.MD)
        outer.set_margin_end(_SPACING.MD)

        title_label = Gtk.Label()
        title_label.set_markup(f"<b>{GLib.markup_escape_text(term.title)}</b>")
        title_label.set_xalign(0.0)
        title_label.set_line_wrap(True)
        outer.pack_start(title_label, False, False, 0)

        summary_label = Gtk.Label(label=term.summary)
        summary_label.set_xalign(0.0)
        summary_label.set_line_wrap(True)
        summary_label.get_style_context().add_class("dim")
        outer.pack_start(summary_label, False, False, 0)

        # The body (long text + See-also links) is built on first expand: laying out
        # 120 of them up front made the page's first show take ~270 ms.
        revealer = Gtk.Revealer()
        revealer.set_reveal_child(False)
        outer.pack_start(revealer, False, False, 0)
        row.revealer = revealer  # type: ignore[attr-defined]
        row.term = term  # type: ignore[attr-defined]

        row.add(outer)
        return row

    def _build_body_box(self, term: Term) -> Gtk.Box:
        body_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=_SPACING.SM)
        body_box.set_margin_top(_SPACING.SM)

        body_label = Gtk.Label(label=term.body)
        body_label.set_xalign(0.0)
        body_label.set_line_wrap(True)
        body_box.pack_start(body_label, False, False, 0)

        if term.related:
            related_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=_SPACING.XS)
            see_also = Gtk.Label(label="See also:")
            see_also.get_style_context().add_class("dim")
            related_box.pack_start(see_also, False, False, 0)
            for related_key in term.related:
                related_term = glossary.get(related_key)
                if related_term is None:
                    continue
                link = Gtk.Button(label=related_term.title)
                link.get_style_context().add_class("flat")
                link.get_accessible().set_name(f"See also: {related_term.title}")
                link.connect("clicked", self._on_related_clicked, related_key)
                related_box.pack_start(link, False, False, 0)
            body_box.pack_start(related_box, False, False, 0)

        return body_box

    # ---- filtering ----------------------------------------------------------

    def _visible_terms(self) -> list[Term]:
        terms: list[Term]
        if self._current_query:
            terms = glossary.search(self._current_query)
        else:
            terms = list(glossary.TERMS)
        if self._current_category != "all":
            terms = [t for t in terms if t.category == self._current_category]
        return terms

    def _rebuild_rows(self) -> None:
        for child in list(self.list_box.get_children()):
            self.list_box.remove(child)
        self._rows_by_key = {}
        self._expanded_key = None

        terms = self._visible_terms()
        for term in terms:
            row = self._build_row(term)
            self.list_box.add(row)
            self._rows_by_key[term.key] = row
        self.list_box.show_all()

        count = len(terms)
        self.count_label.set_text(f"{count} term{'' if count == 1 else 's'}")

    # ---- signal handlers ------------------------------------------------------

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self._current_query = entry.get_text().strip()
        self._rebuild_rows()

    def _on_search_key_press(self, entry: Gtk.SearchEntry, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            entry.set_text("")
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            terms = self._visible_terms()
            if terms:
                self.show_term(terms[0].key)
            return True
        return False

    def _on_category_toggled(self, button: Gtk.ToggleButton, cat_id: str) -> None:
        if self._category_guard:
            return
        if not button.get_active():
            # Keep single-selection semantics: re-clicking the active chip
            # should not leave nothing selected.
            if cat_id == self._current_category:
                self._category_guard = True
                button.set_active(True)
                self._category_guard = False
            return

        self._category_guard = True
        for other_id, other_button in self.category_buttons.items():
            if other_id != cat_id:
                other_button.set_active(False)
        self._category_guard = False

        self._current_category = cat_id
        self._rebuild_rows()

    def _on_row_activated(self, _list_box: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        key = getattr(row, "term_key", None)
        if key is None:
            return
        self._toggle_row(key)

    def _on_related_clicked(self, _button: Gtk.Button, key: str) -> None:
        self.show_term(key)

    def _toggle_row(self, key: str) -> None:
        row = self._rows_by_key.get(key)
        if row is None:
            return
        revealer: Gtk.Revealer = row.revealer  # type: ignore[attr-defined]
        was_expanded = revealer.get_reveal_child()
        self._collapse_all()
        if not was_expanded:
            if revealer.get_child() is None:
                revealer.add(self._build_body_box(row.term))  # type: ignore[attr-defined]
                revealer.show_all()
            revealer.set_reveal_child(True)
            self._expanded_key = key

    def _collapse_all(self) -> None:
        for row in self._rows_by_key.values():
            row.revealer.set_reveal_child(False)  # type: ignore[attr-defined]
        self._expanded_key = None

    # ---- public API -----------------------------------------------------------

    def filter(self, query: str) -> None:
        """Apply a search filter, as if the user had typed it into the search box."""
        self.search_entry.set_text(query)
        self._current_query = query.strip()
        self._rebuild_rows()

    def show_term(self, key: str) -> None:
        """Reset filters, then expand the row for ``key`` (a no-op if unknown)."""
        term = glossary.get(key)
        if term is None:
            return

        self.search_entry.set_text("")
        self._current_query = ""
        self._category_guard = True
        for cat_id, button in self.category_buttons.items():
            button.set_active(cat_id == "all")
        self._category_guard = False
        self._current_category = "all"
        self._rebuild_rows()

        row = self._rows_by_key.get(key)
        if row is None:
            return
        self._collapse_all()
        row.revealer.set_reveal_child(True)  # type: ignore[attr-defined]
        self._expanded_key = key
        row.grab_focus()
