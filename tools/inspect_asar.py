#!/usr/bin/env python3
"""
Inspect a StarFinder .asar archive so we can write the fault->image indexer.

Usage:
  python3 tools/inspect_asar.py /path/to/164.asar              # summary + tree
  python3 tools/inspect_asar.py /path/to/164.asar --cat a/b.htm  # print one file

Send me the output of the first form (top of the tree + extension counts) and
one sample HTML page (the --cat of a wiring/diagram page) — that's enough to map
StarFinder pages/images to ECUs and fault codes.
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from mb import asar  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    path = sys.argv[1]
    files = asar.list_files(path)
    if "--cat" in sys.argv:
        inner = sys.argv[sys.argv.index("--cat") + 1]
        data = asar.read_file(path, inner)
        if data is None:
            print("not found:", inner)
        else:
            sys.stdout.write(data.decode("utf-8", "replace"))
        return

    total = sum(s for _, s in files.values())
    print(f"# {path}")
    print(f"files: {len(files)}   total: {total/1e6:.1f} MB\n")

    ext = Counter(Path(p).suffix.lower() or "(none)" for p in files)
    print("== extensions ==")
    for e, n in ext.most_common(20):
        print(f"  {n:>6}  {e}")

    # top-level folders
    tops = Counter(p.split("/")[1] for p in files if "/" in p[1:])
    print("\n== top-level folders ==")
    for d, n in tops.most_common(30):
        print(f"  {n:>6}  /{d}")

    print("\n== first 60 paths ==")
    for p in sorted(files)[:60]:
        print(" ", p)


if __name__ == "__main__":
    main()
