#!/usr/bin/env python3
"""
Build macDiag's normalized measurement/service-group SQLite database from local
Vediamo .vsg and Ecoute .mwg sources. When CBF files are provided, also import
CBF DiagService request metadata and build reviewed job -> DiagService matches.

The DB is derived local data and should live under ./data (gitignored). Runtime
code reads this DB first and falls back to raw files only when the DB is absent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import parse_mwg  # noqa: E402
import parse_vsg  # noqa: E402
import caesar_vc  # noqa: E402


DEFAULT_REFERENCES_JSON = (
    ROOT / "data" / "references" / "safari_bookmarks_2026-06-17" / "can_bookmarks.json"
)
DEFAULT_CAN_EXAMPLES_JSON = ROOT / "resources" / "can_examples.json"


SCHEMA = """
PRAGMA journal_mode=OFF;
PRAGMA synchronous=OFF;

CREATE TABLE meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE groups (
  path TEXT PRIMARY KEY,
  localization_key TEXT NOT NULL,
  source TEXT NOT NULL,
  file TEXT NOT NULL,
  title TEXT NOT NULL,
  ecu TEXT NOT NULL,
  kind TEXT NOT NULL,
  count INTEGER NOT NULL,
  relpath TEXT NOT NULL,
  mtime REAL NOT NULL,
  size INTEGER NOT NULL
);

CREATE TABLE services (
  group_path TEXT NOT NULL,
  ord INTEGER NOT NULL,
  localization_key TEXT NOT NULL,
  job TEXT NOT NULL,
  ecu TEXT NOT NULL,
  alias TEXT NOT NULL,
  unit TEXT NOT NULL,
  kind TEXT NOT NULL,
  low REAL,
  high REAL,
  valmap_json TEXT,
  PRIMARY KEY (group_path, ord),
  FOREIGN KEY (group_path) REFERENCES groups(path) ON DELETE CASCADE
);

CREATE INDEX idx_groups_ecu ON groups(ecu);
CREATE INDEX idx_groups_kind ON groups(kind);
CREATE INDEX idx_services_job ON services(job);
CREATE INDEX idx_groups_l10n ON groups(localization_key);
CREATE INDEX idx_services_l10n ON services(localization_key);

CREATE TABLE diag_services (
  ecu TEXT NOT NULL,
  qualifier TEXT NOT NULL,
  request_hex TEXT NOT NULL,
  sid INTEGER,
  sid_hex TEXT NOT NULL,
  identifier_type TEXT NOT NULL,
  identifier_hex TEXT NOT NULL,
  sec_level INTEGER,
  svc_type INTEGER,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  cbf_file TEXT NOT NULL,
  PRIMARY KEY (ecu, qualifier)
);

CREATE INDEX idx_diag_services_qualifier ON diag_services(qualifier);

CREATE TABLE diag_service_matches (
  ecu TEXT NOT NULL,
  job TEXT NOT NULL,
  qualifier TEXT NOT NULL,
  match_kind TEXT NOT NULL,
  rule TEXT NOT NULL,
  confidence REAL NOT NULL,
  PRIMARY KEY (ecu, job)
);

CREATE INDEX idx_diag_service_matches_qualifier ON diag_service_matches(ecu, qualifier);

CREATE TABLE service_outputs (
  ecu TEXT NOT NULL,
  qualifier TEXT NOT NULL,
  presentation TEXT NOT NULL,
  raw_type TEXT NOT NULL,
  byte_len INTEGER NOT NULL,
  unit TEXT NOT NULL DEFAULT '',
  scale_kind TEXT NOT NULL DEFAULT '',
  formula TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL,
  PRIMARY KEY (ecu, qualifier)
);

CREATE INDEX idx_service_outputs_presentation ON service_outputs(presentation);

CREATE TABLE translations (
  localization_key TEXT NOT NULL,
  lang TEXT NOT NULL,
  text TEXT NOT NULL,
  context TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (localization_key, lang)
);

CREATE TABLE reference_links (
  url TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  domain TEXT NOT NULL,
  tags_json TEXT NOT NULL,
  folders_json TEXT NOT NULL,
  sources_json TEXT NOT NULL,
  vehicle_hints_json TEXT NOT NULL,
  attrs_json TEXT NOT NULL,
  source_file TEXT NOT NULL
);

CREATE INDEX idx_reference_links_domain ON reference_links(domain);

