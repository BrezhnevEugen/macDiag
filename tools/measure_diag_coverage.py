#!/usr/bin/env python3
"""Report MWG/VSG job coverage by CBF DiagService request metadata."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "measurements.sqlite"


def _norm_ecu(ecu: str) -> str:
    return (ecu or "").upper().replace(" ", "")


def _table_exists(db: sqlite3.Connection, table: str) -> bool:
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table,),
    ).fetchone() is not None


def coverage_rows(db_path: Path, ecus: list[str] | None = None) -> list[dict]:
    targets = {_norm_ecu(e) for e in (ecus or []) if e}
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        has_diag = _table_exists(db, "diag_services")
        if not has_diag:
            return []
        has_matches = _table_exists(db, "diag_service_matches")
        has_outputs = _table_exists(db, "service_outputs")
        where = ""
        params: list[object] = []
        if targets:
            where = "WHERE imported.ecu IN (%s)" % ",".join("?" for _ in targets)
            params = sorted(targets)
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
        rows = []
        for r in db.execute(
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
              imported.ecu,
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
            GROUP BY imported.ecu
            ORDER BY matched_rows * 1.0 / NULLIF(service_rows, 0) DESC, imported.ecu
            """,
            params,
        ):
            service_rows = int(r["service_rows"] or 0)
            matched_rows = int(r["matched_rows"] or 0)
            exact_rows = int(r["exact_rows"] or 0)
            normalized_rows = int(r["normalized_rows"] or 0)
            output_rows = int(r["output_rows"] or 0)
            raw_type_rows = int(r["raw_type_rows"] or 0)
            unit_rows = int(r["unit_rows"] or 0)
            formula_rows = int(r["formula_rows"] or 0)
            distinct_jobs = int(r["distinct_jobs"] or 0)
            matched_jobs = int(r["matched_jobs"] or 0)
            rows.append({
                "ecu": r["ecu"],
                "service_rows": service_rows,
                "matched_rows": matched_rows,
                "exact_rows": exact_rows,
                "normalized_rows": normalized_rows,
                "output_rows": output_rows,
                "raw_type_rows": raw_type_rows,
                "unit_rows": unit_rows,
                "formula_rows": formula_rows,
                "missing_rows": max(0, service_rows - matched_rows),
                "distinct_jobs": distinct_jobs,
                "matched_jobs": matched_jobs,
                "missing_jobs": max(0, distinct_jobs - matched_jobs),
                "coverage_pct": round(matched_rows * 100 / service_rows, 1)
                if service_rows else 0,
            })
        return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ecu", nargs="*", help="optional ECU names to filter")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="measurements.sqlite path")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = ap.parse_args(argv)

    rows = coverage_rows(Path(args.db), args.ecu)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    print(
        "ECU                 rows     matched  exact    norm     output   rawtype  unit     formula  missing  jobs     coverage"
    )
    print(
        "------------------  -------  -------  -------  -------  -------  -------  -------  -------  -------  -------  --------"
    )
    for r in rows:
        print(
            f"{r['ecu'][:18]:18}  {r['service_rows']:7}  {r['matched_rows']:7}  "
            f"{r.get('exact_rows', 0):7}  {r.get('normalized_rows', 0):7}  "
            f"{r.get('output_rows', 0):7}  {r.get('raw_type_rows', 0):7}  "
            f"{r.get('unit_rows', 0):7}  {r.get('formula_rows', 0):7}  "
            f"{r['missing_rows']:7}  {r['distinct_jobs']:7}  "
            f"{r['coverage_pct']:6.1f}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
