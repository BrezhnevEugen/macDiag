#!/usr/bin/env python3
"""
Export/import measurement translation dictionaries for data/measurements.sqlite.

Typical flow:

  python3 tools/manage_measure_translations.py export --lang ru \
    --out data/translations/measurements_ru.csv

  # edit the "translation" column while keeping localization_key/source/context

  python3 tools/manage_measure_translations.py import --lang ru \
    --input data/translations/measurements_ru.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "measurements.sqlite"

FIELDS = ["localization_key", "kind", "lang", "source_text", "translation", "context"]


def _connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def export_csv(db_path: Path, lang: str, out_path: Path,
               missing_only: bool = False, prefix: str = "") -> dict:
    """Write a translation workfile for a target language."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    where = ["source.lang = 'source'"]
    params: list[str] = [lang]
    if missing_only:
        where.append("(target.text IS NULL OR target.text = '')")
    if prefix:
        where.append("source.localization_key LIKE ?")
        params.append(f"{prefix}%")

    sql = f"""
        SELECT
          source.localization_key,
          CASE
            WHEN source.localization_key LIKE 'measure.group.%' THEN 'group'
            WHEN source.localization_key LIKE 'measure.service.%' THEN 'service'
            ELSE 'other'
          END AS kind,
          source.text AS source_text,
          COALESCE(target.text, '') AS translation,
          source.context AS context
        FROM translations AS source
        LEFT JOIN translations AS target
          ON target.localization_key = source.localization_key
         AND target.lang = ?
        WHERE {' AND '.join(where)}
        ORDER BY kind, source.localization_key
    """

    written = 0
    with _connect(db_path) as db, out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in db.execute(sql, params):
            writer.writerow({
                "localization_key": row["localization_key"],
                "kind": row["kind"],
                "lang": lang,
                "source_text": row["source_text"],
                "translation": row["translation"],
                "context": row["context"],
            })
            written += 1
    return {"written": written, "out": str(out_path), "lang": lang}


def import_csv(db_path: Path, lang: str, in_path: Path,
               delete_empty: bool = False, dry_run: bool = False) -> dict:
    """Upsert translated rows from a CSV workfile."""
    stats = {
        "upserted": 0,
        "deleted": 0,
        "skipped_empty": 0,
        "skipped_lang": 0,
        "skipped_invalid": 0,
        "dry_run": dry_run,
        "lang": lang,
    }
    with _connect(db_path) as db, in_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row.get("localization_key") or "").strip()
            row_lang = (row.get("lang") or lang).strip()
            text = ((row.get("translation") or row.get("translated_text")
                     or row.get("text") or "")).strip()
            context = row.get("context") or ""

            if not key:
                stats["skipped_invalid"] += 1
                continue
            if row_lang and row_lang != lang:
                stats["skipped_lang"] += 1
                continue
            if not text:
                if delete_empty:
                    if not dry_run:
                        db.execute(
                            "DELETE FROM translations WHERE localization_key = ? AND lang = ?",
                            (key, lang),
                        )
                    stats["deleted"] += 1
                else:
                    stats["skipped_empty"] += 1
                continue
            if not dry_run:
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
            stats["upserted"] += 1
        if not dry_run:
            db.commit()
    return stats


def stats(db_path: Path, lang: str = "") -> dict:
    with _connect(db_path) as db:
        by_lang = {
            r["lang"]: r["count"]
            for r in db.execute(
                "SELECT lang, COUNT(*) AS count FROM translations GROUP BY lang ORDER BY lang"
            )
        }
        out = {"languages": by_lang}
        if lang:
            row = db.execute(
                """
                SELECT
                  COUNT(source.localization_key) AS source_count,
                  COUNT(target.localization_key) AS translated_count
                FROM translations AS source
                LEFT JOIN translations AS target
                  ON target.localization_key = source.localization_key
                 AND target.lang = ?
                WHERE source.lang = 'source'
                """,
                (lang,),
            ).fetchone()
            out["lang"] = lang
            out["source_count"] = row["source_count"]
            out["translated_count"] = row["translated_count"]
            out["missing_count"] = row["source_count"] - row["translated_count"]
        return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(DEFAULT_DB), help="measurements.sqlite path")
    sub = ap.add_subparsers(dest="cmd", required=True)

    exp = sub.add_parser("export", help="export CSV workfile")
    exp.add_argument("--lang", required=True)
    exp.add_argument("--out", required=True)
    exp.add_argument("--missing-only", action="store_true")
    exp.add_argument("--prefix", default="", help="optional localization_key prefix filter")

    imp = sub.add_parser("import", help="import translated CSV")
    imp.add_argument("--lang", required=True)
    imp.add_argument("--input", required=True)
    imp.add_argument("--delete-empty", action="store_true")
    imp.add_argument("--dry-run", action="store_true")

    st = sub.add_parser("stats", help="show translation coverage")
    st.add_argument("--lang", default="")

    args = ap.parse_args(argv)
    db_path = Path(args.db)
    if args.cmd == "export":
        result = export_csv(db_path, args.lang, Path(args.out), args.missing_only, args.prefix)
    elif args.cmd == "import":
        result = import_csv(db_path, args.lang, Path(args.input), args.delete_empty, args.dry_run)
    else:
        result = stats(db_path, args.lang)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
