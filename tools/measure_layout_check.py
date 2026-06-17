#!/usr/bin/env python3
"""Validate CBF output-field widths against the layout's own geometry.

The Caesar output-field layout record carries no usable field width (the dword
we once read as bit_len is a constant 0x10). The real width must come from the
presentation-derived byte_len. We can check that purely from the CBF: within one
DiagService request (one DID), the byte offset of the next field should sit
exactly byte_len bytes after the current one. If byte_len is the true on-wire
width, consecutive gaps equal byte_len; bit_len's constant 16 would not.
"""

from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "measurements.sqlite"

SCALAR_TYPES = ("ubyte", "uword", "ulong", "sbyte", "sword", "slong")


def stride_consistency(rows, min_fields: int = 4) -> tuple[int, int, int]:
    """Count consecutive fields whose gap to the next field equals their width.

    rows: iterable of (group_key, byte_offset, byte_len). Fields are grouped by
    key (one DID), and only clean groups are scored: strictly distinct offsets
    and at least ``min_fields`` fields (overlapping/aliased reads are skipped so
    they cannot mask a genuine width regression).

    Returns (match, total, groups_scored).
    """
    groups: dict[object, list[tuple[int, int]]] = defaultdict(list)
    for key, offset, width in rows:
        groups[key].append((int(offset), int(width)))

    match = total = scored = 0
    for fields in groups.values():
        if len(fields) < min_fields:
            continue
        fields.sort()
        offsets = [o for o, _ in fields]
        if len(set(offsets)) != len(offsets):
            continue
        scored += 1
        for i in range(len(fields) - 1):
            gap = fields[i + 1][0] - fields[i][0]
            if gap <= 0:
                continue
            total += 1
            if gap == fields[i][1]:
                match += 1
    return match, total, scored


def _table_exists(db: sqlite3.Connection, table: str) -> bool:
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table,),
    ).fetchone() is not None


def stride_rows(db_path: Path) -> list[tuple[str, int, int]]:
    """Pull (group_key, byte_offset, byte_len) for byte-aligned scalar outputs."""
    placeholders = ",".join("?" for _ in SCALAR_TYPES)
    with sqlite3.connect(db_path) as db:
        if not (_table_exists(db, "service_outputs")
                and _table_exists(db, "diag_services")):
            return []
        return [
            (f"{ecu}|{did}", bit_pos // 8, byte_len)
            for ecu, did, bit_pos, byte_len in db.execute(
                f"""
                SELECT so.ecu, ds.request_hex, so.bit_pos, so.byte_len
                FROM service_outputs AS so
                JOIN diag_services AS ds
                  ON ds.ecu = so.ecu AND ds.qualifier = so.qualifier
                WHERE so.bit_offset = 0
                  AND so.byte_len IN (1, 2, 4)
                  AND so.raw_type IN ({placeholders})
                ORDER BY so.ecu, ds.request_hex, so.bit_pos
                """,
                SCALAR_TYPES,
            )
        ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(DEFAULT_DB), help="measurements.sqlite path")
    args = ap.parse_args(argv)

    rows = stride_rows(Path(args.db))
    match, total, scored = stride_consistency(rows)
    if not total:
        print("no scorable scalar fields found")
        return 1
    print(f"clean sequential DIDs scored: {scored}")
    print(f"consecutive gap == byte_len:  {match}/{total} = {100 * match / total:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
