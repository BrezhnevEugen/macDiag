#!/usr/bin/env python3
"""Report imported measurement jobs that are not linked to CBF DiagService."""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "measurements.sqlite"

PREFIXES = ("DT_", "ADJ_", "ACT_", "RT_", "FN_", "ON_", "OFF_", "ST_")
READ_SIDS = {"21", "22"}


def _norm_ecu(ecu: str) -> str:
    return (ecu or "").upper().replace(" ", "")


def _table_exists(db: sqlite3.Connection, table: str) -> bool:
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table,),
    ).fetchone() is not None


def _compact(text: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", (text or "").upper())


def _body(text: str) -> str:
    up = (text or "").upper()
    for prefix in PREFIXES:
        if up.startswith(prefix):
            return up[len(prefix):]
    return up


def _prefix(text: str) -> str:
    up = (text or "").upper()
    for prefix in PREFIXES:
        if up.startswith(prefix):
            return prefix[:-1]
    return ""


def _is_read_request(request_hex: str) -> bool:
    req = re.sub(r"[^0-9A-Fa-f]", "", request_hex or "").upper()
    return len(req) >= 2 and req[:2] in READ_SIDS


def _variants(text: str) -> set[str]:
    """Name variants seen between imported MWG/VSG jobs and CBF qualifiers."""
    vals = {text or "", _body(text)}
    out = set()
    for value in vals:
        up = value.upper()
        out.add(_compact(up))
        # Common Caesar qualifier drift in CRD3 data: IO0352 vs IOC352,
        # IOFD08 vs IOCD08. Keep this heuristic only for candidate ranking;
        # exact DB mapping remains strict.
        out.add(_compact(up.replace("IO0", "IOC")))
        out.add(_compact(up.replace("IOF", "IOC")))
        out.add(_compact(up.replace("IOD", "IOC")))
    return {v for v in out if v}


def _tokens(text: str) -> set[str]:
    vals = {text or "", _body(text)}
    out = set()
    for value in vals:
        up = value.upper()
        for variant in (up, up.replace("IO0", "IOC"),
                        up.replace("IOF", "IOC"), up.replace("IOD", "IOC")):
            out.update(re.findall(r"[A-Z0-9]{2,}", variant))
    return {v for v in out if v not in {"DT", "ADJ", "ACT", "RT", "FN", "ON", "OFF", "ST"}}


def _score_variants(lv: set[str], rv: set[str]) -> float:
    if not lv or not rv:
        return 0.0
    if lv & rv:
        return 1.0
    return max(difflib.SequenceMatcher(None, a, b).ratio() for a in lv for b in rv)


def _confidence(score: float) -> str:
    if score >= 0.98:
        return "strong"
    if score >= 0.90:
        return "possible"
    if score >= 0.75:
        return "weak"
    return "none"


def _truncate(text: str, width: int) -> str:
    text = str(text or "")
    return text if len(text) <= width else text[:max(0, width - 1)] + "…"


def _diag_rows(db: sqlite3.Connection, ecu: str) -> list[dict]:
    rows = []
    for r in db.execute(
        """
        SELECT qualifier, request_hex, description
        FROM diag_services
        WHERE ecu = ?
        ORDER BY qualifier
        """,
        (_norm_ecu(ecu),),
    ):
        item = dict(r)
        item["_variants"] = _variants(item["qualifier"])
        item["_tokens"] = _tokens(item["qualifier"])
        rows.append(item)
    return rows


def _rank_candidates(job: str, diag: list[dict], count: int) -> list[dict]:
    job_variants = _variants(job)
    job_tokens = _tokens(job)
    job_prefix = _prefix(job)
    shortlist = []
    for item in diag:
        exact_variant = bool(job_variants & item["_variants"])
        overlap = len(job_tokens & item["_tokens"])
        if exact_variant or overlap >= 2:
            shortlist.append((1000 if exact_variant else overlap, exact_variant, overlap, item))
    shortlist.sort(key=lambda pair: pair[0], reverse=True)
    ranked = []
    for _, exact_variant, overlap, item in shortlist[:500]:
        score = _score_variants(job_variants, item["_variants"])
        cand_prefix = _prefix(item["qualifier"])
        ranked.append({
            "qualifier": item["qualifier"],
            "request_hex": item["request_hex"],
            "description": item["description"] or "",
            "score": round(score, 3),
            "_sort": (
                1 if job_prefix and cand_prefix == job_prefix else 0,
                1 if job_prefix == "DT" and _is_read_request(item["request_hex"]) else 0,
                1 if exact_variant else 0,
                score,
                overlap,
            ),
        })
    ranked.sort(key=lambda item: item["_sort"], reverse=True)
    for item in ranked:
        item.pop("_sort", None)
    return ranked[:max(0, count)]


def unmatched_jobs(db_path: Path, ecu: str, candidates: int = 3) -> dict:
    ecu_key = _norm_ecu(ecu)
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        has_diag = _table_exists(db, "diag_services")
        if not has_diag:
            return {"ecu": ecu_key, "available": False, "jobs": [],
                    "summary": {"reason": "diag_services table is missing"}}
        has_matches = _table_exists(db, "diag_service_matches")
        diag = _diag_rows(db, ecu_key)
        imported_total = db.execute(
            """
            WITH imported AS (
              SELECT
                UPPER(REPLACE(CASE WHEN s.ecu <> '' THEN s.ecu ELSE g.ecu END, ' ', '')) AS ecu,
                s.job AS job
              FROM services AS s
              JOIN groups AS g ON g.path = s.group_path
              WHERE s.job <> ''
            )
            SELECT COUNT(*) AS service_rows, COUNT(DISTINCT job) AS distinct_jobs
            FROM imported
            WHERE ecu = ?
            """,
            (ecu_key,),
        ).fetchone()
        if has_matches:
            missing_join = """
                  LEFT JOIN diag_service_matches AS m
                    ON m.ecu = imported.ecu
                   AND m.job = imported.job
            """
            missing_where = "m.qualifier IS NULL"
        else:
            missing_join = """
                  LEFT JOIN diag_services AS d
                    ON d.ecu = imported.ecu
                   AND d.qualifier = imported.job
            """
            missing_where = "d.qualifier IS NULL"
        rows = [
            dict(r)
            for r in db.execute(
                f"""
                WITH imported AS (
                  SELECT
                    UPPER(REPLACE(CASE WHEN s.ecu <> '' THEN s.ecu ELSE g.ecu END, ' ', '')) AS ecu,
                    s.job AS job,
                    s.alias AS alias,
                    g.title AS title,
                    g.path AS path
                  FROM services AS s
                  JOIN groups AS g ON g.path = s.group_path
                  WHERE s.job <> ''
                ),
                missing AS (
                  SELECT imported.*
                  FROM imported
{missing_join}
                  WHERE imported.ecu = ?
                    AND {missing_where}
                )
                SELECT
                  job,
                  COUNT(*) AS row_count,
                  COUNT(DISTINCT path) AS group_count,
                  MIN(title) AS sample_title,
                  MIN(alias) AS sample_alias,
                  MIN(path) AS sample_path
                FROM missing
                GROUP BY job
                ORDER BY row_count DESC, job
                """,
                (ecu_key,),
            )
        ]

    jobs = []
    confidence_counts = {"strong": 0, "possible": 0, "weak": 0, "none": 0}
    for row in rows:
        ranked = _rank_candidates(row["job"], diag, candidates)
        conf = _confidence(ranked[0]["score"]) if ranked else "none"
        confidence_counts[conf] += 1
        jobs.append({
            "job": row["job"],
            "row_count": int(row["row_count"] or 0),
            "group_count": int(row["group_count"] or 0),
            "sample_title": row["sample_title"] or "",
            "sample_alias": row["sample_alias"] or "",
            "sample_path": row["sample_path"] or "",
            "confidence": conf,
            "candidates": ranked,
        })

    service_rows = int(imported_total["service_rows"] or 0)
    distinct_jobs = int(imported_total["distinct_jobs"] or 0)
    missing_rows = sum(job["row_count"] for job in jobs)
    return {
        "ecu": ecu_key,
        "available": True,
        "summary": {
            "service_rows": service_rows,
            "distinct_jobs": distinct_jobs,
            "missing_rows": missing_rows,
            "missing_jobs": len(jobs),
            "matched_rows": max(0, service_rows - missing_rows),
            "matched_jobs": max(0, distinct_jobs - len(jobs)),
            "confidence": confidence_counts,
        },
        "jobs": jobs,
    }


def _print_report(report: dict, limit: int) -> None:
    summary = report["summary"]
    print(
        f"{report['ecu']}: {summary['missing_jobs']} unmatched jobs / "
        f"{summary['missing_rows']} rows "
        f"(matched rows {summary['matched_rows']} of {summary['service_rows']})"
    )
    print("confidence:", json.dumps(summary["confidence"], sort_keys=True))
    print()
    print("rows  conf      job                                      candidate                                score  request")
    print("----  --------  ---------------------------------------  ---------------------------------------  -----  --------")
    for job in report["jobs"][:limit]:
        cand = job["candidates"][0] if job["candidates"] else {}
        print(
            f"{job['row_count']:4}  {job['confidence'][:8]:8}  "
            f"{_truncate(job['job'], 39):39}  "
            f"{_truncate(cand.get('qualifier', ''), 39):39}  "
            f"{cand.get('score', 0):5.3f}  {cand.get('request_hex', '')}"
        )
        if job["sample_title"]:
            print(f"      group: {_truncate(job['sample_title'], 86)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ecu", help="ECU name, for example CRD3_DEV")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="measurements.sqlite path")
    ap.add_argument("--limit", type=int, default=40, help="rows to print in table mode")
    ap.add_argument("--candidates", type=int, default=3, help="candidate count per job")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    report = unmatched_jobs(Path(args.db), args.ecu, candidates=args.candidates)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report, max(1, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