CREATE TABLE can_examples (
  id TEXT PRIMARY KEY,
  source_url TEXT NOT NULL,
  source_title TEXT NOT NULL,
  vehicle TEXT NOT NULL,
  body TEXT NOT NULL,
  bus TEXT NOT NULL,
  speed_kbit_s REAL,
  can_id TEXT NOT NULL,
  dlc INTEGER,
  data_hex TEXT NOT NULL,
  source_node TEXT NOT NULL,
  target_node TEXT NOT NULL,
  direction TEXT NOT NULL,
  payload_meaning TEXT NOT NULL,
  tags_json TEXT NOT NULL,
  confidence TEXT NOT NULL,
  safety_note TEXT NOT NULL,
  notes TEXT NOT NULL
);

CREATE INDEX idx_can_examples_vehicle ON can_examples(vehicle);
CREATE INDEX idx_can_examples_can_id ON can_examples(can_id);
"""


def _iter_groups(vsg_dir: Path, mwg_dir: Path):
    if vsg_dir.exists():
        for p in sorted(vsg_dir.rglob("*.vsg")):
            yield "vsg", str(p.relative_to(vsg_dir)), p, parse_vsg.parse_vsg
    if mwg_dir.exists():
        for p in sorted(mwg_dir.rglob("*.mwg")):
            rel = str(p.relative_to(mwg_dir))
            yield "mwg", "mwg:" + rel, p, parse_mwg.parse_mwg


def _norm_ecu(ecu: str) -> str:
    return (ecu or "").upper().replace(" ", "")


def _norm_qualifier(qualifier: str) -> str:
    return (qualifier or "").upper()


def _cbf_files(cbf_dir: Path | None) -> dict[str, Path]:
    if not cbf_dir or not cbf_dir.exists():
        return {}
    out: dict[str, Path] = {}
    for p in sorted(cbf_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() == ".cbf":
            out.setdefault(_norm_ecu(p.stem), p)
    return out


def _request_meta(request_hex: str) -> dict:
    req_hex = re.sub(r"[^0-9A-Fa-f]", "", request_hex or "").upper()
    if not req_hex:
        return {"request_hex": "", "sid": None, "sid_hex": "",
                "identifier_type": "", "identifier_hex": ""}
    try:
        req = bytes.fromhex(req_hex)
    except ValueError:
        return {"request_hex": "", "sid": None, "sid_hex": "",
                "identifier_type": "", "identifier_hex": ""}
    if not req:
        return {"request_hex": "", "sid": None, "sid_hex": "",
                "identifier_type": "", "identifier_hex": ""}
    sid = req[0]
    ident_type = ""
    ident_hex = ""
    if sid in (0x21, 0x3B) and len(req) >= 2:
        ident_type = "lid"
        ident_hex = f"{req[1]:02X}"
    elif sid in (0x22, 0x2E) and len(req) >= 3:
        ident_type = "did"
        ident_hex = f"{((req[1] << 8) | req[2]):04X}"
    elif sid == 0x31 and len(req) >= 4:
        ident_type = "routine_id"
        ident_hex = req[2:4].hex().upper()
    return {"request_hex": req_hex, "sid": sid, "sid_hex": f"{sid:02X}",
            "identifier_type": ident_type, "identifier_hex": ident_hex}


def _diag_for_ecu(ecu: str, cbf_by_ecu: dict[str, Path],
                  cache: dict[str, dict], stats: dict) -> dict:
    key = _norm_ecu(ecu)
    if not key:
        return {}
    if key in cache:
        return cache[key]
    p = cbf_by_ecu.get(key)
    if not p:
        stats["diag_cbf_missing_ecus"] += 1
        cache[key] = {}
        return {}
    try:
        cat = caesar_vc.diag_catalog(p)
    except Exception:  # noqa: BLE001
        stats["diag_parse_errors"] += 1
        cache[key] = {}
        return {}
    cache[key] = cat
    stats["diag_ecus"] += 1
    return cat


def _insert_diag_service(conn: sqlite3.Connection, ecu: str, qualifier: str,
                         info: dict, cbf_file: Path) -> None:
    req_meta = _request_meta(info.get("request") or "")
    if not req_meta["request_hex"]:
        return
    conn.execute(
        """
        INSERT OR IGNORE INTO diag_services(
          ecu, qualifier, request_hex, sid, sid_hex, identifier_type,
          identifier_hex, sec_level, svc_type, name, description, cbf_file
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (_norm_ecu(ecu), qualifier, req_meta["request_hex"], req_meta["sid"],
         req_meta["sid_hex"], req_meta["identifier_type"],
         req_meta["identifier_hex"], info.get("sec_level"), info.get("svc_type"),
         info.get("name") or "", info.get("description") or "", str(cbf_file)),
    )
    _insert_service_output(conn, ecu, qualifier, info)


