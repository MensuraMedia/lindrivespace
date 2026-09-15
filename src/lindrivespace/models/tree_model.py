"""Gtk.TreeStore adapter for a scan.

Design (see docs/CONCEPT-AND-TECHNICAL-DESIGN.md §6 and §16):

* The model rebuilds its own :class:`FsNode` tree from the scanner's pre-order
  events, so the UI never touches the worker's objects.
* The store holds only three columns — the node object, its name (for
  type-ahead search) and a dummy flag. Every displayed string, the percent
  value and the bold weight are computed **at draw time** through cell data
  functions (:meth:`cell_data_func`), so a batch of 10 000 events costs a few
  object appends, not 150 000 GValue conversions, and only the ~40 visible
  rows are ever formatted.
* Rows are **lazy**: a directory's children are inserted only when that row is
  *populated* — the root immediately, every other row on expand
  (``populate(iter)``). Un-populated rows with children carry one dummy child
  so the expander arrow shows.
* **GTK sorting is never enabled.** ``set_sort()`` reorders children with
  ``move_before`` (only rows outside a longest increasing subsequence move, so
  expansion state survives), or rebuilds a wide, un-expanded folder in O(n).
* Totals are **running** while a scan is in flight: a child's ``DirDone`` is
  pushed up every open ancestor at once, so percent bars stay live.
"""

from __future__ import annotations

import bisect
import time
from collections.abc import Callable, Iterable
from enum import IntEnum

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from lindrivespace.core import fsnode as fs  # noqa: E402
from lindrivespace.core.events import (  # noqa: E402
    DirDone,
    DirStarted,
    Finished,
    Progress,
    ScanError,
    ScanEvent,
)
from lindrivespace.core.fsnode import FsNode  # noqa: E402


class Col(IntEnum):
    """Store column indices."""

    NODE = 0  # FsNode (object) — None on the dummy row
    NAME = 1  # str — used by the tree view's interactive search
    IS_DUMMY = 2  # bool


COLUMN_TYPES = (object, str, bool)

# Display kinds understood by display()/cell_data_func(); also the persisted column ids.
DISPLAY_KINDS = (
    "name",
    "name_size",
    "size",
    "alloc",
    "files",
    "dirs",
    "percent",
    "modified",
    "owner",
    "type",
    "icon",
)
SORT_COLUMNS = ("name", "size", "alloc", "files", "dirs", "percent", "modified")

WEIGHT_NORMAL = 400
WEIGHT_MEDIUM = 500

ICON_FOLDER = "folder-symbolic"
ICON_ROOT = "drive-harddisk-symbolic"
ICON_DENIED = "changes-prevent-symbolic"
ICON_MOUNT = "drive-harddisk-symbolic"
ICON_EXCLUDED = "action-unavailable-symbolic"
ICON_PARTIAL = "dialog-warning-symbolic"


def _default_fmt_bytes(n: int) -> str:
    value = float(n)
    for unit in ("Bytes", "KB", "MB", "GB", "TB", "PB"):
        if value < 1000 or unit == "PB":
            if unit == "Bytes":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}" if unit in ("TB", "PB") else f"{value:.1f} {unit}"
        value /= 1000.0
    return f"{n} Bytes"


def _fmt_count(n: int) -> str:
    return f"{n:,}"


def _fmt_date(ts: float) -> str:
    if ts <= 0:
        return ""
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def icon_for(node: FsNode) -> str:
    flags = node.flags
    if flags & fs.DENIED:
        return ICON_DENIED
    if flags & fs.ROOT:
        return ICON_ROOT
    if flags & fs.MOUNTPOINT:
        return ICON_MOUNT
    if flags & fs.EXCLUDED:
        return ICON_EXCLUDED
    if flags & fs.PARTIAL:
        return ICON_PARTIAL
    return ICON_FOLDER


