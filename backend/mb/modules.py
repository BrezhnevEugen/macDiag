"""
Mercedes-Benz W221 (S-Class) and X164 (GL-Class) diagnostic module map.

Data sources
------------
1. `vediamo_catalog.json` (next to this file) - REAL metadata extracted from the
   user's Vediamo CBF files by tools/parse_cbf.py: ECU name, diagnostic protocol
   (from the CBF communication template), MB part numbers, variants, bus speeds.
   This is the source of truth for *which* ECU speaks *which* protocol.

2. A vehicle profile JSON (`profiles/w221_x164.json` by default) - user-editable
   aliases, labels and fallback CAN request/response IDs. Select another profile
   without changing code with `MACDIAG_PROFILE_PATH=/path/to/profile.json`.
   CBF-derived identifiers always override the profile values.

NOTE on chassis association: MB part numbers overlap across Baureihen, so the
chassis is NOT inferred from the part-number prefix. It comes from BRxxx/Wxxx
references inside each CBF and from ECU naming (see tools/parse_cbf.py).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from . import ecu_db

_CATALOG_PATH = Path(__file__).with_name("vediamo_catalog.json")
_PROFILES_DIR = Path(__file__).with_name("profiles")
_DEFAULT_PROFILE_PATH = _PROFILES_DIR / "w221_x164.json"
_PROFILE_LOCK = threading.RLock()


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


def _profile_path() -> Path:
    return Path(os.environ.get("MACDIAG_PROFILE_PATH", str(_DEFAULT_PROFILE_PATH)))


def _load_profile(path: Path) -> dict:
    """Load a vehicle profile without turning malformed local data into a crash."""
    result = {
        "id": None, "label": None, "path": str(path), "modules": [],
        "simulator": {}, "gateway_probes": {}, "gateway_info": {}, "error": None,
    }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("modules"), list):
            raise ValueError("profile must be an object with a modules array")
        ids = set()
        modules = []
        for item in raw["modules"]:
            if not isinstance(item, dict) or not item.get("id") or not item.get("cbf"):
                raise ValueError("each profile module needs id and cbf")
            if item["id"] in ids:
                raise ValueError(f"duplicate module id: {item['id']}")
            ids.add(item["id"])
            modules.append(dict(item))
        simulator = raw.get("simulator", {})
        gateway_probes = raw.get("gateway_probes", {})
        gateway_info = raw.get("gateway_info", {})
        if not all(isinstance(value, dict) for value in (
                simulator, gateway_probes, gateway_info)):
            raise ValueError("simulator, gateway_probes and gateway_info must be objects")
        result.update({
            "id": raw.get("id"), "label": raw.get("label"), "modules": modules,
            "simulator": simulator, "gateway_probes": gateway_probes,
            "gateway_info": gateway_info,
        })
    except (OSError, ValueError, json.JSONDecodeError) as e:
        result["error"] = str(e)
    return result


PROFILE = _load_profile(_profile_path())
MODULES: list[dict] = []
MODULES_BY_ID: dict[str, dict] = {}


def profile_info() -> dict:
    """Profile metadata safe to expose in the API and diagnostics UI."""
    with _PROFILE_LOCK:
        return {key: PROFILE[key] for key in ("id", "label", "path", "error")} | {
            "module_count": len(PROFILE["modules"]),
            "source": "packaged" if Path(PROFILE["path"]).parent == _PROFILES_DIR else "external",
        }


def simulator_profile() -> dict:
    """Current simulator scenario, owned by the active vehicle profile."""
    with _PROFILE_LOCK:
        return json.loads(json.dumps(PROFILE["simulator"]))


def gateway_probes() -> dict:
    """Read-only gateway probe definitions for the active vehicle profile."""
    with _PROFILE_LOCK:
        return json.loads(json.dumps(PROFILE["gateway_probes"]))


def gateway_info_spec() -> dict:
    """Read-only gateway identity/configuration specification from the profile."""
    with _PROFILE_LOCK:
        return json.loads(json.dumps(PROFILE["gateway_info"]))


def available_profiles() -> list[dict]:
    """Only packaged profiles are selectable from the UI; no arbitrary paths."""
    profiles = []
    for path in sorted(_PROFILES_DIR.glob("*.json")):
        profile = _load_profile(path)
        if profile["error"] is None and profile["id"]:
            profiles.append({
                "id": profile["id"], "label": profile["label"] or profile["id"],
                "module_count": len(profile["modules"]),
            })
    return profiles


def select_profile(profile_id: str) -> dict | None:
    """Switch to a packaged profile without accepting a filesystem path from UI."""
    for path in _PROFILES_DIR.glob("*.json"):
        candidate = _load_profile(path)
        if candidate["error"] is None and candidate["id"] == profile_id:
            with _PROFILE_LOCK:
                global PROFILE
                PROFILE = candidate
                _rebuild_registry()
                return profile_info()
    return None


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
    # Prefer REAL CAN ids decoded from CBF comparam tables; fallback identifiers
    # are profile data, never vehicle values embedded in executable code.
    if meta.get("can_request"):
        m["tx"] = meta["can_request"]
        m["rx"] = meta["can_response"]
        m["id_source"] = "cbf"           # extracted from Vediamo CBF
    else:
        m["id_source"] = "profile"       # needs verification against the car
    m["in_catalog"] = bool(meta)
    return m


def _rebuild_registry() -> None:
    """Mutate exported collections so existing importers see a profile reload."""
    enriched = [_enrich(e) for e in PROFILE["modules"]]
    MODULES[:] = enriched
    MODULES_BY_ID.clear()
    MODULES_BY_ID.update({m["id"]: m for m in MODULES})


_rebuild_registry()


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