def _insert_service_output(conn: sqlite3.Connection, ecu: str, qualifier: str,
                           info: dict) -> None:
    presentation = info.get("presentation") or ""
    if not presentation:
        return
    meta = caesar_vc.presentation_meta(presentation)
    raw_type = info.get("presentation_raw_type") or meta["raw_type"]
    byte_len = int(info.get("presentation_byte_len") or meta["byte_len"] or 0)
    unit = info.get("presentation_unit") or meta["unit"]
    scale_kind = info.get("presentation_scale_kind") or meta["scale_kind"]
    formula = info.get("presentation_formula") or meta["formula"]
    source = "cbf_diag_inline"
    meta_source = info.get("presentation_meta_source") or (
        "presentation_name" if (unit or formula) else ""
    )
    if meta_source:
        source += "+" + meta_source
    conn.execute(
        """
        INSERT OR IGNORE INTO service_outputs(
          ecu, qualifier, presentation, raw_type, byte_len, unit, scale_kind, formula, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (_norm_ecu(ecu), qualifier, presentation, raw_type, byte_len,
         unit, scale_kind, formula, source),
    )


def _insert_diag_catalog(conn: sqlite3.Connection, ecu: str, diag: dict,
                         cbf_file: Path) -> None:
    for qualifier, info in diag.items():
        _insert_diag_service(conn, ecu, qualifier, info, cbf_file)


def _diag_lookup(diag: dict) -> dict[str, tuple[str, dict]]:
    return {_norm_qualifier(qualifier): (qualifier, info)
            for qualifier, info in diag.items()}


def _is_read_request(info: dict) -> bool:
    meta = _request_meta(info.get("request") or "")
    return meta["sid"] in (0x21, 0x22)


def _dt_ioc_candidates(job: str) -> list[tuple[str, str]]:
    up = _norm_qualifier(job)
    if not up.startswith("DT_"):
        return []
    out = []
    for src in ("IO0", "IOF", "IOD"):
        if src in up:
            out.append((up.replace(src, "IOC"), f"dt_{src.lower()}_to_ioc"))
    return out


def _diag_match(job: str, diag: dict, lookup: dict[str, tuple[str, dict]]) -> dict | None:
    """Return a reviewed service match. Exact always wins; normalization is
    intentionally narrow and read-only for now."""
    if not job:
        return None
    info = diag.get(job)
    if info and _request_meta(info.get("request") or "")["request_hex"]:
        return {"qualifier": job, "info": info, "match_kind": "exact",
                "rule": "exact", "confidence": 1.0}
    for candidate, rule in _dt_ioc_candidates(job):
        found = lookup.get(candidate)
        if not found:
            continue
        qualifier, info = found
        if not _norm_qualifier(qualifier).startswith("DT_"):
            continue
        if _is_read_request(info):
            return {"qualifier": qualifier, "info": info, "match_kind": "normalized",
                    "rule": rule, "confidence": 1.0}
    return None


def _insert_diag_match(conn: sqlite3.Connection, ecu: str, job: str, match: dict) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO diag_service_matches(
          ecu, job, qualifier, match_kind, rule, confidence
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (_norm_ecu(ecu), job, match["qualifier"], match["match_kind"],
         match["rule"], match["confidence"]),
    )


def _slug(s: str) -> str:
    norm = unicodedata.normalize("NFKD", s or "")
    ascii_s = norm.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_s).strip("_")
    return (slug or "item")[:80]


def _l10n_key(namespace: str, semantic_id: str) -> str:
    digest = hashlib.sha1((semantic_id or "").encode("utf-8")).hexdigest()[:10]
    return f"{namespace}.{_slug(semantic_id)}.{digest}"


def group_l10n_key(title: str, kind: str) -> str:
    return _l10n_key("measure.group", f"{kind}:{title}")


def service_l10n_key(job: str) -> str:
    return _l10n_key("measure.service", job)


def _vehicle_hints(row: dict) -> list[str]:
    haystack = " ".join([
        row.get("title") or "",
        row.get("url") or "",
        " ".join(row.get("folders") or []),
    ]).upper()
    hints = set(re.findall(r"\b[WXCVR]\s?\d{3}\b", haystack))
    hints |= set(re.findall(r"\bE\s?211\b", haystack))
    return sorted({h.replace(" ", "") for h in hints})


def _insert_reference_links(conn: sqlite3.Connection,
                            references_json: Path | None) -> int:
    if not references_json or not references_json.exists():
        return 0
    try:
        data = json.loads(references_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    rows = data.get("bookmarks") or []
    inserted = 0
    for row in rows:
        url = (row.get("url") or "").strip()
        if not url:
            continue
        title = (row.get("title") or url).strip()
        domain = (row.get("domain") or urlparse(url).netloc).strip()
        conn.execute(
            """
            INSERT OR REPLACE INTO reference_links(
              url, title, domain, tags_json, folders_json, sources_json,
              vehicle_hints_json, attrs_json, source_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                url,
                title,
                domain,
                json.dumps(row.get("tags") or [], ensure_ascii=False),
                json.dumps(row.get("folders") or [], ensure_ascii=False),
                json.dumps(row.get("sources") or [], ensure_ascii=False),
                json.dumps(_vehicle_hints(row), ensure_ascii=False),
                json.dumps(row.get("attrs") or {}, ensure_ascii=False),
                str(references_json),
            ),
        )
        inserted += 1
    return inserted