def _lis_indices(seq: list[int]) -> list[int]:
    """Indices of one longest strictly increasing subsequence of ``seq``."""
    if not seq:
        return []
    tails: list[int] = []
    tails_idx: list[int] = []
    prev = [-1] * len(seq)
    for i, value in enumerate(seq):
        pos = bisect.bisect_left(tails, value)
        if pos == len(tails):
            tails.append(value)
            tails_idx.append(i)
        else:
            tails[pos] = value
            tails_idx[pos] = i
        prev[i] = tails_idx[pos - 1] if pos > 0 else -1
    out: list[int] = []
    k = tails_idx[-1]
    while k != -1:
        out.append(k)
        k = prev[k]
    out.reverse()
    return out


class ScanTreeModel:
    """Owns a ``Gtk.TreeStore`` and the FsNode tree behind it."""

    LIVE_RESORT_MAX_CHILDREN = 500  # during a scan, wider folders are sorted when it ends
    LIVE_RESORT_INTERVAL = 0.25  # seconds between live re-sorts of the same folder
    REBUILD_THRESHOLD = 200  # out-of-place rows before a remove/re-append rebuild

    def __init__(
        self,
        *,
        fmt_bytes: Callable[[int], str] | None = None,
        allocated_primary: bool = True,
        top_n_bold: int = 3,
    ) -> None:
        self.store = Gtk.TreeStore(*COLUMN_TYPES)
        self.fmt_bytes: Callable[[int], str] = fmt_bytes or _default_fmt_bytes
        self.allocated_primary = allocated_primary
        self.top_n_bold = top_n_bold
        self.sort_column = "alloc"
        self.sort_descending = True

        self.root: FsNode | None = None
        self.nodes: dict[int, FsNode] = {}
        self.iters: dict[int, Gtk.TreeIter] = {}  # rows present in the store, by node id
        self.populated: set[int] = set()  # node ids whose children are in the store
        self._dirty_parents: set[int] = set()
        self._deferred_parents: set[int] = set()
        self._last_resort: dict[int, float] = {}
        self._bold_cache: dict[int, frozenset[int]] = {}
        self.entries = 0
        self.scanning = False
        self.errors: list[ScanError] = []
        self.version = 0  # bumped on every flush; views redraw when it changes

    # ------------------------------------------------------------------ reset

    def reset(self) -> None:
        self.store.clear()
        self.root = None
        self.nodes.clear()
        self.iters.clear()
        self.populated.clear()
        self._dirty_parents.clear()
        self._deferred_parents.clear()
        self._last_resort.clear()
        self._bold_cache.clear()
        self.entries = 0
        self.scanning = False
        self.errors.clear()
        self.version += 1

    # ----------------------------------------------------------------- events

    def apply(self, event: ScanEvent) -> None:
        """Apply one scanner event. Call :meth:`flush` after a batch."""
        if isinstance(event, DirStarted):
            self._on_started(event)
        elif isinstance(event, DirDone):
            self._on_done(event)
        elif isinstance(event, Progress):
            self.entries = event.entries
        elif isinstance(event, Finished):
            self.scanning = False
            self.entries = event.entries
            self._dirty_parents.update(self.populated)
            self._dirty_parents.update(self._deferred_parents)
            self._deferred_parents.clear()
            self._last_resort.clear()
        elif isinstance(event, ScanError):
            if len(self.errors) < 200:
                self.errors.append(event)

    def apply_many(self, events: Iterable[ScanEvent]) -> None:
        for event in events:
            self.apply(event)
        self.flush()

    def _on_started(self, ev: DirStarted) -> None:
        parent = self.nodes.get(ev.parent_id) if ev.parent_id is not None else None
        node = FsNode(ev.id, ev.name, parent, mtime=ev.mtime, flags=ev.flags, top_limit=0)
        self.nodes[ev.id] = node
        if parent is None:
            if self.root is not None:
                self.reset()
                self.nodes[ev.id] = node
            self.root = node
            self.scanning = True
            self.iters[ev.id] = self.store.append(None, [node, node.name, False])
            self.populated.add(ev.id)  # the root is always populated
            return
        ancestor: FsNode | None = parent
        while ancestor is not None and not ancestor.finalized:
            ancestor.dirs += 1
            ancestor = ancestor.parent
        if parent.id in self.populated:
            # prepend: O(1) in GtkTreeStore (append walks to the last sibling). The
            # row lands in sorted position at the next flush anyway.
            self.iters[ev.id] = self.store.prepend(self.iters[parent.id], [node, node.name, False])
            self._dirty_parents.add(parent.id)
        else:
            self._ensure_dummy(parent)

    def _on_done(self, ev: DirDone) -> None:
        node = self.nodes.get(ev.id)
        if node is None:
            return
        d_size = ev.size - node.size
        d_alloc = ev.alloc - node.alloc
        d_files = ev.files - node.files
        d_dirs = ev.dirs - node.dirs
        node.size, node.alloc, node.files, node.dirs = ev.size, ev.alloc, ev.files, ev.dirs
        node.mtime_max = max(node.mtime_max, ev.mtime_max)
        node.flags |= ev.flags
        node.top_limit = max(node.top_limit, len(ev.top_files))
        node._top = list(ev.top_files)  # noqa: SLF001 - restore the ring verbatim
        node._finalized = True  # noqa: SLF001 - totals are final (from the scanner)
        ancestor = node.parent
        while ancestor is not None and not ancestor.finalized:
            ancestor.size += d_size
            ancestor.alloc += d_alloc
            ancestor.files += d_files
            ancestor.dirs += d_dirs
            if ev.mtime_max > ancestor.mtime_max:
                ancestor.mtime_max = ev.mtime_max
            self._dirty_parents.add(ancestor.id)
            ancestor = ancestor.parent
        if node.parent is not None:
            self._dirty_parents.add(node.parent.id)
        self._dirty_parents.add(node.id)

    # ------------------------------------------------------------------ flush

    def flush(self) -> None:
        """Re-sort children of parents touched since the last flush and bump ``version``."""
        now = time.monotonic()
        for parent_id in list(self._dirty_parents):
            self._bold_cache.pop(parent_id, None)
            if parent_id not in self.populated:
                self._dirty_parents.discard(parent_id)
                continue
            if self.scanning:
                last = self._last_resort.get(parent_id, 0.0)
                if now - last < self.LIVE_RESORT_INTERVAL:
                    continue  # stays dirty; retried on a later flush
                self._last_resort[parent_id] = now
            self._resort_children(parent_id)
            self._dirty_parents.discard(parent_id)
        self.version += 1

    # --------------------------------------------------------------- populate

    def populate(self, it: Gtk.TreeIter) -> None:
        """Insert the children of the row at ``it`` (call from ``row-expanded``)."""
        node = self.node_for_iter(it)
        if node is None or node.id in self.populated:
            return
        self.populated.add(node.id)
        child = self.store.iter_children(it)
        while child is not None:
            if self.store.get_value(child, Col.IS_DUMMY):
                nxt = self.store.iter_next(child)
                self.store.remove(child)
                child = nxt
            else:
                child = self.store.iter_next(child)
        store = self.store
        for c in reversed(self._sorted(node.children)):  # prepend keeps O(1) per row
            cit = store.prepend(it, [c, c.name, False])
            self.iters[c.id] = cit
            if c.children:
                store.prepend(cit, [None, "…", True])
        self.version += 1

    def _ensure_dummy(self, parent: FsNode) -> None:
        pit = self.iters.get(parent.id)
        if pit is None or self.store.iter_has_child(pit):
            return
        self.store.append(pit, [None, "…", True])

    # ----------------------------------------------------------------- sorting

    def set_sort(self, column: str, descending: bool) -> None:
        if column not in SORT_COLUMNS:
            raise ValueError(f"not a sortable column: {column}")
        self.sort_column, self.sort_descending = column, descending
        for parent_id in list(self.populated):
            self._resort_children(parent_id, force=True)
        self.version += 1

    def set_primary(self, allocated: bool) -> None:
        self.allocated_primary = allocated
        self._bold_cache.clear()
        for parent_id in list(self.populated):
            self._resort_children(parent_id, force=True)
        self.version += 1

    def _sort_key(self) -> Callable[[FsNode], object]:
        col = self.sort_column
        if col == "name":
            return lambda n: n.name.casefold()
        if col == "size":
            return lambda n: n.size
        if col in ("alloc", "percent"):
            return (lambda n: n.alloc) if self.allocated_primary else (lambda n: n.size)
        if col == "files":
            return lambda n: n.files
        if col == "dirs":
            return lambda n: n.dirs
        return lambda n: n.mtime_max  # modified

    def _sorted(self, children: list[FsNode]) -> list[FsNode]:
        return sorted(children, key=self._sort_key(), reverse=self.sort_descending)

    def _resort_children(self, parent_id: int, force: bool = False) -> None:
        parent = self.nodes.get(parent_id)
        pit = self.iters.get(parent_id)
        if parent is None or pit is None or not parent.children:
            return
        store = self.store
        n = store.iter_n_children(pit)
        if self.scanning and not force and n > self.LIVE_RESORT_MAX_CHILDREN:
            self._deferred_parents.add(parent_id)
            return
        current: list[tuple[int, Gtk.TreeIter]] = []
        child = store.iter_children(pit)
        while child is not None:
            node = store.get_value(child, Col.NODE)
            current.append((node.id if node is not None else -1, child))
            child = store.iter_next(child)
        if not current:
            return
        current_ids = [cid for cid, _ in current]
        present = set(current_ids)
        wanted = [c.id for c in self._sorted(parent.children) if c.id in present]
        wanted += [cid for cid in current_ids if cid == -1]  # dummy rows stay last
        if wanted == current_ids:
            return
        iters = dict(current)
        rank = {cid: i for i, cid in enumerate(wanted)}
        seq = [rank[cid] for cid in current_ids]
        keep = _lis_indices(seq)
        moving = len(seq) - len(keep)
        has_populated = any(cid in self.populated for cid in current_ids if cid != -1)
        if moving > self.REBUILD_THRESHOLD and not has_populated:
            self._rebuild_children(pit, wanted)
            return
        keep_positions = {seq[i] for i in keep}
        next_kept: list[Gtk.TreeIter | None] = [None] * (len(wanted) + 1)
        for idx in range(len(wanted) - 1, -1, -1):
            next_kept[idx] = iters[wanted[idx]] if idx in keep_positions else next_kept[idx + 1]
        for idx, cid in enumerate(wanted):
            if idx in keep_positions:
                continue
            store.move_before(iters[cid], next_kept[idx + 1])

    def _rebuild_children(self, pit: Gtk.TreeIter, wanted: list[int]) -> None:
        """Remove and re-append all child rows in ``wanted`` order.

        Only used when no child row is populated, so no expansion state is lost.
        """
        store = self.store
        child = store.iter_children(pit)
        while child is not None:
            node = store.get_value(child, Col.NODE)
            if node is not None:
                self.iters.pop(node.id, None)
            nxt = store.iter_next(child)
            store.remove(child)
            child = nxt
        for cid in reversed(wanted):
            if cid == -1:
                continue
            node = self.nodes[cid]
            it = store.prepend(pit, [node, node.name, False])
            self.iters[cid] = it
            if node.children:
                store.prepend(it, [None, "…", True])

    # ---------------------------------------------------------------- display

    def primary(self, node: FsNode) -> int:
        return node.alloc if self.allocated_primary else node.size

    def percent(self, node: FsNode) -> float:
        return node.percent_of_parent(self.allocated_primary)

    def is_bold(self, node: FsNode) -> bool:
        parent = node.parent
        if parent is None:
            return True
        bold = self._bold_cache.get(parent.id)
        if bold is None:
            ranked = sorted(parent.children, key=self.primary, reverse=True)
            bold = frozenset(c.id for c in ranked[: self.top_n_bold] if self.primary(c) > 0)
            self._bold_cache[parent.id] = bold
        return node.id in bold

    def weight(self, node: FsNode) -> int:
        return WEIGHT_MEDIUM if self.is_bold(node) else WEIGHT_NORMAL

    def display(self, node: FsNode, kind: str) -> str:
        """Formatted text for a column kind."""
        if kind == "name":
            return node.name
        if kind == "name_size":
            return self.fmt_bytes(self.primary(node))
        if kind == "size":
            return self.fmt_bytes(node.size)
        if kind == "alloc":
            return self.fmt_bytes(node.alloc)
        if kind == "files":
            return "—" if node.denied else _fmt_count(node.files)
        if kind == "dirs":
            return "—" if node.denied else _fmt_count(node.dirs)
        if kind == "percent":
            return f"{self.percent(node):.1f} %"
        if kind == "modified":
            return _fmt_date(node.mtime_max)
        if kind == "icon":
            return icon_for(node)
        if kind in ("owner", "type"):
            return ""
        raise ValueError(f"unknown display kind: {kind}")

    def cell_data_func(
        self, kind: str
    ) -> Callable[
        [Gtk.TreeViewColumn, Gtk.CellRenderer, Gtk.TreeModel, Gtk.TreeIter, object], None
    ]:
        """A ``set_cell_data_func`` callback that fills a renderer from the node.

        ``kind`` is one of DISPLAY_KINDS. Text renderers get ``text`` and
        ``weight``; ``icon`` sets ``icon-name``; ``percent`` sets ``percent``
        and ``text`` on the percent-bar renderer (or ``text`` on a text one).
        """
        if kind not in DISPLAY_KINDS:
            raise ValueError(f"unknown display kind: {kind}")

        def func(
            _column: Gtk.TreeViewColumn,
            cell: Gtk.CellRenderer,
            model: Gtk.TreeModel,
            it: Gtk.TreeIter,
            _data: object,
        ) -> None:
            node = model.get_value(it, Col.NODE)
            has_percent = cell.find_property("percent") is not None
            if node is None:  # dummy row
                if kind == "icon":
                    cell.set_property("icon-name", "")
                elif kind == "percent" and has_percent:
                    cell.set_property("percent", 0.0)
                    cell.set_property("text", "")
                else:
                    cell.set_property("text", "…" if kind == "name" else "")
                return
            if kind == "icon":
                cell.set_property("icon-name", icon_for(node))
                return
            if kind == "percent" and has_percent:
                cell.set_property("percent", self.percent(node))
                cell.set_property("text", self.display(node, "percent"))
                return
            cell.set_property("text", self.display(node, kind))
            if cell.find_property("weight") is not None:
                cell.set_property("weight", self.weight(node))

        return func

    # -------------------------------------------------------------- lookups

    def node_for_iter(self, it: Gtk.TreeIter) -> FsNode | None:
        value = self.store.get_value(it, Col.NODE)
        return value if isinstance(value, FsNode) else None

    def node_for_path(self, path: Gtk.TreePath) -> FsNode | None:
        return self.node_for_iter(self.store.get_iter(path))

    def iter_for_node(self, node: FsNode) -> Gtk.TreeIter | None:
        return self.iters.get(node.id)

    def reveal(self, node: FsNode) -> Gtk.TreeIter | None:
        """Populate every ancestor so ``node`` has a row; return its iter."""
        chain: list[FsNode] = []
        cur: FsNode | None = node
        while cur is not None:
            chain.append(cur)
            cur = cur.parent
        chain.reverse()
        for ancestor in chain[:-1]:
            it = self.iters.get(ancestor.id)
            if it is None:
                return None
            self.populate(it)
        return self.iters.get(node.id)

    def is_dummy(self, it: Gtk.TreeIter) -> bool:
        return bool(self.store.get_value(it, Col.IS_DUMMY))
