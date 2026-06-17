"""
Measurement / service groups from Vediamo .vsg and .mwg files.

Each .vsg/.mwg is an engineer-built screen of diagnostic jobs (live data,
adaptations, routines). We index them by ECU and expose:
  * measurement groups -> live-data dashboards (DT_/ADJ_ jobs)
  * service groups      -> procedures with routines/actuators (RT_)

Runtime DB: env MACDIAG_MEASURE_DB (preferred, generated from local raw data).
Raw fallback dirs: MACDIAG_VSG_DIR and MACDIAG_MWG_DIR.

Reading real physical values requires the job's request bytes (from the CBF
DiagService) AND the output scaling (from the CBF output presentation, not yet
parsed). For now values are synthesized in simulator mode; on hardware the raw
read hook is in place and scaling is a follow-up.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import sys
import time
import unicodedata
from functools import lru_cache
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))
import parse_vsg as _vsg  # noqa: E402
import parse_mwg as _mwg  # noqa: E402

VSG_DIR = Path(os.environ.get("MACDIAG_VSG_DIR",
                              str(Path(__file__).resolve().parent.parent.parent / "data" / "vsg")))
MWG_DIR = Path(os.environ.get(
    "MACDIAG_MWG_DIR",
    str(Path(__file__).resolve().parent.parent.parent / "data" / "vediamo_raw"),
))
MEASURE_DB = Path(os.environ.get(
    "MACDIAG_MEASURE_DB",
    str(Path(__file__).resolve().parent.parent.parent / "data" / "measurements.sqlite"),
))

_LANG_RE = re.compile(r"^[a-z]{2,12}(?:[-_][a-z0-9]{2,12})?$", re.I)
_HW_READ_ONLY_SIDS = {0x21, 0x22}
_HW_READ_ONLY_JOB_PREFIXES = ("DT_",)


def available() -> bool:
    if _db_available():
        return True
    return ((VSG_DIR.exists() and any(VSG_DIR.rglob("*.vsg")))
            or (MWG_DIR.exists() and any(MWG_DIR.rglob("*.mwg"))))


def _db_available() -> bool:
    if not MEASURE_DB.exists():
        return False
    try:
        with sqlite3.connect(MEASURE_DB) as db:
            db.execute("SELECT 1 FROM groups LIMIT 1").fetchone()
        return True
    except sqlite3.Error:
        return False


def _table_exists(db: sqlite3.Connection, table: str) -> bool:
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table,),
    ).fetchone() is not None


def _table_has_column(db: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in db.execute(f"PRAGMA table_info({table})"))


@lru_cache(maxsize=1)
def _index() -> list[dict]:
    """Measurement group summaries. Prefer generated SQLite, fallback to raw."""
    if _db_available():
        try:
            st = MEASURE_DB.stat()
            return _db_index(str(MEASURE_DB), st.st_mtime, st.st_size)
        except Exception:  # noqa: BLE001
            pass
    return _raw_index()


@lru_cache(maxsize=4)
def _db_index(db_path: str, mtime: float, size: int) -> list[dict]:
    out = []
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        for r in db.execute(
            """
            SELECT path, localization_key, source, file, title, ecu, kind, count
            FROM groups ORDER BY path
            """
        ):
            out.append(dict(r))
    return out


def _translations(lang: str) -> dict[str, str]:
    if not lang or not _db_available():
        return {}
    try:
        st = MEASURE_DB.stat()
        return _db_translations(str(MEASURE_DB), st.st_mtime, st.st_size, lang)
    except Exception:  # noqa: BLE001
        return {}


@lru_cache(maxsize=16)
def _db_translations(db_path: str, mtime: float, size: int, lang: str) -> dict[str, str]:
    try:
        with sqlite3.connect(db_path) as db:
            return {
                key: text
                for key, text in db.execute(
                    """
                    SELECT localization_key, text
                    FROM translations
                    WHERE lang = ? AND text <> ''
                    """,
                    (lang,),
                )
            }
    except sqlite3.Error:
        return {}


def _valid_translation_lang(lang: str) -> str:
    lang = (lang or "").strip().lower()
    if lang == "source" or not _LANG_RE.match(lang):
        raise ValueError("invalid translation language")
    return lang


def translation_stats(lang: str = "ru") -> dict:
    """Coverage counters for the measurement dictionary."""
    lang = _valid_translation_lang(lang)
    if not _db_available():
        return {"available": False, "lang": lang, "languages": {},
                "source_count": 0, "translated_count": 0, "missing_count": 0}
    with sqlite3.connect(MEASURE_DB) as db:
        db.row_factory = sqlite3.Row
        languages = {
            r["lang"]: r["count"]
            for r in db.execute(
                "SELECT lang, COUNT(*) AS count FROM translations GROUP BY lang ORDER BY lang"
            )
        }
        row = db.execute(
            """
            SELECT
              COUNT(source.localization_key) AS source_count,
              COUNT(target.localization_key) AS translated_count
            FROM translations AS source
            LEFT JOIN translations AS target
              ON target.localization_key = source.localization_key
             AND target.lang = ?
             AND target.text <> ''
            WHERE source.lang = 'source'
            """,
            (lang,),
        ).fetchone()
    source_count = int(row["source_count"] or 0)
    translated_count = int(row["translated_count"] or 0)
    return {"available": True, "lang": lang, "languages": languages,
            "source_count": source_count, "translated_count": translated_count,
            "missing_count": max(0, source_count - translated_count)}


def translation_rows(lang: str = "ru", q: str = "", kind: str = "all",
                     status: str = "all", limit: int = 100, offset: int = 0) -> dict:
    """Paginated dictionary rows for UI editing."""
    lang = _valid_translation_lang(lang)
    kind = kind if kind in {"all", "group", "service"} else "all"
    status = status if status in {"all", "missing", "translated"} else "all"
    limit = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    if not _db_available():
        return {"available": False, "lang": lang, "rows": [], "total": 0,
                "limit": limit, "offset": offset, "stats": translation_stats(lang)}

    where = ["source.lang = 'source'"]
    params: list[object] = [lang]
    if kind == "group":
        where.append("source.localization_key LIKE 'measure.group.%'")
    elif kind == "service":
        where.append("source.localization_key LIKE 'measure.service.%'")
    if status == "missing":
        where.append("(target.text IS NULL OR target.text = '')")
    elif status == "translated":
        where.append("(target.text IS NOT NULL AND target.text <> '')")
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        where.append(
            "(source.localization_key LIKE ? OR source.text LIKE ? OR "
            "source.context LIKE ? OR target.text LIKE ?)"
        )
        params.extend([like, like, like, like])
    where_sql = " AND ".join(where)

    with sqlite3.connect(MEASURE_DB) as db:
        db.row_factory = sqlite3.Row
        total = db.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM translations AS source
            LEFT JOIN translations AS target
              ON target.localization_key = source.localization_key
             AND target.lang = ?
            WHERE {where_sql}
            """,
            params,
        ).fetchone()["n"]
        rows = []
        for r in db.execute(
            f"""
            SELECT
              source.localization_key,
              CASE
                WHEN source.localization_key LIKE 'measure.group.%' THEN 'group'
                WHEN source.localization_key LIKE 'measure.service.%' THEN 'service'
                ELSE 'other'
              END AS kind,
              source.text AS source_text,
              source.context AS source_context,
              COALESCE(target.text, '') AS translation,
              COALESCE(target.context, '') AS translation_context
            FROM translations AS source
            LEFT JOIN translations AS target
              ON target.localization_key = source.localization_key
             AND target.lang = ?
            WHERE {where_sql}
            ORDER BY kind, source.localization_key
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ):
            rows.append(dict(r))
    return {"available": True, "lang": lang, "rows": rows, "total": int(total or 0),
            "limit": limit, "offset": offset, "stats": translation_stats(lang)}


def save_translation(localization_key: str, lang: str, text: str) -> dict:
    """Upsert/delete one translated label."""
    lang = _valid_translation_lang(lang)
    key = (localization_key or "").strip()
    if not key:
        raise ValueError("localization_key is required")
    if not _db_available():
        raise FileNotFoundError(str(MEASURE_DB))
    text = (text or "").strip()
    with sqlite3.connect(MEASURE_DB) as db:
        source = db.execute(
            "SELECT context FROM translations WHERE localization_key = ? AND lang = 'source'",
            (key,),
        ).fetchone()
        if not source:
            raise KeyError(key)
        if text:
            existing = db.execute(
                "SELECT context FROM translations WHERE localization_key = ? AND lang = ?",
                (key, lang),
            ).fetchone()
            context = (existing[0] if existing else source[0]) or ""
            marker = "ui_edit=1"
            if marker not in context:
                context = f"{context}; {marker}" if context else marker
            db.execute(
                """
                INSERT INTO translations(localization_key, lang, text, context)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(localization_key, lang) DO UPDATE SET
                  text = excluded.text,
                  context = excluded.context
                """,
                (key, lang, text, context),
            )
        else:
            db.execute(
                "DELETE FROM translations WHERE localization_key = ? AND lang = ?",
                (key, lang),
            )
        db.commit()
    _db_translations.cache_clear()
    return {"ok": True, "localization_key": key, "lang": lang, "text": text}


def _json_list(text: str | None) -> list:
    try:
        value = json.loads(text or "[]")
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _json_dict(text: str | None) -> dict:
    try:
        value = json.loads(text or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _reference_available() -> bool:
    if not _db_available():
        return False
    try:
        with sqlite3.connect(MEASURE_DB) as db:
            return _table_exists(db, "reference_links")
    except sqlite3.Error:
        return False


@lru_cache(maxsize=4)
def _db_reference_links(db_path: str, mtime: float, size: int) -> list[dict]:
    rows = []
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        if not _table_exists(db, "reference_links"):
            return rows
        for r in db.execute(
            """
            SELECT url, title, domain, tags_json, folders_json, sources_json,
                   vehicle_hints_json, attrs_json, source_file
            FROM reference_links
            ORDER BY title
            """
        ):
            row = dict(r)
            row["tags"] = _json_list(row.pop("tags_json", "[]"))
            row["folders"] = _json_list(row.pop("folders_json", "[]"))
            row["sources"] = _json_list(row.pop("sources_json", "[]"))
            row["vehicle_hints"] = _json_list(row.pop("vehicle_hints_json", "[]"))
            row["attrs"] = _json_dict(row.pop("attrs_json", "{}"))
            rows.append(row)
    return rows


def _reference_rows() -> list[dict]:
    if not _reference_available():
        return []
    try:
        st = MEASURE_DB.stat()
        return _db_reference_links(str(MEASURE_DB), st.st_mtime, st.st_size)
    except Exception:  # noqa: BLE001
        return []


def reference_link_stats() -> dict:
    """Counters for locally imported reference links."""
    rows = _reference_rows()
    tag_counts: dict[str, int] = {}
    vehicle_counts: dict[str, int] = {}
    domain_counts: dict[str, int] = {}
    for row in rows:
        domain = row.get("domain") or ""
        if domain:
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        for tag in row.get("tags") or []:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        for hint in row.get("vehicle_hints") or []:
            vehicle_counts[hint] = vehicle_counts.get(hint, 0) + 1
    return {
        "available": _reference_available(),
        "total": len(rows),
        "tags": dict(sorted(tag_counts.items())),
        "vehicles": dict(sorted(vehicle_counts.items())),
        "domains": dict(sorted(domain_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
    }


def reference_links(q: str = "", tag: str = "", vehicle: str = "",
                    limit: int = 100, offset: int = 0) -> dict:
    """Search local reference links imported from Safari/bookmark sources."""
    limit = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    q = (q or "").strip().lower()
    tag = (tag or "").strip().lower()
    vehicle = (vehicle or "").strip().upper().replace(" ", "")
    rows = _reference_rows()

    def match(row: dict) -> bool:
        tags = [str(t).lower() for t in (row.get("tags") or [])]
        vehicles = [str(v).upper().replace(" ", "") for v in (row.get("vehicle_hints") or [])]
        if tag and tag not in tags:
            return False
        if vehicle and vehicle not in vehicles:
            return False
        if q:
            haystack = "\n".join([
                str(row.get("title") or ""),
                str(row.get("url") or ""),
                str(row.get("domain") or ""),
                " ".join(str(x) for x in (row.get("tags") or [])),
                " ".join(str(x) for x in (row.get("folders") or [])),
                " ".join(str(x) for x in (row.get("vehicle_hints") or [])),
            ]).lower()
            if q not in haystack:
                return False
        return True

    filtered = [row for row in rows if match(row)]
    page = filtered[offset:offset + limit]
    return {
        "available": _reference_available(),
        "rows": page,
        "total": len(filtered),
        "limit": limit,
        "offset": offset,
        "stats": reference_link_stats(),
    }


@lru_cache(maxsize=4)
def _db_can_examples(db_path: str, mtime: float, size: int) -> list[dict]:
    rows = []
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        if not _table_exists(db, "can_examples"):
            return rows
        for r in db.execute(
            """
            SELECT id, source_url, source_title, vehicle, body, bus, speed_kbit_s,
                   can_id, dlc, data_hex, source_node, target_node, direction,
                   payload_meaning, tags_json, confidence, safety_note, notes
            FROM can_examples
            ORDER BY body, can_id, id
            """
        ):
            row = dict(r)
            row["tags"] = _json_list(row.pop("tags_json", "[]"))
            rows.append(row)
    return rows


def _can_example_rows() -> list[dict]:
    if not _db_available():
        return []
    try:
        st = MEASURE_DB.stat()
        return _db_can_examples(str(MEASURE_DB), st.st_mtime, st.st_size)
    except Exception:  # noqa: BLE001
        return []


def can_example_stats() -> dict:
    rows = _can_example_rows()
    tag_counts: dict[str, int] = {}
    vehicle_counts: dict[str, int] = {}
    can_id_counts: dict[str, int] = {}
    for row in rows:
        vehicle = (row.get("body") or row.get("vehicle") or "").strip()
        if vehicle:
            vehicle_counts[vehicle] = vehicle_counts.get(vehicle, 0) + 1
        can_id = (row.get("can_id") or "").strip()
        if can_id:
            can_id_counts[can_id] = can_id_counts.get(can_id, 0) + 1
        for tag_name in row.get("tags") or []:
            tag_counts[tag_name] = tag_counts.get(tag_name, 0) + 1
    return {
        "available": bool(rows) or _reference_available(),
        "total": len(rows),
        "tags": dict(sorted(tag_counts.items())),
        "vehicles": dict(sorted(vehicle_counts.items())),
        "can_ids": dict(sorted(can_id_counts.items())),
    }


def can_examples(q: str = "", tag: str = "", vehicle: str = "",
                 can_id: str = "", limit: int = 100, offset: int = 0) -> dict:
    """Search reviewed passive CAN examples extracted from reference sources."""
    limit = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    q = (q or "").strip().lower()
    tag = (tag or "").strip().lower()
    vehicle = (vehicle or "").strip().upper().replace(" ", "")
    can_id = (can_id or "").strip().upper().replace("0X", "0x")
    rows = _can_example_rows()

    def match(row: dict) -> bool:
        tags = [str(t).lower() for t in (row.get("tags") or [])]
        vehicles = [
            str(row.get("body") or "").upper().replace(" ", ""),
            str(row.get("vehicle") or "").upper().replace(" ", ""),
        ]
        if tag and tag not in tags:
            return False
        if vehicle and vehicle not in vehicles:
            return False
        if can_id and can_id != (row.get("can_id") or "").strip().upper().replace("0X", "0x"):
            return False
        if q:
            haystack = "\n".join([
                str(row.get("id") or ""),
                str(row.get("source_title") or ""),
                str(row.get("vehicle") or ""),
                str(row.get("body") or ""),
                str(row.get("bus") or ""),
                str(row.get("can_id") or ""),
                str(row.get("data_hex") or ""),
                str(row.get("source_node") or ""),
                str(row.get("target_node") or ""),
                str(row.get("payload_meaning") or ""),
                str(row.get("notes") or ""),
                " ".join(str(x) for x in (row.get("tags") or [])),
            ]).lower()
            if q not in haystack:
                return False
        return True

    filtered = [row for row in rows if match(row)]
    page = filtered[offset:offset + limit]
    return {
        "available": bool(rows),
        "rows": page,
        "total": len(filtered),
        "limit": limit,
        "offset": offset,
        "stats": can_example_stats(),
    }


def _raw_index() -> list[dict]:
    """Parse every .vsg/.mwg once -> list of group summaries (with rel path)."""
    out = []
    if VSG_DIR.exists():
        for p in sorted(VSG_DIR.rglob("*.vsg")):
            try:
                g = _vsg.parse_vsg(p)
            except Exception:  # noqa: BLE001
                continue
            if not g.get("services"):
                continue
            g["path"] = str(p.relative_to(VSG_DIR))
            g["source"] = "vsg"
            out.append(g)
    if MWG_DIR.exists():
        for p in sorted(MWG_DIR.rglob("*.mwg")):
            try:
                g = _mwg.parse_mwg(p)
            except Exception:  # noqa: BLE001
                continue
            if not g.get("services"):
                continue
            g["path"] = "mwg:" + str(p.relative_to(MWG_DIR))
            g["source"] = "mwg"
            out.append(g)
    return out


def _norm(ecu: str) -> str:
    return (ecu or "").upper().replace(" ", "")


def _slug(s: str) -> str:
    norm = unicodedata.normalize("NFKD", s or "")
    ascii_s = norm.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_s).strip("_")
    return (slug or "item")[:80]


def _l10n_key(namespace: str, semantic_id: str) -> str:
    digest = hashlib.sha1((semantic_id or "").encode("utf-8")).hexdigest()[:10]
    return f"{namespace}.{_slug(semantic_id)}.{digest}"


def _group_l10n_key(title: str, kind: str) -> str:
    return _l10n_key("measure.group", f"{kind}:{title}")


def _service_l10n_key(job: str) -> str:
    return _l10n_key("measure.service", job)


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


def _request_meta(request_hex: str) -> dict:
    req_hex = re.sub(r"[^0-9A-Fa-f]", "", request_hex or "").upper()
    if not req_hex:
        return {}
    try:
        req = bytes.fromhex(req_hex)
    except ValueError:
        return {}
    if not req:
        return {}
    sid = req[0]
    ident_type = ""
    ident = ""
    if sid in (0x21, 0x3B) and len(req) >= 2:
        ident_type = "lid"
        ident = f"{req[1]:02X}"
    elif sid in (0x22, 0x2E) and len(req) >= 3:
        ident_type = "did"
        ident = f"{((req[1] << 8) | req[2]):04X}"
    elif sid == 0x31 and len(req) >= 4:
        ident_type = "routine_id"
        ident = req[2:4].hex().upper()
    return {"req": req_hex, "sid": sid, "sid_hex": f"{sid:02X}",
            "identifier_type": ident_type, "identifier": ident}


def _hardware_read_guard(svc: dict, req_hex: str | None) -> dict:
    """Allow only conservative read-only measurement requests onto hardware."""
    req_hex = re.sub(r"[^0-9A-Fa-f]", "", req_hex or "").upper()
    if not req_hex:
        return {"allowed": False, "status": "missing_request",
                "reason": "no CBF request metadata"}
    try:
        req = bytes.fromhex(req_hex)
    except ValueError:
        return {"allowed": False, "status": "invalid_request",
                "reason": "request is not valid hex", "req": req_hex}
    if not req:
        return {"allowed": False, "status": "invalid_request",
                "reason": "request is empty", "req": req_hex}
    sid = req[0]
    sid_hex = f"{sid:02X}"
    if sid not in _HW_READ_ONLY_SIDS:
        return {"allowed": False, "status": "blocked",
                "reason": f"SID {sid_hex} is not in hardware read allowlist",
                "req": req_hex, "sid": sid, "sid_hex": sid_hex}
    job = (svc.get("job") or "").upper()
    if not job.startswith(_HW_READ_ONLY_JOB_PREFIXES):
        prefixes = ", ".join(_HW_READ_ONLY_JOB_PREFIXES)
        return {"allowed": False, "status": "blocked",
                "reason": f"job prefix is not in hardware read allowlist ({prefixes})",
                "req": req_hex, "sid": sid, "sid_hex": sid_hex}
    return {"allowed": True, "status": "ok", "reason": "",
            "req": req_hex, "sid": sid, "sid_hex": sid_hex}


def _attach_diag_meta(svc: dict, info: dict | None) -> dict:
    if not info:
        return svc
    req_hex = info.get("request") or info.get("request_hex") or ""
    meta = _request_meta(req_hex)
    if not meta:
        return svc
    svc.update(meta)
    svc["sec_level"] = info.get("sec_level")
    svc["diag_description"] = info.get("description") or ""
    svc["diag_name"] = info.get("name") or ""
    svc["diag_svc_type"] = info.get("svc_type")
    if info.get("presentation"):
        svc["output_presentation"] = info.get("presentation") or ""
        svc["output_raw_type"] = info.get("presentation_raw_type") or ""
        svc["output_byte_len"] = info.get("presentation_byte_len") or 0
        svc["output_value_map"] = info.get("presentation_value_map") or []
        svc["value_source"] = "raw"
    if info.get("cbf_file"):
        svc["diag_source"] = info.get("cbf_file")
    return svc


_CBF_TITLE = {"ru": "Все параметры (CBF)", "en": "All parameters (CBF)",
              "de": "Alle Parameter (CBF)"}
_CBF_L10N_KEY = _group_l10n_key("All parameters (CBF)", "measurement")
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
    tr = _translations(lang)
    svc = []
    for q, info in sorted(cat.items()):
        if not q.startswith("DT_"):
            continue
        key = _service_l10n_key(q)
        item = {"job": q, "localization_key": key,
                "alias": info.get("description") or "",
                "label": tr.get(key) or glossary.humanize(q, info.get("description") or ""),
                "note": glossary.prefix_note(q), "unit": "", "kind": "data",
                "low": None, "high": None, "valmap": None}
        svc.append(_attach_diag_meta(item, info))
        if len(svc) >= 200:
            break
    if not svc:
        return None
    title = tr.get(_CBF_L10N_KEY) or _CBF_TITLE.get(lang, _CBF_TITLE["ru"])
    return {"file": f"cbf:{ecu}", "localization_key": _CBF_L10N_KEY, "title": title,
            "ecu": ecu, "kind": "measurement", "count": len(svc), "services": svc}


def diagnostic_coverage(ecu: str = "") -> dict:
    """How many imported MWG/VSG jobs are linked to CBF DiagService metadata."""
    base = {"available": False, "ecu": ecu, "service_rows": 0, "matched_rows": 0,
            "exact_rows": 0, "normalized_rows": 0,
            "output_rows": 0, "raw_type_rows": 0, "unit_rows": 0,
            "formula_rows": 0, "missing_rows": 0, "distinct_jobs": 0,
            "matched_jobs": 0, "missing_jobs": 0, "coverage_pct": 0}
    if not _db_available():
        return base
    target = _norm(ecu)
    try:
        with sqlite3.connect(MEASURE_DB) as db:
            db.row_factory = sqlite3.Row
            has_diag = _table_exists(db, "diag_services")
            if not has_diag:
                return base | {"available": True}
            has_matches = _table_exists(db, "diag_service_matches")
            has_outputs = _table_exists(db, "service_outputs")
            where = ""
            params: list[object] = []
            if target:
                where = "WHERE imported.ecu = ?"
                params.append(target)
            if has_matches:
                match_join = """
                LEFT JOIN diag_service_matches AS m
                  ON m.ecu = imported.ecu
                 AND m.job = imported.job
                """
                count_expr = "m.qualifier"
                matched_jobs_expr = "CASE WHEN m.qualifier IS NOT NULL THEN imported.job END"
                exact_rows_expr = "SUM(CASE WHEN m.match_kind = 'exact' THEN 1 ELSE 0 END)"
                normalized_rows_expr = (
                    "SUM(CASE WHEN m.match_kind = 'normalized' THEN 1 ELSE 0 END)"
                )
                output_join = """
                LEFT JOIN service_outputs AS o
                  ON o.ecu = m.ecu
                 AND o.qualifier = m.qualifier
                """ if has_outputs else ""
            else:
                match_join = """
                LEFT JOIN diag_services AS d
                  ON d.ecu = imported.ecu
                 AND d.qualifier = imported.job
                """
                count_expr = "d.qualifier"
                matched_jobs_expr = "CASE WHEN d.qualifier IS NOT NULL THEN imported.job END"
                exact_rows_expr = "COUNT(d.qualifier)"
                normalized_rows_expr = "0"
                output_join = """
                LEFT JOIN service_outputs AS o
                  ON o.ecu = d.ecu
                 AND o.qualifier = d.qualifier
                """ if has_outputs else ""
            output_rows_expr = "COUNT(o.presentation)" if has_outputs else "0"
            raw_type_rows_expr = (
                "SUM(CASE WHEN o.raw_type <> '' THEN 1 ELSE 0 END)"
                if has_outputs else "0"
            )
            unit_rows_expr = (
                "SUM(CASE WHEN o.unit <> '' THEN 1 ELSE 0 END)"
                if has_outputs else "0"
            )
            formula_rows_expr = (
                "SUM(CASE WHEN o.formula <> '' THEN 1 ELSE 0 END)"
                if has_outputs else "0"
            )
            row = db.execute(
                f"""
                WITH imported AS (
                  SELECT
                    UPPER(REPLACE(CASE WHEN s.ecu <> '' THEN s.ecu ELSE g.ecu END, ' ', '')) AS ecu,
                    s.job AS job
                  FROM services AS s
                  JOIN groups AS g ON g.path = s.group_path
                  WHERE s.job <> ''
                )
                SELECT
                  COUNT(*) AS service_rows,
                  COUNT({count_expr}) AS matched_rows,
                  {exact_rows_expr} AS exact_rows,
                  {normalized_rows_expr} AS normalized_rows,
                  {output_rows_expr} AS output_rows,
                  {raw_type_rows_expr} AS raw_type_rows,
                  {unit_rows_expr} AS unit_rows,
                  {formula_rows_expr} AS formula_rows,
                  COUNT(DISTINCT imported.job) AS distinct_jobs,
                  COUNT(DISTINCT {matched_jobs_expr}) AS matched_jobs
                FROM imported
                {match_join}
                {output_join}
                {where}
                """,
                params,
            ).fetchone()
    except sqlite3.Error:
        return base
    service_rows = int(row["service_rows"] or 0)
    matched_rows = int(row["matched_rows"] or 0)
    exact_rows = int(row["exact_rows"] or 0)
    normalized_rows = int(row["normalized_rows"] or 0)
    output_rows = int(row["output_rows"] or 0)
    raw_type_rows = int(row["raw_type_rows"] or 0)
    unit_rows = int(row["unit_rows"] or 0)
    formula_rows = int(row["formula_rows"] or 0)
    distinct_jobs = int(row["distinct_jobs"] or 0)
    matched_jobs = int(row["matched_jobs"] or 0)
    pct = round((matched_rows * 100 / service_rows), 1) if service_rows else 0
    return {"available": True, "ecu": ecu, "service_rows": service_rows,
            "matched_rows": matched_rows, "exact_rows": exact_rows,
            "normalized_rows": normalized_rows, "output_rows": output_rows,
            "raw_type_rows": raw_type_rows, "unit_rows": unit_rows,
            "formula_rows": formula_rows,
            "missing_rows": max(0, service_rows - matched_rows),
            "distinct_jobs": distinct_jobs, "matched_jobs": matched_jobs,
            "missing_jobs": max(0, distinct_jobs - matched_jobs), "coverage_pct": pct}


def groups_for(ecu: str, lang: str = "ru") -> dict:
    """Measurement + service groups for an ECU: curated .vsg groups, plus an
    auto-generated 'all parameters' group from the CBF."""
    from . import glossary
    e = _norm(ecu)
    tr = _translations(lang)
    meas, serv = [], []
    for g in _index():
        if _norm(g.get("ecu")) != e:
            continue
        steps = sum(1 for s in g.get("services", []) if s.get("kind") == "routine")
        key = g.get("localization_key") or _group_l10n_key(
            g.get("title", ""), g.get("kind", "measurement"))
        item = {"path": g["path"],
                "localization_key": key,
                "title": tr.get(key) or glossary.friendly_title(g["path"], g["title"], lang),
                "raw_title": g["title"], "count": g["count"], "steps": steps,
                "source": g.get("source", "vsg")}
        (serv if g["kind"] == "service" else meas).append(item)
    cg = cbf_group(ecu, lang)
    if cg:
        meas.append({"path": cg["file"], "title": cg["title"],
                     "localization_key": cg["localization_key"],
                     "count": cg["count"], "auto": True})
    return {"ecu": ecu, "coverage": diagnostic_coverage(ecu),
            "measurement": meas, "service": serv}


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


def _db_group(path: str) -> dict | None:
    if not _db_available():
        return None
    try:
        with sqlite3.connect(MEASURE_DB) as db:
            db.row_factory = sqlite3.Row
            gr = db.execute(
                """
                SELECT path, localization_key, source, file, title, ecu, kind, count
                FROM groups WHERE path = ?
                """,
                (path,),
            ).fetchone()
            if not gr:
                return None
            services = []
            has_diag = _table_exists(db, "diag_services")
            has_matches = _table_exists(db, "diag_service_matches")
            has_outputs = _table_exists(db, "service_outputs")
            has_output_value_maps = (
                has_outputs and _table_has_column(db, "service_outputs", "value_map_json")
            )
            has_output_layout = (
                has_outputs and _table_has_column(db, "service_outputs", "bit_pos")
            )
            output_join = """
                    LEFT JOIN service_outputs AS o
                      ON o.ecu = d.ecu
                     AND o.qualifier = d.qualifier
            """ if has_outputs else ""
            if has_outputs:
                output_value_map_expr = (
                    "o.value_map_json" if has_output_value_maps else "''"
                )
                output_layout_cols = (
                    "o.bit_pos AS output_bit_pos, o.bit_len AS output_bit_len, "
                    "o.byte_offset AS output_byte_offset, o.bit_offset AS output_bit_offset"
                    if has_output_layout else
                    "NULL AS output_bit_pos, NULL AS output_bit_len, "
                    "NULL AS output_byte_offset, NULL AS output_bit_offset"
                )
                output_cols = (
                    "o.presentation AS output_presentation, o.raw_type AS output_raw_type, "
                    "o.byte_len AS output_byte_len, o.unit AS output_unit, "
                    "o.scale_kind AS output_scale_kind, o.formula AS output_formula, "
                    f"{output_value_map_expr} AS output_value_map_json, "
                    f"{output_layout_cols}"
                )
            else:
                output_cols = (
                    "NULL AS output_presentation, NULL AS output_raw_type, "
                    "NULL AS output_byte_len, NULL AS output_unit, "
                    "NULL AS output_scale_kind, NULL AS output_formula, "
                    "NULL AS output_value_map_json, NULL AS output_bit_pos, "
                    "NULL AS output_bit_len, NULL AS output_byte_offset, "
                    "NULL AS output_bit_offset"
                )
            if has_diag and has_matches:
                rows = db.execute(
                    f"""
                    SELECT
                      s.localization_key, s.job, s.ecu, s.alias, s.unit, s.kind,
                      s.low, s.high, s.valmap_json,
                      d.request_hex, d.sid, d.sid_hex, d.identifier_type,
                      d.identifier_hex, d.sec_level, d.svc_type, d.name AS diag_name,
                      d.description AS diag_description, d.cbf_file,
                      m.qualifier AS diag_qualifier, m.match_kind AS diag_match_kind,
                      m.rule AS diag_match_rule, m.confidence AS diag_match_confidence,
                      {output_cols}
                    FROM services AS s
                    LEFT JOIN diag_service_matches AS m
                      ON m.ecu = UPPER(REPLACE(CASE WHEN s.ecu <> '' THEN s.ecu ELSE ? END, ' ', ''))
                     AND m.job = s.job
                    LEFT JOIN diag_services AS d
                      ON d.ecu = m.ecu
                     AND d.qualifier = m.qualifier
                    {output_join}
                    WHERE s.group_path = ?
                    ORDER BY s.ord
                    """,
                    (gr["ecu"], path),
                )
            elif has_diag:
                rows = db.execute(
                    f"""
                    SELECT
                      s.localization_key, s.job, s.ecu, s.alias, s.unit, s.kind,
                      s.low, s.high, s.valmap_json,
                      d.request_hex, d.sid, d.sid_hex, d.identifier_type,
                      d.identifier_hex, d.sec_level, d.svc_type, d.name AS diag_name,
                      d.description AS diag_description, d.cbf_file,
                      d.qualifier AS diag_qualifier,
                      CASE WHEN d.qualifier IS NOT NULL THEN 'exact' ELSE NULL END AS diag_match_kind,
                      CASE WHEN d.qualifier IS NOT NULL THEN 'exact' ELSE NULL END AS diag_match_rule,
                      CASE WHEN d.qualifier IS NOT NULL THEN 1.0 ELSE NULL END AS diag_match_confidence,
                      {output_cols}
                    FROM services AS s
                    LEFT JOIN diag_services AS d
                      ON d.ecu = UPPER(REPLACE(CASE WHEN s.ecu <> '' THEN s.ecu ELSE ? END, ' ', ''))
                     AND d.qualifier = s.job
                    {output_join}
                    WHERE s.group_path = ?
                    ORDER BY s.ord
                    """,
                    (gr["ecu"], path),
                )
            else:
                rows = db.execute(
                    """
                    SELECT localization_key, job, ecu, alias, unit, kind, low, high, valmap_json
                    FROM services WHERE group_path = ? ORDER BY ord
                    """,
                    (path,),
                )
            for s in rows:
                valmap = json.loads(s["valmap_json"]) if s["valmap_json"] else None
                item = {
                    "localization_key": s["localization_key"],
                    "job": s["job"], "ecu": s["ecu"], "alias": s["alias"],
                    "unit": s["unit"], "kind": s["kind"], "low": s["low"],
                    "high": s["high"], "valmap": valmap,
                }
                if has_diag and s["request_hex"]:
                    item.update({
                        "req": s["request_hex"],
                        "sid": s["sid"],
                        "sid_hex": s["sid_hex"],
                        "identifier_type": s["identifier_type"],
                        "identifier": s["identifier_hex"],
                        "sec_level": s["sec_level"],
                        "diag_svc_type": s["svc_type"],
                        "diag_name": s["diag_name"] or "",
                        "diag_description": s["diag_description"] or "",
                        "diag_source": s["cbf_file"] or "",
                        "diag_qualifier": s["diag_qualifier"] or s["job"],
                        "diag_match_kind": s["diag_match_kind"] or "exact",
                        "diag_match_rule": s["diag_match_rule"] or "exact",
                        "diag_match_confidence": s["diag_match_confidence"],
                    })
                    if s["output_presentation"]:
                        output_unit = s["output_unit"] or ""
                        output_value_map = []
                        if s["output_value_map_json"]:
                            try:
                                output_value_map = json.loads(s["output_value_map_json"])
                            except json.JSONDecodeError:
                                output_value_map = []
                        if output_unit and not item["unit"]:
                            item["unit"] = output_unit
                        item.update({
                            "output_presentation": s["output_presentation"] or "",
                            "output_raw_type": s["output_raw_type"] or "",
                            "output_byte_len": s["output_byte_len"] or 0,
                            "output_unit": output_unit,
                            "output_scale_kind": s["output_scale_kind"] or "",
                            "output_formula": s["output_formula"] or "",
                            "output_value_map": output_value_map,
                            "value_source": (
                                "enum" if s["output_scale_kind"] == "enum"
                                else "scaled" if s["output_scale_kind"] else "raw"
                            ),
                        })
                        if s["output_bit_pos"] is not None:
                            item.update({
                                "output_bit_pos": s["output_bit_pos"],
                                "output_bit_len": s["output_bit_len"],
                                "output_byte_offset": s["output_byte_offset"],
                                "output_bit_offset": s["output_bit_offset"],
                            })
                services.append(item)
            g = dict(gr)
            g["services"] = services
            return g
    except sqlite3.Error:
        # Generated DB schema can evolve; stale DBs should not break the API.
        return None


def _decorate_group(g: dict, path: str, lang: str) -> dict:
    g["path"] = path
    raw_title = g.get("title", "")
    g["localization_key"] = g.get("localization_key") or _group_l10n_key(
        raw_title, g.get("kind", "measurement"))
    tr = _translations(lang)
    from . import glossary
    g["description"] = glossary.describe_group(path, raw_title, lang)
    g["title"] = tr.get(g["localization_key"]) or glossary.friendly_title(
        path, raw_title, lang)
    for s in g["services"]:
        s["localization_key"] = s.get("localization_key") or _service_l10n_key(s["job"])
        s["label"] = tr.get(s["localization_key"]) or glossary.humanize(
            s["job"], s.get("alias", ""))
        s["note"] = glossary.prefix_note(s["job"])
    return g


def get_group(path: str, lang: str = "ru") -> dict | None:
    if path.startswith("cbf:"):
        g = cbf_group(path[4:], lang)
        if g:
            g["description"] = _CBF_DESC.get(lang, _CBF_DESC["ru"])
        return g
    g = _db_group(path)
    if g:
        return _decorate_group(g, path, lang)
    if path.startswith("mwg:"):
        root = MWG_DIR.resolve()
        full = (MWG_DIR / path[4:]).resolve()
        parser = _mwg.parse_mwg
        source = "mwg"
    else:
        root = VSG_DIR.resolve()
        full = (VSG_DIR / path).resolve()
        parser = _vsg.parse_vsg
        source = "vsg"
    if root != full and root not in full.parents:
        return None
    if not full.exists():
        return None
    g = parser(full)
    g["path"] = path
    g["source"] = source
    return _decorate_group(g, path, lang)


def group_ecu(path: str) -> str | None:
    g = get_group(path)
    return g.get("ecu") if g else None


def _bcd_value(data: bytes):
    digits = []
    for b in data:
        hi, lo = (b >> 4) & 0xF, b & 0xF
        if hi > 9 or lo > 9:
            return data.hex().upper()
        digits.extend([str(hi), str(lo)])
    s = "".join(digits).lstrip("0")
    return int(s or "0")


def _layout_data(resp: bytes, svc: dict | None) -> bytes | None:
    if not svc:
        return None
    bit_pos = svc.get("output_bit_pos")
    bit_len = svc.get("output_bit_len")
    if bit_pos is None or bit_len is None:
        return None
    try:
        bit_pos = int(bit_pos)
        bit_len = int(bit_len)
    except (TypeError, ValueError):
        return None
    if bit_pos < 0 or bit_len <= 0:
        return None
    if bit_pos % 8:
        if not _is_single_bit_output(svc):
            return None
        byte_index = bit_pos // 8
        if byte_index >= len(resp):
            return b""
        return bytes([(resp[byte_index] >> (bit_pos % 8)) & 1])
    if bit_len % 8:
        return None
    start = bit_pos // 8
    end = start + (bit_len // 8)
    if end > len(resp):
        return b""
    return resp[start:end]


def _is_single_bit_output(svc: dict) -> bool:
    raw_type = (svc.get("output_raw_type") or "").lower()
    scale_kind = (svc.get("output_scale_kind") or "").lower()
    formula = (svc.get("output_formula") or "").strip()
    if raw_type == "bool" or scale_kind == "boolean" or formula in {"x != 0", "x == 0"}:
        return True
    if scale_kind != "enum":
        return False
    values = set()
    for entry in svc.get("output_value_map") or []:
        try:
            values.add(int(entry.get("low")))
            values.add(int(entry.get("high")))
        except (TypeError, ValueError, AttributeError):
            return False
    return bool(values) and values <= {0, 1}


def _raw_value(req: bytes, resp: bytes, svc: dict | None = None):
    """Interpret a positive response, using CBF output layout when available."""
    data = _layout_data(resp, svc)
    if data is None:
        n = 3 if req and req[0] == 0x22 else 2 if req and req[0] == 0x21 else 1
        data = resp[n:] if len(resp) > n else b""
    if not data:
        return None
    raw_type = (svc or {}).get("output_raw_type") or ""
    if raw_type == "bcd":
        return _bcd_value(data)
    if raw_type == "ascii":
        return data.decode("latin-1", "replace").rstrip("\x00")
    if raw_type in {"block", "bytes", "hexdump"}:
        return data.hex().upper()
    if len(data) <= 4:
        return int.from_bytes(data, "big")
    return data.hex().upper()


def _apply_output_formula(value, svc: dict) -> tuple[object, str]:
    """Apply only simple, reviewed formula strings from PRES_* metadata."""
    if not isinstance(value, (int, float)):
        return value, "raw"
    if (svc.get("output_scale_kind") or "") == "enum":
        for entry in svc.get("output_value_map") or []:
            try:
                low = entry.get("low")
                high = entry.get("high")
                if low is None or high is None:
                    continue
                if int(low) <= int(value) <= int(high):
                    label = entry.get("label") or ""
                    return (label or value), "enum"
            except (TypeError, ValueError, AttributeError):
                continue
        return value, "enum"
    formula = (svc.get("output_formula") or "").strip()
    if not formula:
        return value, "raw"
    if formula == "x":
        return value, "scaled"
    if formula == "bcd":
        return value, "scaled"
    if formula == "x != 0":
        return bool(value), "enum"
    if formula == "x == 0":
        return not bool(value), "enum"
    m = re.fullmatch(r"x / ([1-9][0-9]*)", formula)
    if m:
        scaled = value / int(m.group(1))
    else:
        m = re.fullmatch(
            r"x \* (-?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+))(?: ([+-]) ([0-9]+(?:\.[0-9]+)?|\.[0-9]+))?",
            formula,
        )
        if not m:
            return value, "raw"
        scaled = value * float(m.group(1))
        if m.group(2):
            offset = float(m.group(3))
            scaled = scaled + offset if m.group(2) == "+" else scaled - offset
    if isinstance(scaled, float) and not scaled.is_integer():
        return round(scaled, 4), "scaled"
    return int(scaled), "scaled"


def read_values(path: str, lang: str = "ru", hw: bool = False, client=None) -> list[dict]:
    """Return current values for a group's data parameters.

    Simulator: synthesize plausible values within each parameter's limits.
    Hardware: TODO scale raw job responses (needs output-presentation parsing);
    for now still synthesizes so the dashboard renders.
    """
    g = get_group(path, lang)
    if not g:
        return []
    cat = None
    t = time.time()
    out = []
    for i, s in enumerate(g["services"]):
        if s["kind"] == "routine":
            continue
        val = None
        value_source = "simulated"
        read_status = "simulated"
        read_reason = ""
        read_req = s.get("req") or ""
        read_sid = s.get("sid_hex") or ""
        # hardware: read the real (raw) value via the job's request bytes
        if hw and client:
            reqhex = s.get("req")
            if not reqhex:
                if cat is None:
                    cat = _diag_cat(g["ecu"])
                reqhex = cat.get(s["job"], {}).get("request")
            guard = _hardware_read_guard(s, reqhex)
            read_status = guard["status"]
            read_reason = guard.get("reason", "")
            read_req = guard.get("req", reqhex or "")
            read_sid = guard.get("sid_hex", "")
            if guard["allowed"]:
                try:
                    rb = bytes.fromhex(guard["req"])
                    val = _raw_value(rb, client.raw_request(rb), s)
                    val, value_source = _apply_output_formula(val, s)
                    read_status = "hw_ok"
                except Exception:  # noqa: BLE001
                    read_status = "error"
                    read_reason = "hardware request failed"
                    val = None
        if val is None:
            lo = s["low"] if s["low"] is not None else 0
            hi = s["high"] if s["high"] is not None else 100
            val = round(lo + (hi - lo) * (0.5 + 0.45 * math.sin(t / 3 + i)), 2)
            if s.get("valmap") and not s["unit"]:
                lbl = s["valmap"].get(int(round(val)))
                if lbl and lbl != "?":
                    val = lbl
        unit = s.get("unit") or s.get("output_unit") or ""
        out.append({"job": s["job"],
                    "localization_key": s.get("localization_key") or _service_l10n_key(s["job"]),
                    "label": s.get("label") or s["job"],
                    "note": s.get("note", ""), "unit": unit, "value": val,
                    "low": s["low"], "high": s["high"], "kind": s["kind"],
                    "value_source": value_source,
                    "read_status": read_status, "read_reason": read_reason,
                    "read_req": read_req, "read_sid": read_sid})
    return out
