"""File-type classification by extension, for the "File Types" insight (§3.3).

Pure stdlib. Classification is by filename extension only (no content sniffing)
since it must run fast over rings of :class:`~lindrivespace.core.fsnode.TopFile`
entries, not full file contents.
"""

from __future__ import annotations

from enum import Enum

from lindrivespace.core.fsnode import FsNode


class FileClass(str, Enum):
    VIDEO = "video"
    IMAGE = "image"
    AUDIO = "audio"
    ARCHIVE = "archive"
    PACKAGE = "package"
    DISK_IMAGE = "disk_image"
    DOCUMENT = "document"
    CODE = "code"
    DATA = "data"
    LOG = "log"
    CACHE = "cache"
    MODEL = "model"
    OTHER = "other"


_LABELS: dict[FileClass, str] = {
    FileClass.VIDEO: "Video",
    FileClass.IMAGE: "Image",
    FileClass.AUDIO: "Audio",
    FileClass.ARCHIVE: "Archives",
    FileClass.PACKAGE: "Packages",
    FileClass.DISK_IMAGE: "Disk images",
    FileClass.DOCUMENT: "Documents",
    FileClass.CODE: "Code",
    FileClass.DATA: "Data",
    FileClass.LOG: "Logs",
    FileClass.CACHE: "Cache/temp",
    FileClass.MODEL: "Models",
    FileClass.OTHER: "Other",
}

_DISPLAY_ORDER: tuple[FileClass, ...] = (
    FileClass.VIDEO,
    FileClass.IMAGE,
    FileClass.AUDIO,
    FileClass.DOCUMENT,
    FileClass.CODE,
    FileClass.DATA,
    FileClass.MODEL,
    FileClass.ARCHIVE,
    FileClass.PACKAGE,
    FileClass.DISK_IMAGE,
    FileClass.LOG,
    FileClass.CACHE,
    FileClass.OTHER,
)

# Multi-part extensions must be listed before their single-part suffix would
# otherwise match something else (".tar.gz" is checked before ".gz").
_MULTI_PART_EXTENSIONS: dict[str, FileClass] = {
    ".tar.gz": FileClass.ARCHIVE,
    ".tar.bz2": FileClass.ARCHIVE,
    ".tar.xz": FileClass.ARCHIVE,
    ".tar.zst": FileClass.ARCHIVE,
    ".tar.lz": FileClass.ARCHIVE,
    ".tar.lzma": FileClass.ARCHIVE,
}

