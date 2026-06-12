"""
Minimal pure-Python reader for Electron `.asar` archives (StarFinder data).

An .asar is a Chromium Pickle: four little-endian uint32, then a JSON header
describing the file tree (each leaf has byte offset + size), then the raw file
bytes concatenated. We read only the header + the one requested file, so opening
a 230 MB chassis archive to fetch a single image is cheap.

No external dependencies, no extraction step — the StarFinder provider reads
images straight out of `<chassis>.asar`.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path


def _open_header(f) -> tuple[dict, int]:
    a, hdr_size, c, json_len = struct.unpack("<4I", f.read(16))
    header = json.loads(f.read(json_len).decode("utf-8", "replace"))
    base = (8 + hdr_size + 3) & ~3   # file region starts after the header pickle, 4-aligned
    return header, base


def _walk(node: dict, prefix: str = "") -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for name, meta in node.get("files", {}).items():
        p = f"{prefix}/{name}"
        if "files" in meta:
            out.update(_walk(meta, p))
        elif "offset" in meta:
            out[p] = (int(meta["offset"]), int(meta["size"]))
    return out


def list_files(path: str | Path) -> dict[str, tuple[int, int]]:
    """inner path ('/a/b.htm') -> (offset, size) for every file in the archive."""
    with open(path, "rb") as f:
        header, _ = _open_header(f)
    return _walk(header)


def read_file(path: str | Path, inner: str) -> bytes | None:
    """Return the bytes of one file inside the archive, or None if absent."""
    key = inner if inner.startswith("/") else "/" + inner
    with open(path, "rb") as f:
        header, base = _open_header(f)
        files = _walk(header)
        hit = files.get(key)
        if not hit:
            return None
        off, size = hit
        f.seek(base + off)
        return f.read(size)


def exists(path: str | Path, inner: str) -> bool:
    key = inner if inner.startswith("/") else "/" + inner
    return key in list_files(path)


def iter_files(path: str | Path, prefix: str = ""):
    """Yield (inner_path, bytes) for every file under `prefix`, parsing the
    header once (cheap bulk scan of a big archive)."""
    with open(path, "rb") as f:
        header, base = _open_header(f)
        for inner, (off, size) in _walk(header).items():
            if inner.startswith(prefix):
                f.seek(base + off)
                yield inner, f.read(size)