def _insert_can_examples(conn: sqlite3.Connection,
                         can_examples_json: Path | None) -> int:
    if not can_examples_json or not can_examples_json.exists():
        return 0
    try:
        data = json.loads(can_examples_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    rows = data.get("examples") or []
    inserted = 0
    for row in rows:
        example_id = (row.get("id") or "").strip()
        source_url = (row.get("source_url") or "").strip()
        if not example_id or not source_url:
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO can_examples(
              id, source_url, source_title, vehicle, body, bus, speed_kbit_s,
              can_id, dlc, data_hex, source_node, target_node, direction,
              payload_meaning, tags_json, confidence, safety_note, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                example_id,
                source_url,
                row.get("source_title") or "",
                row.get("vehicle") or "",
                row.get("body") or "",
                row.get("bus") or "",
                row.get("speed_kbit_s"),
                (row.get("can_id") or "").upper().replace("0X", "0x"),
                row.get("dlc"),
                (row.get("data_hex") or "").upper(),
                row.get("source_node") or "",
                row.get("target_node") or "",
                row.get("direction") or "",
                row.get("payload_meaning") or "",
                json.dumps(row.get("tags") or [], ensure_ascii=False),
                row.get("confidence") or "reviewed",
                row.get("safety_note") or "",
                row.get("notes") or "",
            ),
        )
        inserted += 1
    return inserted