_EXTENSIONS: dict[str, FileClass] = {
    # Video
    ".mp4": FileClass.VIDEO,
    ".mkv": FileClass.VIDEO,
    ".avi": FileClass.VIDEO,
    ".mov": FileClass.VIDEO,
    ".webm": FileClass.VIDEO,
    ".wmv": FileClass.VIDEO,
    ".flv": FileClass.VIDEO,
    ".m4v": FileClass.VIDEO,
    ".mpg": FileClass.VIDEO,
    ".mpeg": FileClass.VIDEO,
    ".3gp": FileClass.VIDEO,
    # Image
    ".jpg": FileClass.IMAGE,
    ".jpeg": FileClass.IMAGE,
    ".png": FileClass.IMAGE,
    ".gif": FileClass.IMAGE,
    ".bmp": FileClass.IMAGE,
    ".webp": FileClass.IMAGE,
    ".svg": FileClass.IMAGE,
    ".tif": FileClass.IMAGE,
    ".tiff": FileClass.IMAGE,
    ".heic": FileClass.IMAGE,
    ".raw": FileClass.IMAGE,
    ".ico": FileClass.IMAGE,
    ".psd": FileClass.IMAGE,
    ".xcf": FileClass.IMAGE,
    # Audio
    ".mp3": FileClass.AUDIO,
    ".flac": FileClass.AUDIO,
    ".wav": FileClass.AUDIO,
    ".ogg": FileClass.AUDIO,
    ".m4a": FileClass.AUDIO,
    ".aac": FileClass.AUDIO,
    ".wma": FileClass.AUDIO,
    ".opus": FileClass.AUDIO,
    ".aiff": FileClass.AUDIO,
    # Archive
    ".zip": FileClass.ARCHIVE,
    ".gz": FileClass.ARCHIVE,
    ".bz2": FileClass.ARCHIVE,
    ".xz": FileClass.ARCHIVE,
    ".7z": FileClass.ARCHIVE,
    ".rar": FileClass.ARCHIVE,
    ".tar": FileClass.ARCHIVE,
    ".zst": FileClass.ARCHIVE,
    ".lz": FileClass.ARCHIVE,
    ".lzma": FileClass.ARCHIVE,
    ".tgz": FileClass.ARCHIVE,
    ".tbz2": FileClass.ARCHIVE,
    # Package
    ".deb": FileClass.PACKAGE,
    ".rpm": FileClass.PACKAGE,
    ".snap": FileClass.PACKAGE,
    ".flatpak": FileClass.PACKAGE,
    ".flatpakref": FileClass.PACKAGE,
    ".whl": FileClass.PACKAGE,
    ".jar": FileClass.PACKAGE,
    ".apk": FileClass.PACKAGE,
    ".appimage": FileClass.PACKAGE,
    ".egg": FileClass.PACKAGE,
    ".gem": FileClass.PACKAGE,
    ".msi": FileClass.PACKAGE,
    # Disk image
    ".iso": FileClass.DISK_IMAGE,
    ".img": FileClass.DISK_IMAGE,
    ".qcow2": FileClass.DISK_IMAGE,
    ".vdi": FileClass.DISK_IMAGE,
    ".vmdk": FileClass.DISK_IMAGE,
    ".vhd": FileClass.DISK_IMAGE,
    ".vhdx": FileClass.DISK_IMAGE,
    ".dmg": FileClass.DISK_IMAGE,
    # Document
    ".pdf": FileClass.DOCUMENT,
    ".doc": FileClass.DOCUMENT,
    ".docx": FileClass.DOCUMENT,
    ".odt": FileClass.DOCUMENT,
    ".xls": FileClass.DOCUMENT,
    ".xlsx": FileClass.DOCUMENT,
    ".ods": FileClass.DOCUMENT,
    ".ppt": FileClass.DOCUMENT,
    ".pptx": FileClass.DOCUMENT,
    ".odp": FileClass.DOCUMENT,
    ".txt": FileClass.DOCUMENT,
    ".md": FileClass.DOCUMENT,
    ".rtf": FileClass.DOCUMENT,
    ".epub": FileClass.DOCUMENT,
    # Code
    ".py": FileClass.CODE,
    ".c": FileClass.CODE,
    ".h": FileClass.CODE,
    ".cpp": FileClass.CODE,
    ".hpp": FileClass.CODE,
    ".js": FileClass.CODE,
    ".ts": FileClass.CODE,
    ".java": FileClass.CODE,
    ".go": FileClass.CODE,
    ".rs": FileClass.CODE,
    ".sh": FileClass.CODE,
    ".rb": FileClass.CODE,
    ".php": FileClass.CODE,
    ".html": FileClass.CODE,
    ".css": FileClass.CODE,
    ".vala": FileClass.CODE,
    # Data
    ".json": FileClass.DATA,
    ".csv": FileClass.DATA,
    ".tsv": FileClass.DATA,
    ".sqlite": FileClass.DATA,
    ".sqlite3": FileClass.DATA,
    ".db": FileClass.DATA,
    ".parquet": FileClass.DATA,
    ".xml": FileClass.DATA,
    ".yaml": FileClass.DATA,
    ".yml": FileClass.DATA,
    ".toml": FileClass.DATA,
    ".ndjson": FileClass.DATA,
    # Log
    ".log": FileClass.LOG,
    ".log1": FileClass.LOG,
    ".out": FileClass.LOG,
    ".trace": FileClass.LOG,
    # Cache / temp
    ".tmp": FileClass.CACHE,
    ".temp": FileClass.CACHE,
    ".cache": FileClass.CACHE,
    ".part": FileClass.CACHE,
    ".partial": FileClass.CACHE,
    ".crdownload": FileClass.CACHE,
    ".download": FileClass.CACHE,
    ".bak": FileClass.CACHE,
    ".swp": FileClass.CACHE,
    ".lock": FileClass.CACHE,
    # Model
    ".safetensors": FileClass.MODEL,
    ".gguf": FileClass.MODEL,
    ".ckpt": FileClass.MODEL,
    ".pt": FileClass.MODEL,
    ".pth": FileClass.MODEL,
    ".onnx": FileClass.MODEL,
    ".bin": FileClass.MODEL,
    ".h5": FileClass.MODEL,
    ".weights": FileClass.MODEL,
}


def classify(name: str) -> FileClass:
    """Classify `name` by its extension, case-insensitively.

    Multi-part extensions such as ``.tar.gz`` are recognised before the final
    single-part suffix is tried. A name with no recognised extension (or no
    extension at all) is :attr:`FileClass.OTHER`.
    """
    lower = name.lower()
    for suffix, fc in _MULTI_PART_EXTENSIONS.items():
        if lower.endswith(suffix):
            return fc
    dot = lower.rfind(".")
    if dot <= 0:  # no extension, or a dotfile with no further suffix (".bashrc")
        return FileClass.OTHER
    ext = lower[dot:]
    return _EXTENSIONS.get(ext, FileClass.OTHER)


def class_label(fc: FileClass) -> str:
    """Human-readable label for `fc`, e.g. ``"Disk images"``."""
    return _LABELS[fc]


def class_order() -> tuple[FileClass, ...]:
    """Display order for the File Types insight."""
    return _DISPLAY_ORDER


def summarize_top_files(node: FsNode, recursive: bool = True) -> dict[FileClass, tuple[int, int]]:
    """Aggregate (count, alloc) by :class:`FileClass` over `node`'s top files.

    This is an ESTIMATE, not an exact total: :attr:`FsNode.top_files` only
    keeps the largest ``top_limit`` files directly inside each directory (a
    bounded ring, see ``core/fsnode.py``), so directories with more files than
    the ring size silently drop their smallest entries from this summary. When
    ``recursive`` is True the rings of every descendant (via :meth:`FsNode.walk`)
    are folded in as well, still subject to the same per-directory cap.
    """
    totals: dict[FileClass, tuple[int, int]] = {}

    def add(fc: FileClass, alloc: int) -> None:
        count, total_alloc = totals.get(fc, (0, 0))
        totals[fc] = (count + 1, total_alloc + alloc)

    nodes = node.walk() if recursive else (node,)
    for n in nodes:
        for top_file in n.top_files:
            add(classify(top_file.name), top_file.alloc)

    return totals
