from __future__ import annotations

from lindrivespace.core.classify import (
    FileClass,
    class_label,
    class_order,
    classify,
    summarize_top_files,
)
from lindrivespace.core.fsnode import FsNode

REPRESENTATIVE = {
    "movie.mp4": FileClass.VIDEO,
    "clip.MKV": FileClass.VIDEO,
    "photo.jpg": FileClass.IMAGE,
    "photo.PNG": FileClass.IMAGE,
    "song.mp3": FileClass.AUDIO,
    "track.flac": FileClass.AUDIO,
    "backup.zip": FileClass.ARCHIVE,
    "data.tar.gz": FileClass.ARCHIVE,
    "app.deb": FileClass.PACKAGE,
    "app.rpm": FileClass.PACKAGE,
    "vm.iso": FileClass.DISK_IMAGE,
    "disk.qcow2": FileClass.DISK_IMAGE,
    "report.pdf": FileClass.DOCUMENT,
    "notes.docx": FileClass.DOCUMENT,
    "main.py": FileClass.CODE,
    "app.ts": FileClass.CODE,
    "export.csv": FileClass.DATA,
    "state.sqlite": FileClass.DATA,
    "server.log": FileClass.LOG,
    "download.crdownload": FileClass.CACHE,
    "weights.safetensors": FileClass.MODEL,
    "model.gguf": FileClass.MODEL,
    "unknown.xyz123": FileClass.OTHER,
    "Makefile": FileClass.OTHER,
    ".bashrc": FileClass.OTHER,
}


def test_classify_representative_names() -> None:
    for name, expected in REPRESENTATIVE.items():
        assert classify(name) == expected, f"{name} classified as {classify(name)}"


def test_classify_multi_part_extensions() -> None:
    assert classify("archive.tar.gz") == FileClass.ARCHIVE
    assert classify("archive.tar.bz2") == FileClass.ARCHIVE
    assert classify("archive.tar.xz") == FileClass.ARCHIVE
    # A single ".gz" (not preceded by ".tar") still classifies as archive.
    assert classify("plain.gz") == FileClass.ARCHIVE


def test_classify_case_insensitive() -> None:
    assert classify("VIDEO.MP4") == FileClass.VIDEO
    assert classify("Video.Mp4") == FileClass.VIDEO
    assert classify("ARCHIVE.TAR.GZ") == FileClass.ARCHIVE


def test_classify_no_extension() -> None:
    assert classify("README") == FileClass.OTHER
    assert classify("LICENSE") == FileClass.OTHER


def test_class_label_and_order() -> None:
    for fc in FileClass:
        label = class_label(fc)
        assert isinstance(label, str) and label
    order = class_order()
    assert set(order) == set(FileClass)
    assert len(order) == len(set(order))


def _build_tree() -> FsNode:
    root = FsNode(1, "/data", top_limit=10)
    sub = FsNode(2, "sub", root, mtime=1.0)
    root.add_file(100, 4096, 1.0, "video.mp4")
    root.add_file(200, 4096, 2.0, "photo.jpg")
    sub.add_file(300, 4096, 3.0, "song.mp3")
    sub.add_file(400, 4096, 4.0, "clip.mp4")
    sub.finalize()
    root.finalize()
    return root


def test_summarize_top_files_non_recursive() -> None:
    root = _build_tree()
    summary = summarize_top_files(root, recursive=False)
    assert summary[FileClass.VIDEO] == (1, 4096)
    assert summary[FileClass.IMAGE] == (1, 4096)
    assert FileClass.AUDIO not in summary


def test_summarize_top_files_recursive() -> None:
    root = _build_tree()
    summary = summarize_top_files(root, recursive=True)
    assert summary[FileClass.VIDEO] == (2, 8192)
    assert summary[FileClass.IMAGE] == (1, 4096)
    assert summary[FileClass.AUDIO] == (1, 4096)
