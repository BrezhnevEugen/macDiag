#!/usr/bin/env python3
"""
Seed high-confidence Russian measurement translations into measurements.sqlite.

This is intentionally conservative: it translates common diagnostic terms,
German group titles and readable job identifiers, while leaving unclear strings
for manual review in data/translations/*.csv.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "measurements.sqlite"
MARKER = "auto_seed=measure_ru_glossary_v1"

EXACT = {
    "abgas": "отработавшие газы",
    "abgasklappe": "заслонка ОГ",
    "abgasruckfuhrung": "EGR / рециркуляция ОГ",
    "abgasrueckfuehrung": "EGR / рециркуляция ОГ",
    "abgasrückführung": "EGR / рециркуляция ОГ",
    "abgleiche lesen": "чтение адаптаций",
    "adaptionsverfahren fur cop ab c2n": "процедура адаптации COP с C2N",
    "adaptionsverfahren für cop ab c2n": "процедура адаптации COP с C2N",
    "agr hp": "EGR высокого давления",
    "agr lp": "EGR низкого давления",
    "ald einlernen": "обучение ALD",
    "allgemein": "общие параметры",
    "batteriespannung": "напряжение АКБ",
    "code und datenstand": "кодировка и версия данных",
    "dieseldaten": "данные дизельного двигателя",
    "drehzahl": "обороты двигателя",
    "einspritzmenge": "количество впрыска",
    "fahrpedalstellung": "положение педали акселератора",
    "ladedruck": "давление наддува",
    "ladedruck sollwert": "заданное давление наддува",
    "ladedruckregelklappe": "заслонка регулирования наддува",
    "ladedruckregelklappe return control": "контроль обратного хода заслонки наддува",
    "luftmasse": "масса воздуха",
    "motor starten": "запустить двигатель",
    "raildruck": "давление в топливной рампе",
    "solldrehzahl": "заданные обороты",
    "status": "статус",
    "waste gate": "вестгейт",
    "waste gate return control": "контроль обратного хода вестгейта",
    "wassertemperatur": "температура ОЖ",
}

PHRASES = [
    (r"\bdpf\b.*\bcontinuous\b.*\bsimulated\b.*\bsoot\b.*\bmass\b", "расчётная масса сажи DPF"),
    (r"\bdpf\b.*\bmileage\b.*\blast\b.*\bsuccessful\b", "пробег с последней успешной регенерации DPF"),
    (r"\bdpf\b.*\bageing\b.*\bfctr\b|\bdpf\b.*\bageing\b.*\bfactor\b", "коэффициент старения DPF"),
    (r"\bdpf\b.*\bsoot\b.*\bmass\b|\bruss\b.*\bmasse\b|\bdpf\b.*\brus", "масса сажи DPF"),
    (r"\bdpf\b.*\bload\b.*\bpercent\b|\bdpf\b.*\bbelad", "загрузка DPF"),
    (r"\bdpf\b.*\bdifferential\b.*\bpressure\b|\bdpf\b.*\bdiff.*druck", "перепад давления DPF"),
    (r"\bdpf\b.*\bash(es)?\b.*\bmass\b|\basche\b.*\bdpf", "масса золы DPF"),
    (r"\bdpf\b.*\bregeneration\b|\bpartikelfilter\b.*\breg", "регенерация DPF"),
    (r"\bboost\b.*\bpressure\b|\bladedruck\b", "давление наддува"),
    (r"\brail\b.*\bpressure\b|\braildruck\b", "давление в топливной рампе"),
    (r"\bfuel\b.*\bfilter\b|\bkraftstofffilter\b", "топливный фильтр"),
    (r"\bfuel\b.*\bpump\b|\bkraftstoffpumpe\b", "топливный насос"),
    (r"\bfuel\b.*\bquantity\b|\beinspritzmenge\b|\binj.*\bq", "количество впрыска"),
    (r"\bidle\b.*\bspeed\b|\bleerlauf\b.*\bdrehzahl\b|\bll\b.*\bsolldrehzahl\b", "обороты холостого хода"),
    (r"\bengine\b.*\bspeed\b|\bdrehzahl\b", "обороты двигателя"),
    (r"\bvehicle\b.*\bspeed\b|\bveh\b.*\bspeed\b|\bgeschwindigkeit\b", "скорость автомобиля"),
    (r"\bpedal\b.*\bposition\b|\bfahrpedalstellung\b|\bpwg\b.*\bsensor\b|\bapp\b", "положение педали акселератора"),
    (r"\bbattery\b.*\bvoltage\b|\bbatteriespannung\b", "напряжение АКБ"),
    (r"\bwater\b.*\btemperature\b|\bwassertemperatur\b|\bcoolant\b.*\btemp", "температура ОЖ"),
    (r"\boil\b.*\btemperature\b|\boeltemperatur\b|\böltemperatur\b", "температура масла"),
    (r"\bair\b.*\bmass\b|\bluftmasse\b", "масса воздуха"),
    (r"\bair\b.*\btemperature\b|\blufttemperatur\b", "температура воздуха"),
    (r"\bexhaust\b.*\bgas\b.*\bflap\b|\babgasklappe\b", "заслонка ОГ"),
    (r"\bglow\b.*\bplug\b|\bglow\b.*\bcontrol\b|\bglueh\b|\bglüh", "управление свечами накаливания"),
    (r"\bthrottle\b.*\bvalve\b|\bdrossel", "дроссельная заслонка"),
    (r"\bactuator\b.*\blearning\b|\baktoren\b.*\blernen\b", "обучение актуаторов"),
    (r"\badblue\b|\bscr\b", "SCR / AdBlue"),
    (r"\begr\b|\bagr\b", "EGR"),
    (r"\bstartanforderer\b", "запросы запуска"),
    (r"\bvorbedingungen\b", "предусловия"),
    (r"\bfehlerstatus\b", "статус ошибок"),
    (r"\bdatenstand\b", "версия данных"),
    (r"\bcode\b.*\bdatenstand\b", "кодировка и версия данных"),
]

TOKEN_MAP = {
    "actual": "фактическое",
    "adaptation": "адаптация",
    "adaption": "адаптация",
    "ageing": "старение",
    "air": "воздух",
    "ashes": "зола",
    "ash": "зола",
    "battery": "АКБ",
    "boost": "наддув",
    "calibration": "калибровка",
    "change": "замена",
    "comb": "сгорание",
    "continuous": "постоянная",
    "control": "управление",
    "coolant": "ОЖ",
    "current": "текущее",
    "differential": "перепад",
    "distance": "пробег",
    "dpf": "DPF",
    "druck": "давление",
    "drehzahl": "обороты",
    "egr": "EGR",
    "agr": "EGR",
    "engine": "двигатель",
    "einlernen": "обучение",
    "exhaust": "ОГ",
    "fahrpedalstellung": "положение педали акселератора",
    "factor": "коэффициент",
    "fctr": "коэффициент",
    "filter": "фильтр",
    "filt": "фильтр",
    "flap": "заслонка",
    "fuel": "топливо",
    "geschwindigkeit": "скорость",
    "glow": "накал",
    "idle": "холостой ход",
    "ist": "фактическое",
    "istwert": "фактическое значение",
    "klappe": "заслонка",
    "ladedruck": "давление наддува",
    "last": "последний",
    "learning": "обучение",
    "leerlauf": "холостой ход",
    "load": "загрузка",
    "luftmasse": "масса воздуха",
    "mass": "масса",
    "masse": "масса",
    "mileage": "пробег",
    "offset": "смещение",
    "oil": "масло",
    "oeltemperatur": "температура масла",
    "pedal": "педаль",
    "percent": "%",
    "position": "положение",
    "pressure": "давление",
    "pump": "насос",
    "rail": "топливная рампа",
    "raildruck": "давление в топливной рампе",
    "regeneration": "регенерация",
    "rgn": "регенерация",
    "sensor": "датчик",
    "simulated": "расчётная",
    "soll": "заданное",
    "sollwert": "заданное значение",
    "soot": "сажа",
    "speed": "скорость/обороты",
    "stellung": "положение",
    "successful": "успешная",
    "target": "заданное",
    "temperature": "температура",
    "temp": "температура",
    "throttle": "дроссель",
    "time": "время",
    "total": "суммарное",
    "valve": "клапан",
    "vehicle": "автомобиль",
    "veh": "автомобиль",
    "voltage": "напряжение",
    "wasser": "ОЖ",
    "wassertemperatur": "температура ОЖ",
}

SKIP_TOKENS = {
    "act", "adj", "app", "c", "dc", "dj", "dl", "dt", "fn", "i", "icv", "io",
    "ioc", "iod", "nvv", "off", "on", "p", "pt", "rli", "rt", "sto", "t", "tv",
}


def _ascii_lower(s: str) -> str:
    normalized = unicodedata.normalize("NFKD", s or "")
    return normalized.encode("ascii", "ignore").decode("ascii").lower()


def _clean(s: str) -> str:
    s = (s or "").strip()
    s = s.strip("$").strip()
    s = re.sub(r"[-=]*>\s*", " ", s)
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    s = s.replace("_", " ").replace("/", " ").replace("+", " ")
    s = s.replace("³", "3").replace("°", " град. ")
    s = re.sub(r"[\"'`´]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9а-яё%]+", " ", _ascii_lower(_clean(s)))).strip()


def _tokenize(s: str) -> list[str]:
    clean = _norm(s)
    tokens = []
    for t in clean.split():
        if not t or t in SKIP_TOKENS:
            continue
        if t.isdigit() or re.fullmatch(r"[0-9a-f]{2,5}", t):
            continue
        if re.fullmatch(r"[a-z]{1,2}[0-9a-f]{2,5}", t):
            continue
        tokens.append(t)
    return tokens


def translate(text: str, key: str = "", context: str = "") -> str | None:
    raw = (text or "").strip()
    if not raw or re.fullmatch(r"[-_\s]+", raw):
        return None

    exact_key = _norm(raw)
    if exact_key in EXACT:
        return EXACT[exact_key]
    if raw.startswith("$"):
        return None

    hay = " ".join([_norm(raw), _norm(key), _norm(context)])
    for pattern, replacement in PHRASES:
        if re.search(pattern, hay):
            if re.search(r"\bsoll\b|\btarget\b|\bpdesval\b", hay) and not replacement.startswith("задан"):
                return f"заданное {replacement}"
            if re.search(r"\bist\b|\bactual\b", hay) and not replacement.startswith("фактичес"):
                return f"фактическое {replacement}"
            return replacement

    tokens = _tokenize(raw)
    translated = []
    hits = 0
    unknown = 0
    for token in tokens:
        mapped = TOKEN_MAP.get(token)
        if mapped:
            if mapped not in translated:
                translated.append(mapped)
            hits += 1
        elif token.upper() in {"ABS", "AGR", "ALD", "ASA", "BLK", "CEPC", "COP", "DPF", "EGR",
                               "IMA", "ISA", "NMK", "SCR", "VTG"}:
            translated.append(token.upper())
            hits += 1
        else:
            unknown += 1

    if hits == 0:
        return None
    if unknown > hits:
        return None

    if len(translated) == 1 and len(tokens) > 1 and re.fullmatch(r"[A-Z0-9 /]+", translated[0]):
        return None

    result = " ".join(translated).strip()
    result = result.replace("DPF сажа масса", "масса сажи DPF")
    result = result.replace("сажа масса", "масса сажи")
    result = result.replace("давление наддув", "давление наддува")
    return result or None


def seed(db_path: Path, overwrite: bool = False, dry_run: bool = False, limit: int = 0) -> dict:
    stats = {
        "candidates": 0,
        "inserted": 0,
        "updated": 0,
        "skipped_existing": 0,
        "skipped_unknown": 0,
        "dry_run": dry_run,
        "samples": [],
    }
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            """
            SELECT source.localization_key, source.text, source.context, target.text AS existing
            FROM translations AS source
            LEFT JOIN translations AS target
              ON target.localization_key = source.localization_key
             AND target.lang = 'ru'
            WHERE source.lang = 'source'
            ORDER BY source.localization_key
            """
        ).fetchall()
        for row in rows:
            if limit and stats["candidates"] >= limit:
                break
            text = translate(row["text"], row["localization_key"], row["context"])
            if not text:
                stats["skipped_unknown"] += 1
                continue
            stats["candidates"] += 1
            if row["existing"] and not overwrite:
                stats["skipped_existing"] += 1
                continue
            if len(stats["samples"]) < 12:
                stats["samples"].append({
                    "source": row["text"],
                    "translation": text,
                    "key": row["localization_key"],
                })
            context = row["context"] or ""
            if MARKER not in context:
                context = f"{context}; {MARKER}" if context else MARKER
            if not dry_run:
                db.execute(
                    """
                    INSERT INTO translations(localization_key, lang, text, context)
                    VALUES (?, 'ru', ?, ?)
                    ON CONFLICT(localization_key, lang) DO UPDATE SET
                      text = excluded.text,
                      context = excluded.context
                    """,
                    (row["localization_key"], text, context),
                )
            if row["existing"]:
                stats["updated"] += 1
            else:
                stats["inserted"] += 1
        if not dry_run:
            db.commit()
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)
    print(json.dumps(
        seed(Path(args.db), overwrite=args.overwrite, dry_run=args.dry_run, limit=args.limit),
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
