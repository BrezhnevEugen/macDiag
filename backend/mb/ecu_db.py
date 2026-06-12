"""
Read-only access to the unified ECU database (ecu_db.sqlite).

The DB is built offline by tools/build_ecu_db.py from the whole Vediamo CBF
library. The backend pulls only what it needs on demand: lookup by ECU name,
filter by chassis/protocol, or free-text search. If the DB file is missing the
functions degrade gracefully (return empty), so the app still runs on the
bundled simulator.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

# Path is env-overridable so the database can live in a mounted data volume
# (Docker) and be extended/rebuilt without touching the image.
_DEF_DB = Path(__file__).resolve().parent.parent.parent / "data" / "ecu_db.sqlite"
if not _DEF_DB.exists():                      # fallback to bundled location
    _DEF_DB = Path(__file__).with_name("ecu_db.sqlite")
DB_PATH = Path(os.environ.get("MACDIAG_DB_PATH", str(_DEF_DB)))


def available() -> bool:
    """True only if the DB exists AND has a usable `ecu` table.

    A missing, empty (0-byte) or corrupt file must NOT crash the app - it just
    means "no catalog". Everything else (curated modules, DTC, coding) keeps
    working; rebuild with tools/build_ecu_db.py.
    """
    c = _conn()
    if c is None:
        return False
    try:
        c.execute("SELECT 1 FROM ecu LIMIT 1").fetchone()
        return True
    except sqlite3.Error:
        return False
    finally:
        c.close()


def _conn() -> sqlite3.Connection | None:
    if not DB_PATH.exists() or DB_PATH.stat().st_size == 0:
        return None
    try:
        # immutable read-only: avoids file locking (works on network/FUSE mounts)
        uri = f"file:{DB_PATH}?immutable=1&mode=ro"
        c = sqlite3.connect(uri, uri=True)
        c.row_factory = sqlite3.Row
        return c
    except sqlite3.Error:
        return None


def _row_to_ecu(c: sqlite3.Connection, row: sqlite3.Row) -> dict:
    name = row["name"]
    g = lambda t, col: [r[0] for r in c.execute(  # noqa: E731
        f"SELECT {col} FROM {t} WHERE ecu=?", (name,))]
    keys = row.keys()
    return {
        "ecu": name,
        "file": row["file"],
        "protocol": row["protocol"],
        "template": row["template"],
        "size": row["size"],
        "bus": json.loads(row["bus_json"] or "{}"),
        "can_request": row["can_request"] if "can_request" in keys else None,
        "can_response": row["can_response"] if "can_response" in keys else None,
        "can_global": row["can_global"] if "can_global" in keys else None,
        "baudrate": row["baudrate"] if "baudrate" in keys else None,
        "part_numbers": g("ecu_part", "part"),
        "variants": g("ecu_variant", "variant"),
        "chassis": g("ecu_chassis", "chassis"),
        "comparams": g("ecu_comparam", "comparam"),
        "jobs": g("ecu_job", "job"),
    }


def get(name: str) -> dict | None:
    c = _conn()
    if c is None:
        return None
    try:
        row = c.execute("SELECT * FROM ecu WHERE name=?", (name,)).fetchone()
        return _row_to_ecu(c, row) if row else None
    except sqlite3.Error:
        return None
    finally:
        c.close()


def search(q: str | None = None, chassis: str | None = None,
           protocol: str | None = None, limit: int = 100) -> list[dict]:
    c = _conn()
    if c is None:
        return []
    try:
        return _search(c, q, chassis, protocol, limit)
    except sqlite3.Error:
        return []
    finally:
        c.close()


def _search(c, q, chassis, protocol, limit):
    names: list[str]
    if q:
        # match ECU name first; fall back to FTS over jobs/parts
        like = f"%{q}%"
        names = [r[0] for r in c.execute(
            "SELECT name FROM ecu WHERE name LIKE ? ORDER BY name", (like,))]
        try:
            for r in c.execute(
                    "SELECT name FROM ecu_fts WHERE ecu_fts MATCH ? LIMIT 200",
                    (q + "*",)):
                if r[0] not in names:
                    names.append(r[0])
        except sqlite3.OperationalError:
            pass
    else:
        names = [r[0] for r in c.execute("SELECT name FROM ecu ORDER BY name")]

    out = []
    for name in names:
        row = c.execute("SELECT * FROM ecu WHERE name=?", (name,)).fetchone()
        if not row:
            continue
        e = _row_to_ecu(c, row)
        if chassis and chassis not in e["chassis"]:
            continue
        if protocol and e["protocol"] != protocol:
            continue
        out.append(e)
        if len(out) >= limit:
            break
    return out


def chassis_counts() -> dict[str, int]:
    c = _conn()
    if c is None:
        return {}
    try:
        return {r[0]: r[1] for r in c.execute(
            "SELECT chassis, COUNT(*) FROM ecu_chassis GROUP BY chassis "
            "ORDER BY 2 DESC")}
    except sqlite3.Error:
        return {}
    finally:
        c.close()


def stats() -> dict:
    c = _conn()
    if c is None:
        return {"available": False, "count": 0}
    try:
        total = c.execute("SELECT COUNT(*) FROM ecu").fetchone()[0]
        by_proto = {r[0]: r[1] for r in c.execute(
            "SELECT protocol, COUNT(*) FROM ecu GROUP BY protocol")}
        return {"available": True, "count": total, "by_protocol": by_proto,
                "by_chassis": chassis_counts()}
    except sqlite3.Error:
        return {"available": False, "count": 0}
    finally:
        c.close()
