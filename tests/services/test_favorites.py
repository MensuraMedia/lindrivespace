"""Tests for lindrivespace.services.favorites. Headless: GObject only, no Gtk."""

from __future__ import annotations

from pathlib import Path

from lindrivespace.config.settings import Settings
from lindrivespace.services.favorites import FavoritesStore, get_store


def _store(isolated_xdg: Path) -> FavoritesStore:
    return FavoritesStore(Settings())


def test_add_persists_through_a_fresh_settings(isolated_xdg: Path, tmp_path: Path) -> None:
    folder = tmp_path / "Projects"
    folder.mkdir()
    store = _store(isolated_xdg)

    fav = store.add(str(folder))

    assert fav.path == str(folder)
    assert fav.label == "Projects"
    assert fav.is_dir is True
    assert fav.added  # non-empty timestamp

    reloaded = FavoritesStore(Settings())
    assert [f.path for f in reloaded.list()] == [str(folder)]
    assert reloaded.list()[0].label == "Projects"


def test_add_normalises_and_defaults_label_for_root(isolated_xdg: Path) -> None:
    store = _store(isolated_xdg)
    fav = store.add("/")
    assert fav.path == "/"
    assert fav.label == "/"


def test_add_custom_label(isolated_xdg: Path, tmp_path: Path) -> None:
    store = _store(isolated_xdg)
    fav = store.add(str(tmp_path), label="My stuff")
    assert fav.label == "My stuff"


def test_add_is_idempotent_for_duplicates(isolated_xdg: Path, tmp_path: Path) -> None:
    store = _store(isolated_xdg)
    store.add(str(tmp_path), label="First")
    again = store.add(str(tmp_path), label="Second")

    assert len(store.list()) == 1
    assert again.label == "First"  # first label wins; add() is a no-op on duplicates


def test_remove(isolated_xdg: Path, tmp_path: Path) -> None:
    store = _store(isolated_xdg)
    store.add(str(tmp_path))
    assert store.is_favorite(str(tmp_path)) is True

    store.remove(str(tmp_path))

    assert store.is_favorite(str(tmp_path)) is False
    assert store.list() == []
    # reload to confirm the removal itself persisted, not just in-memory state
    assert FavoritesStore(Settings()).list() == []


def test_toggle_returns_new_state(isolated_xdg: Path, tmp_path: Path) -> None:
    store = _store(isolated_xdg)

    assert store.toggle(str(tmp_path)) is True
    assert store.is_favorite(str(tmp_path)) is True

    assert store.toggle(str(tmp_path)) is False
    assert store.is_favorite(str(tmp_path)) is False


def test_rename_persists(isolated_xdg: Path, tmp_path: Path) -> None:
    store = _store(isolated_xdg)
    store.add(str(tmp_path), label="Old name")

    store.rename(str(tmp_path), "New name")

    assert store.get(str(tmp_path)).label == "New name"
    assert FavoritesStore(Settings()).get(str(tmp_path)).label == "New name"


def test_move_reorders_and_persists(isolated_xdg: Path, tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    c = tmp_path / "c"
    for d in (a, b, c):
        d.mkdir()
    store = _store(isolated_xdg)
    store.add(str(a))
    store.add(str(b))
    store.add(str(c))

    store.move(str(c), 0)

    assert [f.path for f in store.list()] == [str(c), str(a), str(b)]
    assert [f.path for f in FavoritesStore(Settings()).list()] == [str(c), str(a), str(b)]


def test_move_unknown_path_is_a_no_op(isolated_xdg: Path, tmp_path: Path) -> None:
    store = _store(isolated_xdg)
    store.add(str(tmp_path))
    store.move("/no/such/path", 0)
    assert [f.path for f in store.list()] == [str(tmp_path)]


def test_scan_target_folder_is_itself(isolated_xdg: Path, tmp_path: Path) -> None:
    store = _store(isolated_xdg)
    fav = store.add(str(tmp_path))
    assert fav.is_dir is True
    assert store.scan_target(fav) == str(tmp_path)


def test_scan_target_file_is_its_parent(isolated_xdg: Path, tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("hello")
    store = _store(isolated_xdg)
    fav = store.add(str(file_path))

    assert fav.is_dir is False
    assert store.scan_target(fav) == str(tmp_path)


def test_is_dir_reflects_current_filesystem_state_not_persisted(
    isolated_xdg: Path, tmp_path: Path
) -> None:
    folder = tmp_path / "goes-away"
    folder.mkdir()
    store = _store(isolated_xdg)
    fav = store.add(str(folder))
    assert fav.is_dir is True

    folder.rmdir()

    assert store.get(str(folder)).is_dir is False


def test_changed_signal_emitted_once_per_mutation(isolated_xdg: Path, tmp_path: Path) -> None:
    store = _store(isolated_xdg)
    counts: list[int] = []
    store.connect("changed", lambda _s: counts.append(1))

    store.add(str(tmp_path))
    assert len(counts) == 1

    store.rename(str(tmp_path), "renamed")
    assert len(counts) == 2

    store.toggle(str(tmp_path))  # removes
    assert len(counts) == 3

    store.add(str(tmp_path))  # duplicate-free add does mutate (adds again)
    assert len(counts) == 4

    store.add(str(tmp_path))  # now a true duplicate: no mutation, no signal
    assert len(counts) == 4


def test_get_store_caches_one_instance_on_the_app_object(isolated_xdg: Path) -> None:
    class _FakeApp:
        def __init__(self) -> None:
            self.settings = Settings()

    app = _FakeApp()
    store_a = get_store(app)
    store_b = get_store(app)

    assert store_a is store_b
    assert app.favorites_store is store_a  # type: ignore[attr-defined]
