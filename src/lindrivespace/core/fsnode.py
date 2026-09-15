"""Directory node used by the scanner and the tree model.

Memory matters: a home directory scan easily has a million directories, so the
node keeps only aggregates plus a bounded ring of the largest files it contains
directly. Individual regular files are never stored as nodes.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterator
from typing import NamedTuple

# Flag bits stored in FsNode.flags
DENIED = 1  # os.scandir / stat raised PermissionError somewhere directly below
SYMLINK = 2  # the entry itself is a symlink (never followed)
MOUNTPOINT = 4  # st_dev differs from the scan root (crossed only when cross_mounts=True)
PARTIAL = 8  # scan was cancelled while this subtree was open
EXCLUDED = 16  # matched an exclusion rule; listed but not descended
ROOT = 32  # the scan root


class TopFile(NamedTuple):
    """One of the largest regular files directly inside a directory."""

    alloc: int
    size: int
    mtime: float
    name: str


class FsNode:
    """A directory in the scanned tree.

    ``size`` is the apparent size (sum of ``st_size``), ``alloc`` the allocated
    size (sum of ``st_blocks * 512``). Both include the whole subtree once
    :meth:`finalize` has run. ``files`` / ``dirs`` are recursive counts.
    """

    __slots__ = (
        "id",
        "name",
        "parent",
        "children",
        "size",
        "alloc",
        "files",
        "dirs",
        "mtime",
        "mtime_max",
        "flags",
        "_top",
        "top_limit",
        "_finalized",
    )

    def __init__(
        self,
        node_id: int,
        name: str,
        parent: FsNode | None = None,
        mtime: float = 0.0,
        flags: int = 0,
        top_limit: int | None = None,
    ) -> None:
        self.id = node_id
        self.name = name
        self.parent = parent
        self.children: list[FsNode] = []
        self.size = 0
        self.alloc = 0
        self.files = 0
        self.dirs = 0
        self.mtime = mtime
        self.mtime_max = mtime
        self.flags = flags
        self._top: list[TopFile] = []  # min-heap on alloc
        inherited = parent.top_limit if parent is not None else 50
        self.top_limit: int = inherited if top_limit is None else top_limit
        self._finalized = False
        if parent is not None:
            parent.children.append(self)

    # ---- building ---------------------------------------------------------

    def add_file(self, size: int, alloc: int, mtime: float, name: str, keep: bool = True) -> None:
        """Account for one regular file directly inside this directory.

        ``keep=False`` counts the file but keeps it out of the largest-files ring
        (the scanner passes it for files below ``ScanOptions.top_min_bytes``).
        """
        self.size += size
        self.alloc += alloc
        self.files += 1
        if mtime > self.mtime_max:
            self.mtime_max = mtime
        if self.top_limit <= 0 or not keep:
            return
        entry = TopFile(alloc, size, mtime, name)
        if len(self._top) < self.top_limit:
            heapq.heappush(self._top, entry)
        elif alloc > self._top[0].alloc:
            heapq.heapreplace(self._top, entry)

    def finalize(self) -> None:
        """Fold children into this node's totals and sort children largest first.

        Safe to call more than once; child totals must already be final.
        """
        size = self.size
        alloc = self.alloc
        files = self.files
        dirs = self.dirs
        mtime_max = self.mtime_max
        if self._finalized:
            # Re-finalize from scratch: subtract nothing, recompute from own files.
            # Own-file totals are what remains after removing child sums.
            for child in self.children:
                size -= child.size
                alloc -= child.alloc
                files -= child.files
                dirs -= child.dirs + 1
        for child in self.children:
            size += child.size
            alloc += child.alloc
            files += child.files
            dirs += child.dirs + 1
            if child.mtime_max > mtime_max:
                mtime_max = child.mtime_max
        self.size = size
        self.alloc = alloc
        self.files = files
        self.dirs = dirs
        self.mtime_max = mtime_max
        self.children.sort(key=lambda c: c.alloc, reverse=True)
        self._finalized = True

    # ---- reading ----------------------------------------------------------

    @property
    def finalized(self) -> bool:
        return self._finalized

    @property
    def denied(self) -> bool:
        return bool(self.flags & DENIED)

    @property
    def top_files(self) -> list[TopFile]:
        """Largest files directly in this directory, largest first."""
        return sorted(self._top, reverse=True)

    def path(self) -> str:
        """Absolute path, assuming the root node's name is an absolute path."""
        parts: list[str] = []
        node: FsNode | None = self
        while node is not None:
            parts.append(node.name)
            node = node.parent
        parts.reverse()
        root = parts[0]
        if len(parts) == 1:
            return root
        sep = "" if root.endswith("/") else "/"
        return root + sep + "/".join(parts[1:])

    def depth(self) -> int:
        d = 0
        node = self.parent
        while node is not None:
            d += 1
            node = node.parent
        return d

    def percent_of_parent(self, allocated: bool = True) -> float:
        """Share of the parent's total, 0–100. The root reports 100."""
        if self.parent is None:
            return 100.0
        total = self.parent.alloc if allocated else self.parent.size
        own = self.alloc if allocated else self.size
        if total <= 0:
            return 0.0
        return min(100.0, own * 100.0 / total)

    def walk(self) -> Iterator[FsNode]:
        """Pre-order traversal, iterative."""
        stack = [self]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.children))

    def find(self, node_id: int) -> FsNode | None:
        for node in self.walk():
            if node.id == node_id:
                return node
        return None

    def __repr__(self) -> str:
        return f"FsNode({self.id}, {self.name!r}, alloc={self.alloc}, files={self.files})"
