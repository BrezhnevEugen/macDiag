#!/usr/bin/env python3
"""
Cross-check seed-key coverage: which ECUs in the macDiag database have a
definition in UnlockECU's db.json, which security provider they use, and whether
that provider is ported in backend/mb/unlock.py.

Run after fetching the definition database:
    python tools/fetch_unlock_db.py
    python tools/check_unlock_coverage.py            # full report
    python tools/check_unlock_coverage.py EZS164 KI164 ESP9MFA   # specific ECUs

The seed-key constants come from UnlockECU's db.json (reverse-engineered from
the per-ECU Mercedes security DLLs). For ECUs NOT in db.json, the algorithm lives
in those DLLs (shipped with Vediamo/DTS/Xentry) - reverse-engineer them, or have
UnlockECU call the original DLL directly. NOTE: SMR-D/SMR-F files are flash
containers and do NOT carry seed-key constants.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.mb import unlock, ecu_db  # noqa: E402


def _db_index() -> dict:
    """ecu name (upper) -> list of definitions, from unlock_db.json."""
    p = unlock.DB_PATH
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    entries = data if isinstance(data, list) else data.get("Definitions", [])
    idx = {}
    for d in entries:
        for name in [d.get("EcuName")] + (d.get("Aliases") or []):
            if name:
                idx.setdefault(name.upper(), []).append(d)
    return idx


def report(names: list[str] | None = None):
    if not unlock.DB_PATH.exists():
        print("unlock_db.json not found. Run: python tools/fetch_unlock_db.py")
        return
    dbidx = _db_index()
    ported = set(unlock.PROVIDERS)

    if names:
        ecus = [{"ecu": n} for n in names]
    else:
        ecus = ecu_db.search(limit=10000) if ecu_db.available() else []
        if not ecus:
            print("ecu_db.sqlite not found. Run: python tools/build_ecu_db.py ...")
            return

    covered = unported = missing = 0
    rows = []
    for e in ecus:
        name = e["ecu"]
        defs = dbidx.get(name.upper(), [])
        if not defs:
            status, prov, levels = "—  нет в db.json", "", ""
            missing += 1
        else:
            provs = sorted({d.get("Provider") for d in defs})
            levels = ",".join(str(d.get("AccessLevel")) for d in defs)
            prov = ", ".join(provs)
            if all(pv in ported for pv in provs):
                status = "✓  готов"
                covered += 1
            else:
                status = "△  есть, провайдер не портирован"
                unported += 1
        rows.append((name, status, prov, levels))

    rows.sort(key=lambda r: (r[1].startswith("—"), r[1].startswith("△"), r[0]))
    print(f"{'ECU':<16}{'статус':<34}{'провайдер (уровни)'}")
    print("-" * 96)
    for name, status, prov, levels in rows:
        pv = f"{prov} [{levels}]" if prov else ""
        print(f"{name:<16}{status:<34}{pv}")
    print("-" * 96)
    print(f"готов: {covered}  |  провайдер не портирован: {unported}  |  "
          f"нет в db.json: {missing}  |  всего: {len(rows)}")


if __name__ == "__main__":
    report(sys.argv[1:] or None)
