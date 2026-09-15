"""GlossaryPage tests (WP15) -- uses the shared session-scoped ``window``
fixture from ``tests/ui/conftest.py`` (see its docstring: never build a
second ``Gtk.Application`` in this process).

Every test resets the page's filters (via ``page.filter("")`` /
``page.show_term`` reset behaviour, or an explicit teardown) since ``window``
is shared with every other module in the session.
"""

from __future__ import annotations

import gi
import pytest

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from lindrivespace.core import glossary  # noqa: E402


def _pump() -> None:
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)


@pytest.fixture
def page(window):  # type: ignore[no-untyped-def]
    window.show_page("glossary")
    glossary_page = window.pages["glossary"]
    # Reset any filtering left by a previous test in this session.
    glossary_page.filter("")
    glossary_page.category_buttons["all"].set_active(True)
    _pump()
    yield glossary_page
    glossary_page.filter("")
    _pump()


def test_rows_count_equals_all_terms_initially(page) -> None:  # type: ignore[no-untyped-def]
    assert len(page.list_box.get_children()) == len(glossary.TERMS)
    assert page.count_label.get_text() == f"{len(glossary.TERMS)} terms"


def test_filter_by_mountpoint_reduces_rows_and_orders_mountpoint_first(page) -> None:  # type: ignore[no-untyped-def]
    page.filter("mountpoint")
    _pump()
    rows = page.list_box.get_children()
    assert 0 < len(rows) < len(glossary.TERMS)
    first_row = rows[0]
    assert first_row.term_key == "mountpoint"


def test_filter_is_case_insensitive(page) -> None:  # type: ignore[no-untyped-def]
    page.filter("EXT4")
    _pump()
    rows = page.list_box.get_children()
    assert rows
    assert rows[0].term_key == "ext4"


def test_empty_filter_shows_all_terms_again(page) -> None:  # type: ignore[no-untyped-def]
    page.filter("mountpoint")
    _pump()
    page.filter("")
    _pump()
    assert len(page.list_box.get_children()) == len(glossary.TERMS)


def test_category_chip_filters_to_that_category(page) -> None:  # type: ignore[no-untyped-def]
    cat_id, _label = glossary.CATEGORIES[0]
    page.category_buttons[cat_id].set_active(True)
    _pump()
    rows = page.list_box.get_children()
    expected = len(glossary.by_category(cat_id))
    assert len(rows) == expected
    assert all(row.term_key in {t.key for t in glossary.by_category(cat_id)} for row in rows)

    page.category_buttons["all"].set_active(True)
    _pump()
    assert len(page.list_box.get_children()) == len(glossary.TERMS)


def test_show_term_expands_that_row(page) -> None:  # type: ignore[no-untyped-def]
    page.show_term("ext4")
    _pump()
    row = page.list_box.get_children()[
        [r.term_key for r in page.list_box.get_children()].index("ext4")
    ]
    assert row.revealer.get_reveal_child() is True
    # every other row stays collapsed
    for other in page.list_box.get_children():
        if other.term_key != "ext4":
            assert other.revealer.get_reveal_child() is False


def test_show_term_unknown_key_is_a_no_op(page) -> None:  # type: ignore[no-untyped-def]
    before = len(page.list_box.get_children())
    page.show_term("does-not-exist")
    _pump()
    assert len(page.list_box.get_children()) == before


def test_activating_a_row_toggles_its_revealer(page) -> None:  # type: ignore[no-untyped-def]
    row = page.list_box.get_children()[0]
    assert row.revealer.get_reveal_child() is False
    page.list_box.emit("row-activated", row)
    _pump()
    assert row.revealer.get_reveal_child() is True
    page.list_box.emit("row-activated", row)
    _pump()
    assert row.revealer.get_reveal_child() is False


def test_sidebar_has_glossary_button(window) -> None:  # type: ignore[no-untyped-def]
    assert "glossary" in window.sidebar.buttons
    window.sidebar.buttons["glossary"].clicked()
    assert window.current_page_id == "glossary"


def test_glossary_bodies_are_built_on_first_expand(window) -> None:  # type: ignore[no-untyped-def]
    window.show_page("glossary")
    page = window.pages["glossary"]
    key, row = next(iter(page._rows_by_key.items()))
    assert row.revealer.get_child() is None  # nothing built up front
    page._toggle_row(key)
    assert row.revealer.get_child() is not None and row.revealer.get_reveal_child()
    page._toggle_row(key)
    assert not row.revealer.get_reveal_child()
