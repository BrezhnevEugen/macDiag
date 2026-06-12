#!/usr/bin/env python3
"""
Build a unified ECU database (SQLite) from a whole Vediamo CBF library.

Scans every .cbf in a directory (recursively), extracts metadata via
parse_cbf.parse_cbf(), and writes a queryable database. The macDiag backend then
pulls only the ECUs it needs (by name / chassis / protocol / search) instead of
loading the whole library.

Usage:
    python tools/build_ecu_db.py --dir "/path/to/VediamoData" \
                                 --out backend/mb/ecu_db.sqlite

Schema:
    ecu(name PK, file, protocol, template, size, bus_json)
    ecu_part(ecu, part)
    ecu_variant(ecu, variant)
    ecu_chassis(ecu, chassis)
    ecu_comparam(ecu, comparam)
    ecu_job(ecu, job)
    ecu_fts  -- FTS5 over name + jobs + parts for free-text search
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_cbf import parse_cbf  # noqa: E402
import caesar_comparam  # noqa: E402


def _extract_can(path: Path) -> dict:
    """Real CAN request/response/global ids + baudrate from the CBF comparams."""
    try:
        res = caesar_comparam.parse_file(path)
    except Exception:  # noqa: BLE001
        return {}
    for e in res.get("ecus", []):
        can = e.get("can", {})
        if can.get("CP_REQUEST_CANIDENTIFIER"):
            return {
                "can_request": can.get("CP_REQUEST_CANIDENTIFIER"),
                "can_response": can.get("CP_RESPONSE_CANIDENTIFIER"),
                "can_global": can.get("CP_GLOBAL_REQUEST_CANIDENTIFIER"),
                "baudrate": can.get("CP_BAUDRATE"),
            }
    return {}

SCHEMA = """
DROP TABLE IF EXISTS ecu;
DROP TABLE IF EXISTS ecu_part;
DROP TABLE IF EXISTS ecu_variant;
DROP TABLE IF EXISTS ecu_chassis;
DROP TABLE IF EXISTS ecu_comparam;
DROP TABLE IF EXISTS ecu_job;
DROP TABLE IF EXISTS ecu_fts;
CREATE TABLE ecu (
    name TEXT PRIMARY KEY, file TEXT, protocol TEXT, template TEXT,
    size INTEGER, bus_json TEXT,
    can_request INTEGER, can_response INTEGER, can_global INTEGER, baudrate INTEGER
);
CREATE TABLE ecu_part     (ecu TEXT, part TEXT);
CREATE TABLE ecu_variant  (ecu TEXT, variant TEXT);
CREATE TABLE ecu_chassis  (ecu TEXT, chassis TEXT);
CREATE TABLE ecu_comparam (ecu TEXT, comparam TEXT);
CREATE TABLE ecu_job      (ecu TEXT, job TEXT);
CREATE INDEX ix_chassis ON ecu_chassis(chassis);
CREATE INDEX ix_proto   ON ecu(protocol);
CREATE VIRTUAL TABLE ecu_fts USING fts5(name, jobs, parts);
"""


def build(src: Path, out: Path) -> int:
    files = sorted(src.rglob("*.cbf")) + sorted(src.rglob("*.CBF"))
    # de-dup by resolved path (case-insensitive globs can double on some FS)
    seen, uniq = set(), []
    for f in files:
        key = str(f).lower()
        if key not in seen:
            seen.add(key); uniq.append(f)

    out.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(out)
    db.executescript(SCHEMA)
    n = 0
    for f in uniq:
        try:
            e = parse_cbf(f)
        except Exception as ex:  # noqa: BLE001
            print(f"  skip {f.name}: {ex}", file=sys.stderr)
            continue
        name = e["ecu"]
        can = _extract_can(f)
        db.execute(
            "INSERT OR REPLACE INTO ecu VALUES (?,?,?,?,?,?,?,?,?,?)",
            (name, e["file"], e.get("protocol"), e.get("template"),
             e.get("size"), json.dumps(e.get("bus", {})),
             can.get("can_request"), can.get("can_response"),
             can.get("can_global"), can.get("baudrate")),
        )
        db.executemany("INSERT INTO ecu_part VALUES (?,?)",
                       [(name, p) for p in e.get("part_numbers", [])])
        db.executemany("INSERT INTO ecu_variant VALUES (?,?)",
                       [(name, v) for v in e.get("variants", [])])
        db.executemany("INSERT INTO ecu_chassis VALUES (?,?)",
                       [(name, c) for c in e.get("chassis", [])])
        db.executemany("INSERT INTO ecu_comparam VALUES (?,?)",
                       [(name, c) for c in e.get("comparams", [])])
        db.executemany("INSERT INTO ecu_job VALUES (?,?)",
                       [(name, j) for j in e.get("jobs", [])])
        db.execute("INSERT INTO ecu_fts VALUES (?,?,?)",
                   (name, " ".join(e.get("jobs", [])),
                    " ".join(e.get("part_numbers", []))))
        n += 1
    db.commit()
    db.close()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", default="backend/mb/ecu_db.sqlite")
    a = ap.parse_args()
    n = build(Path(a.dir), Path(a.out))
    print(f"built {a.out} with {n} ECUs")


if __name__ == "__main__":
    main()
