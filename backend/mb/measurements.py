"""
Measurement / service groups from Vediamo .vsg files.

Each .vsg is an engineer-built screen of diagnostic jobs (live data, adaptations,
routines) with aliases, units and limits. We index them by ECU and expose:
  * measurement groups -> live-data dashboards (DT_/ADJ_ jobs)
  * service groups      -> procedures with routines/actuators (RT_)

VSG library directory: env MACDIAG_VSG_DIR (mounted data volume).

Reading real physical values requires the job's request bytes (from the CBF
DiagService) AND the output scaling (from the CBF output presentation, not yet
parsed). For now values are synthesized in simulator mode; on hardware the raw
read hook is in place and scaling is a follow-up.
"""

from __future__ import annotations

import math
import os
import sys
import time
from functools import lru_cache
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))
import parse_vsg as _vsg  # noqa: E402

VSG_DIR = Path(os.environ.get("MACDIAG_VSG_DIR",
                              str(Path(__file__).resolve().parent.parent.parent / "data" / "vsg")))


def available() -> bool:
    return VSG_DIR.exists() and any(VSG_DIR.rglob("*.vsg"))


@lru_cache(maxsize=1)
def _index() -> list[dict]:
    """Parse every .vsg once -> list of group summaries (with rel path)."""
    out = []
    if not VSG_DIR.exists():
        return out
    for p in sorted(VSG_DIR.rglob("*.vsg")):
        try:
            g = _vsg.parse_vsg(p)
        except Exception:  # noqa: BLE001
            continue
        g["path"] = str(p.relative_to(VSG_DIR))
        out.append(g)
    return out


def _norm(ecu: str) -> str:
    return (ecu or "").upper().replace(" ", "")


@lru_cache(maxsize=24)
def _diag_cat(ecu: str) -> dict:
    """diag-service catalogue (qualifier -> {request hex, description, ...}) from
    the ECU's CBF, cached. Used to auto-build groups and to read on hardware."""
    from . import varcoding
    p = varcoding.cbf_for(ecu)
    if not p:
        return {}
    sys.path.insert(0, str(_TOOLS))
    import caesar_vc  # noqa: E402
    try:
        return caesar_vc.diag_catalog(p)
    except Exception:  # noqa: BLE001
        return {}


_CBF_TITLE = {"ru": "Все параметры (CBF)", "en": "All parameters (CBF)",
              "de": "Alle Parameter (CBF)"}
_CBF_DESC = {
    "ru": {"title": "Все параметры из CBF",
           "what": "Автогруппа: все data-параметры (DT_) этого ЭБУ из его CBF.",
           "when": "Для блоков без готовой .vsg-группы (бензин, кузовные…).",
           "how": "На железе значения читаются сырыми (масштабирование — позже)."},
    "en": {"title": "All parameters from CBF",
           "what": "Auto group: every data parameter (DT_) of this ECU from its CBF.",
           "when": "For ECUs without a ready .vsg group (petrol, body…).",
           "how": "On hardware values are read raw (scaling — later)."},
    "de": {"title": "Alle Parameter aus CBF",
           "what": "Auto-Gruppe: alle Datenparameter (DT_) dieses Steuergeräts aus seinem CBF.",
           "when": "Für Steuergeräte ohne fertige .vsg-Gruppe (Benzin, Karosserie…).",
           "how": "An der Hardware werden Werte roh gelesen (Skalierung — später)."},
}


def cbf_group(ecu: str, lang: str = "ru") -> dict | None:
    """Auto-generated measurement group from a CBF's data parameters (DT_*).
    For ECUs that have no curated .vsg group (petrol engine, body, etc.)."""
    cat = _diag_cat(ecu)
    if not cat:
        return None
    from . import glossary
    svc = []
    for q, info in sorted(cat.items()):
        if not q.startswith("DT_"):
            continue
        svc.append({"job": q, "alias": info.get("description") or "",
                    "label": glossary.humanize(q, info.get("description") or ""),
                    "note": glossary.prefix_note(q), "unit": "", "kind": "data",
                    "low": None, "high": None, "valmap": None,
                    "req": info.get("request")})
        if len(svc) >= 200:
            break
    if not svc:
        return None
    return {"file": f"cbf:{ecu}", "title": _CBF_TITLE.get(lang, _CBF_TITLE["ru"]),
            "ecu": ecu, "kind": "measurement", "count": len(svc), "services": svc}


