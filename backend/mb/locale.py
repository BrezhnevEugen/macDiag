"""
Localization (ru / en / de) for .vsg / CBF group titles.

The source titles are German. localize(title, lang):
  * de -> the original German title;
  * ru / en -> PHRASES (exact) then a term-by-term translation, else original.

PHRASES grows from tools/list_vsg_titles.py output; TERMS covers common MB
automotive words for the word-by-word fallback.
"""

from __future__ import annotations

import re

LANGS = ("ru", "en", "de")

# exact German title -> {ru, en}
PHRASES = {
    "Überprüfung des Ladedrucksystems":
        {"ru": "Проверка системы наддува", "en": "Boost pressure system check"},
    "Neutralgangsensor":
        {"ru": "Датчик нейтрали", "en": "Neutral gear sensor"},
    "FSCM212 - Druckregelung":
        {"ru": "FSCM212 — регулировка давления", "en": "FSCM212 — pressure control"},
    "Kraftstofffilterbeladung":
        {"ru": "Загрязнение топливного фильтра", "en": "Fuel filter loading"},
    "throttle learning":
        {"ru": "Обучение дроссельной заслонки", "en": "Throttle learning"},
}

# German term -> {ru, en} for word-by-word fallback. lowercase keys.
TERMS = {
    "überprüfung": {"ru": "проверка", "en": "check"},
    "prüfung": {"ru": "проверка", "en": "check"},
    "kontrolle": {"ru": "контроль", "en": "control"},
    "test": {"ru": "тест", "en": "test"},
    "messwerte": {"ru": "измерения", "en": "measurements"},
    "system": {"ru": "система", "en": "system"},
    "systems": {"ru": "системы", "en": "system"},
    "ladedruck": {"ru": "давление наддува", "en": "boost pressure"},
    "ladedrucksystems": {"ru": "системы наддува", "en": "boost system"},
    "druck": {"ru": "давление", "en": "pressure"},
    "druckregelung": {"ru": "регулировка давления", "en": "pressure control"},
    "regelung": {"ru": "регулировка", "en": "control"},
    "raildruck": {"ru": "давление в рампе", "en": "rail pressure"},
    "anpassung": {"ru": "адаптация", "en": "adaptation"},
    "adaption": {"ru": "адаптация", "en": "adaptation"},
    "abgleich": {"ru": "калибровка", "en": "calibration"},
    "lernen": {"ru": "обучение", "en": "learning"},
    "kalibrierung": {"ru": "калибровка", "en": "calibration"},
    "regeneration": {"ru": "регенерация", "en": "regeneration"},
    "partikelfilter": {"ru": "сажевый фильтр", "en": "particulate filter"},
    "drosselklappe": {"ru": "дроссельная заслонка", "en": "throttle valve"},
    "drossel": {"ru": "дроссель", "en": "throttle"},
    "leerlauf": {"ru": "холостой ход", "en": "idle"},
    "einspritzung": {"ru": "впрыск", "en": "injection"},
    "förderbeginn": {"ru": "начало подачи", "en": "start of delivery"},
    "injektor": {"ru": "форсунка", "en": "injector"},
    "abgasklappe": {"ru": "заслонка ОГ", "en": "exhaust flap"},
    "abgas": {"ru": "ОГ", "en": "exhaust"},
    "agr": {"ru": "EGR", "en": "EGR"},
    "neutralgangsensor": {"ru": "датчик нейтрали", "en": "neutral sensor"},
    "neutralsensor": {"ru": "датчик нейтрали", "en": "neutral sensor"},
    "getriebe": {"ru": "КПП", "en": "transmission"},
    "kraftstoff": {"ru": "топливо", "en": "fuel"},
    "kraftstofffilter": {"ru": "топливный фильтр", "en": "fuel filter"},
    "kraftstoffpumpe": {"ru": "топливный насос", "en": "fuel pump"},
    "kühlmittel": {"ru": "ОЖ", "en": "coolant"},
    "wasserventil": {"ru": "клапан ОЖ", "en": "water valve"},
    "heizer": {"ru": "подогреватель", "en": "heater"},
    "temperatur": {"ru": "температура", "en": "temperature"},
    "spannung": {"ru": "напряжение", "en": "voltage"},
    "drehzahl": {"ru": "обороты", "en": "rpm"},
    "geschwindigkeit": {"ru": "скорость", "en": "speed"},
    "drehmoment": {"ru": "момент", "en": "torque"},
    "sensor": {"ru": "датчик", "en": "sensor"},
    "ventil": {"ru": "клапан", "en": "valve"},
    "klappe": {"ru": "заслонка", "en": "flap"},
    "stellung": {"ru": "положение", "en": "position"},
    "position": {"ru": "положение", "en": "position"},
    "winkel": {"ru": "угол", "en": "angle"},
    "soll": {"ru": "заданное", "en": "target"},
    "ist": {"ru": "текущее", "en": "actual"},
    "wert": {"ru": "значение", "en": "value"},
    "status": {"ru": "статус", "en": "status"},
    "motor": {"ru": "двигатель", "en": "engine"},
    "verbrauch": {"ru": "расход", "en": "consumption"},
    "reiserechner": {"ru": "борткомпьютер", "en": "trip computer"},
    "lenkhilfe": {"ru": "усилитель руля", "en": "power steering"},
    "steller": {"ru": "актуатор", "en": "actuator"},
    "freischalten": {"ru": "разблокировка", "en": "unlock"},
    "reset": {"ru": "сброс", "en": "reset"},
    "batterie": {"ru": "АКБ", "en": "battery"},
}

_ARTICLES = {"der", "die", "das", "des", "den", "dem", "ein", "eine", "einen",
             "im", "am", "für", "und", "mit", "von", "zur", "zum", "über",
             "auf", "bei", "an", "in", "the", "of"}


def localize(title: str, lang: str = "ru") -> str:
    t = (title or "").strip()
    if not t or lang == "de" or lang not in LANGS:
        return t
    if t in PHRASES:
        return PHRASES[t].get(lang, t)
    out, hit = [], False
    for w in t.split():
        core = w.strip(".,;:()[]").lower()
        if core in _ARTICLES:
            hit = True
            continue
        tr = TERMS.get(core)
        if tr:
            out.append(tr.get(lang, w)); hit = True
        else:
            out.append(w)
    res = re.sub(r"\s+", " ", " ".join(out)).strip()
    return res if (hit and res) else t
