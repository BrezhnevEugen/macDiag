"""
Mercedes-Benz W221 (S-Class) and X164 (GL-Class) diagnostic module map.

Data sources
------------
1. `vediamo_catalog.json` (next to this file) - REAL metadata extracted from the
   user's Vediamo CBF files by tools/parse_cbf.py: ECU name, diagnostic protocol
   (from the CBF communication template), MB part numbers, variants, bus speeds.
   This is the source of truth for *which* ECU speaks *which* protocol.

2. `CORE` below - a curated list mapping the pickable W221/X164 control units to
   their diagnostic CAN request/response IDs and a human label. The CAN IDs are
   the standard MB 11-bit diagnostic addressing for these chassis and are marked
   `id_source: "standard"` - VERIFY against the car (they are NOT yet extracted
   from the CBF comparam tables; a Vediamo comm-trace is the easiest way to
   confirm the exact IDs on the wire).

NOTE on chassis association: MB part numbers overlap across Baureihen, so the
chassis is NOT inferred from the part-number prefix. It comes from BRxxx/Wxxx
references inside each CBF and from ECU naming (see tools/parse_cbf.py).
"""

from __future__ import annotations

import json
from pathlib import Path

from . import ecu_db

_CATALOG_PATH = Path(__file__).with_name("vediamo_catalog.json")


def _load_catalog() -> dict:
    """ecu name -> real metadata. Prefer the unified SQLite DB; fall back to the
    bundled JSON subset so the app works even without the full DB."""
    try:
        if ecu_db.available():
            return {e["ecu"]: e for e in ecu_db.search(limit=10000)}
    except Exception:  # noqa: BLE001 - bad DB must never crash startup
        pass
    if _CATALOG_PATH.exists():
        try:
            data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
            return {e["ecu"]: e for e in data if "ecu" in e}
        except Exception:  # noqa: BLE001
            return {}
    return {}


CATALOG = _load_catalog()


# Curated pickable modules. `cbf` links to a real ECU in the catalog; protocol,
# part numbers and template are overlaid from there when available.
CORE = [
    # X164 (GL) core
    {"id": "ezs",  "cbf": "EZS164", "name": "EZS / EIS (ignition, gateway)", "tx": 0x7E4, "rx": 0x7EC, "chassis": ["X164"]},
    {"id": "ki",   "cbf": "KI164",  "name": "Instrument cluster (KI)",       "tx": 0x7C4, "rx": 0x7CC, "chassis": ["X164"]},
    {"id": "samv", "cbf": "SAMV164","name": "Front SAM (SAM-V)",             "tx": 0x7C0, "rx": 0x7C8, "chassis": ["X164"]},
    {"id": "samh", "cbf": "SAMH164","name": "Rear SAM (SAM-H)",              "tx": 0x7C1, "rx": 0x7C9, "chassis": ["X164"]},
    {"id": "kla",  "cbf": "KLA164", "name": "Climate control (KLA)",         "tx": 0x7C3, "rx": 0x7CB, "chassis": ["X164"]},
    {"id": "tcm",  "cbf": "TCM164", "name": "7G-Tronic transmission (VGS)",  "tx": 0x7E1, "rx": 0x7E9, "chassis": ["X164"]},
    {"id": "zgw",  "cbf": "ZGW164", "name": "Central gateway (ZGW)",         "tx": 0x7E7, "rx": 0x7EF, "chassis": ["X164"]},
    {"id": "mrm",  "cbf": "MRM164", "name": "Multifunction camera/relay (MRM)", "tx": 0x7C6, "rx": 0x7CE, "chassis": ["X164"]},
    {"id": "rbs",  "cbf": "RBS164", "name": "Tyre pressure / RBS",           "tx": 0x7C2, "rx": 0x7CA, "chassis": ["X164"]},
    {"id": "fscm", "cbf": "FSCM164HY", "name": "Fuel system control (FSCM)", "tx": 0x7C5, "rx": 0x7CD, "chassis": ["X164"]},

    # Engine @ 0x7E0 — only one is fitted (petrol ME-SFI *or* diesel CDI). They
    # share the same diagnostic address, so just two variants are listed.
    {"id": "me97", "cbf": "ME97",   "name": "ME-SFI engine (M272/M273 petrol)", "tx": 0x7E0, "rx": 0x7E8, "chassis": ["W221", "X164"]},
    {"id": "crd3", "cbf": "CRD3",   "name": "CDI engine (OM642 diesel CRD3)","tx": 0x7E0, "rx": 0x7E8, "chassis": ["W221", "X164"]},
    {"id": "esp",  "cbf": "ESP9MFA","name": "ESP 9 / ABS / BAS",             "tx": 0x7E5, "rx": 0x7ED, "chassis": ["W221", "X164"]},

    # W221 specific
    {"id": "eis447", "cbf": "EIS447", "name": "EIS (W221 facelift)",         "tx": 0x7E4, "rx": 0x7EC, "chassis": ["W221"]},
    {"id": "ic204",  "cbf": "IC_204", "name": "Instrument cluster (W221)",   "tx": 0x7C4, "rx": 0x7CC, "chassis": ["W221"]},
    {"id": "eps218", "cbf": "EPS218", "name": "Electric steering lock (EPS)","tx": 0x7C7, "rx": 0x7CF, "chassis": ["W221"]},
    {"id": "fscm221","cbf": "FSCM221","name": "Fuel system control (W221)",  "tx": 0x7C5, "rx": 0x7CD, "chassis": ["W221"]},
]


def _enrich(entry: dict) -> dict:
    m = dict(entry)
    meta = CATALOG.get(entry.get("cbf", ""), {})
    m["protocol"] = meta.get("protocol", "uds")
    m["template"] = meta.get("template", "")
    m["part_numbers"] = meta.get("part_numbers", [])
    m["variants"] = meta.get("variants", [])
    m["bus"] = meta.get("bus", {})
    m["baudrate"] = meta.get("baudrate")
    m["can_global"] = meta.get("can_global")
    # Prefer REAL CAN ids decoded from the CBF comparam tables; fall back to the
    # curated standard addressing only when the CBF didn't yield them.
    if meta.get("can_request"):
        m["tx"] = meta["can_request"]
        m["rx"] = meta["can_response"]
        m["id_source"] = "cbf"           # extracted from Vediamo CBF
    else:
        m["id_source"] = "standard"      # needs verification
    m["in_catalog"] = bool(meta)
    return m


MODULES = [_enrich(e) for e in CORE]
MODULES_BY_ID = {m["id"]: m for m in MODULES}


def modules_for(chassis: str | None = None):
    if not chassis:
        return MODULES
    return [m for m in MODULES if chassis in m["chassis"]]


def catalog_list(chassis: str | None = None, q: str | None = None,
                 protocol: str | None = None, limit: int = 500):
    """Pull ECUs from the unified DB (or the bundled JSON fallback)."""
    if ecu_db.available():
        return ecu_db.search(q=q, chassis=chassis, protocol=protocol, limit=limit)
    items = list(CATALOG.values())
    if chassis:
        items = [e for e in items if chassis in e.get("chassis", [])]
    if protocol:
        items = [e for e in items if e.get("protocol") == protocol]
    if q:
        ql = q.lower()
        items = [e for e in items if ql in e.get("ecu", "").lower()]
    return sorted(items, key=lambda e: e.get("ecu", ""))[:limit]