def groups_for(ecu: str, lang: str = "ru") -> dict:
    """Measurement + service groups for an ECU: curated .vsg groups, plus an
    auto-generated 'all parameters' group from the CBF."""
    from . import glossary
    e = _norm(ecu)
    meas, serv = [], []
    for g in _index():
        if _norm(g.get("ecu")) != e:
            continue
        steps = sum(1 for s in g.get("services", []) if s.get("kind") == "routine")
        item = {"path": g["path"],
                "title": glossary.friendly_title(g["path"], g["title"], lang),
                "raw_title": g["title"], "count": g["count"], "steps": steps}
        (serv if g["kind"] == "service" else meas).append(item)
    cg = cbf_group(ecu, lang)
    if cg:
        meas.append({"path": cg["file"], "title": cg["title"],
                     "count": cg["count"], "auto": True})
    return {"ecu": ecu, "measurement": meas, "service": serv}


def ecus_with_groups() -> list[str]:
    """ECUs offering measurements: those with .vsg groups, plus the curated
    modules (which get an auto CBF group)."""
    s = {g["ecu"] for g in _index() if g.get("ecu")}
    try:
        from .modules import MODULES
        for m in MODULES:
            if m.get("cbf"):
                s.add(m["cbf"])
    except Exception:  # noqa: BLE001
        pass
    return sorted(s)


def get_group(path: str, lang: str = "ru") -> dict | None:
    if path.startswith("cbf:"):
        g = cbf_group(path[4:], lang)
        if g:
            g["description"] = _CBF_DESC.get(lang, _CBF_DESC["ru"])
        return g
    full = VSG_DIR / path
    if not full.exists():
        return None
    g = _vsg.parse_vsg(full)
    g["path"] = path
    raw_title = g.get("title", "")
    from . import glossary
    g["description"] = glossary.describe_group(path, raw_title, lang)
    g["title"] = glossary.friendly_title(path, raw_title, lang)
    for s in g["services"]:
        s["label"] = glossary.humanize(s["job"], s.get("alias", ""))
        s["note"] = glossary.prefix_note(s["job"])
    return g


def group_ecu(path: str) -> str | None:
    g = get_group(path)
    return g.get("ecu") if g else None


def _raw_value(req: bytes, resp: bytes):
    """Strip the positive-response echo, interpret the remaining bytes."""
    n = 3 if req and req[0] == 0x22 else 2 if req and req[0] == 0x21 else 1
    data = resp[n:] if len(resp) > n else b""
    if not data:
        return None
    if len(data) <= 4:
        return int.from_bytes(data, "big")
    return data.hex().upper()


def read_values(path: str, hw: bool = False, client=None) -> list[dict]:
    """Return current values for a group's data parameters.

    Simulator: synthesize plausible values within each parameter's limits.
    Hardware: TODO scale raw job responses (needs output-presentation parsing);
    for now still synthesizes so the dashboard renders.
    """
    g = get_group(path)
    if not g:
        return []
    cat = _diag_cat(g["ecu"]) if (hw and client) else {}
    t = time.time()
    out = []
    for i, s in enumerate(g["services"]):
        if s["kind"] == "routine":
            continue
        val = None
        # hardware: read the real (raw) value via the job's request bytes
        if hw and client:
            reqhex = s.get("req") or cat.get(s["job"], {}).get("request")
            if reqhex:
                try:
                    rb = bytes.fromhex(reqhex)
                    val = _raw_value(rb, client.raw_request(rb))
                except Exception:  # noqa: BLE001
                    val = None
        if val is None:
            lo = s["low"] if s["low"] is not None else 0
            hi = s["high"] if s["high"] is not None else 100
            val = round(lo + (hi - lo) * (0.5 + 0.45 * math.sin(t / 3 + i)), 2)
            if s.get("valmap") and not s["unit"]:
                lbl = s["valmap"].get(int(round(val)))
                if lbl and lbl != "?":
                    val = lbl
        out.append({"job": s["job"], "label": s.get("label") or s["job"],
                    "note": s.get("note", ""), "unit": s["unit"], "value": val,
                    "low": s["low"], "high": s["high"], "kind": s["kind"]})
    return out