def build(vsg_dir: Path, mwg_dir: Path, out: Path,
          cbf_dir: Path | None = None,
          references_json: Path | None = None,
          can_examples_json: Path | None = None) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()

    stats = {"groups": 0, "services": 0, "vsg": 0, "mwg": 0, "skipped": 0,
             "diag_ecus": 0, "diag_cbf_files": 0, "diag_services": 0,
             "diag_matched_services": 0, "diag_exact_matched_services": 0,
             "diag_normalized_matched_services": 0, "diag_unmatched_services": 0,
             "diag_cbf_missing_ecus": 0, "diag_parse_errors": 0,
             "output_presentations": 0, "output_raw_types": 0,
             "output_units": 0, "output_formulas": 0,
             "reference_links": 0, "can_examples": 0}
    cbf_by_ecu = _cbf_files(cbf_dir)
    stats["diag_cbf_files"] = len(cbf_by_ecu)
    diag_cache: dict[str, dict] = {}
    diag_lookup_cache: dict[str, dict[str, tuple[str, dict]]] = {}
    diag_inserted_ecus: set[str] = set()
    conn = sqlite3.connect(tmp)
    try:
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO meta(key, value) VALUES (?, ?)", ("schema_version", "11"))
        conn.execute("INSERT INTO meta(key, value) VALUES (?, ?)", ("built_at", str(time.time())))
        conn.execute("INSERT INTO meta(key, value) VALUES (?, ?)", ("vsg_dir", str(vsg_dir)))
        conn.execute("INSERT INTO meta(key, value) VALUES (?, ?)", ("mwg_dir", str(mwg_dir)))
        if cbf_dir:
            conn.execute("INSERT INTO meta(key, value) VALUES (?, ?)", ("cbf_dir", str(cbf_dir)))
        if references_json:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?)",
                ("references_json", str(references_json)),
            )
        if can_examples_json:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?)",
                ("can_examples_json", str(can_examples_json)),
            )

        for source, path, file_path, parser in _iter_groups(vsg_dir, mwg_dir):
            try:
                g = parser(file_path)
            except Exception:  # noqa: BLE001
                stats["skipped"] += 1
                continue
            services = g.get("services") or []
            if not services:
                stats["skipped"] += 1
                continue
            st = file_path.stat()
            group_key = group_l10n_key(g.get("title") or file_path.stem,
                                       g.get("kind") or "measurement")
            conn.execute(
                """
                INSERT INTO groups(
                  path, localization_key, source, file, title, ecu, kind, count, relpath, mtime, size
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (path, group_key, source, g.get("file") or file_path.name,
                 g.get("title") or file_path.stem,
                 g.get("ecu") or "", g.get("kind") or "measurement", len(services),
                 str(file_path), st.st_mtime, st.st_size),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO translations(localization_key, lang, text, context)
                VALUES (?, 'source', ?, ?)
                """,
                (group_key, g.get("title") or file_path.stem,
                 f"measurement group title; source={source}; ecu={g.get('ecu') or ''}"),
            )
            for i, svc in enumerate(services):
                valmap = svc.get("valmap")
                service_key = service_l10n_key(svc.get("job") or "")
                conn.execute(
                    """
                    INSERT INTO services(
                      group_path, ord, localization_key, job, ecu, alias, unit,
                      kind, low, high, valmap_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (path, i, service_key, svc.get("job") or "", svc.get("ecu") or "",
                     svc.get("alias") or "", svc.get("unit") or "",
                     svc.get("kind") or "data", svc.get("low"), svc.get("high"),
                    json.dumps(valmap, ensure_ascii=False) if valmap else None),
                )
                diag_ecu = svc.get("ecu") or g.get("ecu") or ""
                if cbf_by_ecu and diag_ecu:
                    diag = _diag_for_ecu(diag_ecu, cbf_by_ecu, diag_cache, stats)
                    diag_key = _norm_ecu(diag_ecu)
                    if diag and diag_key not in diag_inserted_ecus:
                        _insert_diag_catalog(conn, diag_ecu, diag, cbf_by_ecu[diag_key])
                        diag_inserted_ecus.add(diag_key)
                    lookup = diag_lookup_cache.setdefault(diag_key, _diag_lookup(diag))
                    match = _diag_match(svc.get("job") or "", diag, lookup)
                    if match:
                        _insert_diag_match(conn, diag_ecu, svc.get("job") or "", match)
                        stats["diag_matched_services"] += 1
                        if match["match_kind"] == "normalized":
                            stats["diag_normalized_matched_services"] += 1
                        else:
                            stats["diag_exact_matched_services"] += 1
                    else:
                        stats["diag_unmatched_services"] += 1
                conn.execute(
                    """
                    INSERT OR IGNORE INTO translations(localization_key, lang, text, context)
                    VALUES (?, 'source', ?, ?)
                    """,
                    (service_key, svc.get("alias") or svc.get("job") or "",
                     f"measurement service label; job={svc.get('job') or ''}; unit={svc.get('unit') or ''}"),
                )
            stats["groups"] += 1
            stats["services"] += len(services)
            stats[source] += 1

        stats["diag_services"] = conn.execute(
            "SELECT COUNT(*) FROM diag_services"
        ).fetchone()[0]
        stats["output_presentations"] = conn.execute(
            "SELECT COUNT(*) FROM service_outputs"
        ).fetchone()[0]
        stats["output_raw_types"] = conn.execute(
            "SELECT COUNT(*) FROM service_outputs WHERE raw_type <> ''"
        ).fetchone()[0]
        stats["output_units"] = conn.execute(
            "SELECT COUNT(*) FROM service_outputs WHERE unit <> ''"
        ).fetchone()[0]
        stats["output_formulas"] = conn.execute(
            "SELECT COUNT(*) FROM service_outputs WHERE formula <> ''"
        ).fetchone()[0]
        stats["reference_links"] = _insert_reference_links(conn, references_json)
        stats["can_examples"] = _insert_can_examples(conn, can_examples_json)
        conn.commit()
    finally:
        conn.close()
    os.replace(tmp, out)
    stats["out"] = str(out)
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vsg-dir", default=str(ROOT / "data" / "vsg"))
    ap.add_argument("--mwg-dir", default=str(ROOT / "data" / "vediamo_raw"))
    ap.add_argument("--cbf-dir", default=str(ROOT / "data" / "cbf"),
                    help="optional CBF directory for job -> DiagService request metadata")
    ap.add_argument("--references-json", default=str(DEFAULT_REFERENCES_JSON),
                    help="optional filtered reference links JSON to import")
    ap.add_argument("--can-examples-json", default=str(DEFAULT_CAN_EXAMPLES_JSON),
                    help="optional reviewed CAN examples JSON to import")
    ap.add_argument("--out", default=str(ROOT / "data" / "measurements.sqlite"))
    args = ap.parse_args(argv)

    stats = build(Path(args.vsg_dir), Path(args.mwg_dir), Path(args.out),
                  Path(args.cbf_dir) if args.cbf_dir else None,
                  Path(args.references_json) if args.references_json else None,
                  Path(args.can_examples_json) if args.can_examples_json else None)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
