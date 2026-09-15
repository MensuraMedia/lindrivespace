"""Tests for the pure-Python glossary content module (WP15)."""

from __future__ import annotations

from lindrivespace.core import glossary


def test_at_least_seventy_terms() -> None:
    assert len(glossary.TERMS) >= 70


def test_every_term_has_summary_and_body() -> None:
    for term in glossary.TERMS:
        assert term.summary.strip(), f"{term.key} has an empty summary"
        assert term.body.strip(), f"{term.key} has an empty body"


def test_keys_are_unique() -> None:
    keys = [t.key for t in glossary.TERMS]
    assert len(keys) == len(set(keys))


def test_every_related_key_exists() -> None:
    keys = {t.key for t in glossary.TERMS}
    for term in glossary.TERMS:
        for related_key in term.related:
            assert related_key in keys, f"{term.key} references unknown related key {related_key!r}"


def test_every_category_has_at_least_five_terms() -> None:
    counts = {cat_id: 0 for cat_id, _label in glossary.CATEGORIES}
    for term in glossary.TERMS:
        assert term.category in counts, f"{term.key} has unknown category {term.category!r}"
        counts[term.category] += 1
    for cat_id, count in counts.items():
        assert count >= 5, f"category {cat_id!r} only has {count} terms"


def test_by_category_filters_correctly() -> None:
    for cat_id, _label in glossary.CATEGORIES:
        terms = glossary.by_category(cat_id)
        assert terms, f"category {cat_id!r} is empty"
        assert all(t.category == cat_id for t in terms)


def test_get_returns_term_or_none() -> None:
    ext4 = glossary.get("ext4")
    assert ext4 is not None
    assert ext4.key == "ext4"
    assert glossary.get("does-not-exist") is None


def test_search_ext4_returns_ext4_first() -> None:
    results = glossary.search("ext4")
    assert results
    assert results[0].key == "ext4"


def test_search_folder_finds_directory_vs_folder() -> None:
    results = glossary.search("folder")
    keys = [t.key for t in results]
    assert "directory-vs-folder" in keys


def test_search_is_case_insensitive() -> None:
    assert [t.key for t in glossary.search("EXT4")] == [t.key for t in glossary.search("ext4")]


def test_search_empty_query_returns_nothing() -> None:
    assert glossary.search("") == []
    assert glossary.search("   ") == []


def test_ext4_mentions_extents_and_journal() -> None:
    ext4 = glossary.get("ext4")
    assert ext4 is not None
    assert "extents" in ext4.body
    assert "journal" in ext4.body


def test_mountpoint_mentions_directory() -> None:
    mountpoint = glossary.get("mountpoint")
    assert mountpoint is not None
    assert "directory" in mountpoint.body
