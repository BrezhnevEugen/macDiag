"""
Human descriptions + readable names for measurement/service groups.

.vsg titles and job names are terse and German (e.g. "cr42 dpf-reg HK",
"DT_STO_C641_Inlet_Throttle_learning_open_done"). This maps them to:
  * a readable Russian PROCEDURE NAME and a curated "what / when / how" that
    matches the corresponding Mercedes Xentry/DAS service function;
  * a humanised parameter label + prefix meaning.

Curated for MB diesel (the .vsg set is CRD/CR families). Extend freely.
"""

from __future__ import annotations

import re

from . import locale

# RU procedure name -> {en, de} (the matched-procedure titles).
NAME_I18N = {
    "Переадаптация сажевого фильтра (DPF)":
        {"en": "DPF re-adaptation (particulate filter)", "de": "DPF-Neuadaption (Partikelfilter)"},
    "Регенерация сажевого фильтра (DPF)":
        {"en": "DPF regeneration (particulate filter)", "de": "DPF-Regeneration (Partikelfilter)"},
    "Калибровка форсунок (NMK / коды впрыска)":
        {"en": "Injector calibration (NMK / injection codes)", "de": "Injektor-Kalibrierung (NMK / Einspritzcodes)"},
    "Обучение актуаторов":
        {"en": "Actuator learning", "de": "Aktuator-Lernen"},
    "Адаптация холостого хода":
        {"en": "Idle adaptation", "de": "Leerlauf-Adaption"},
    "Адаптация дроссельной заслонки":
        {"en": "Throttle valve adaptation", "de": "Drosselklappen-Adaption"},
    "ALD — дорожная калибровка впрыска":
        {"en": "ALD — on-road injection calibration", "de": "ALD — Einspritz-Fahrkalibrierung"},
    "Адаптация датчика нейтрали / передач":
        {"en": "Neutral / gear sensor adaptation", "de": "Neutral-/Gangsensor-Adaption"},
    "Сброс ресурса топливного фильтра":
        {"en": "Fuel filter service reset", "de": "Kraftstofffilter-Reset"},
    "Контур давления топлива (Rail)":
        {"en": "Fuel pressure circuit (rail)", "de": "Kraftstoffdruck-Kreis (Rail)"},
    "Система наддува":
        {"en": "Boost pressure system", "de": "Ladedrucksystem"},
    "Система EGR (рециркуляция ОГ)":
        {"en": "EGR system (exhaust recirculation)", "de": "AGR-System (Abgasrückführung)"},
    "Тест компрессии (по неравномерности)":
        {"en": "Compression test (by roughness)", "de": "Kompressionstest (Laufunruhe)"},
    "Система SCR / AdBlue":
        {"en": "SCR / AdBlue system", "de": "SCR-/AdBlue-System"},
    "Измерительная группа":
        {"en": "Measurement group", "de": "Messwertgruppe"},
}

_WARN_I18N = {
    "ru": "Процедура изменяет адаптации/EEPROM ЭБУ — это запись, а не наблюдение. Выполняй по регламенту.",
    "en": "This procedure changes ECU adaptations/EEPROM — it writes, it does not just observe. Follow the service procedure.",
    "de": "Diese Prozedur ändert Steuergeräte-Adaptionen/EEPROM — sie schreibt, sie beobachtet nicht nur. Nach Vorschrift ausführen.",
}


def _name(ru: str, lang: str) -> str:
    if lang == "ru" or lang not in ("en", "de"):
        return ru
    e = NAME_I18N.get(ru)
    return (e and e.get(lang)) or ru

# Service-function knowledge base, matched by keyword over the group name/title.
# Each: regex -> {name (RU title), what, when, how, writes (changes adaptations)}.
PROCEDURES = [
    (r"dpf.?rgn.?werkstatt|readapt|re-?adapt|neuer? dpf|dpf.?tausch", {
        "name": "Переадаптация сажевого фильтра (DPF)",
        "what": "Сброс/инициализация счётчиков сажи и зольности после замены DPF "
                "(новый или б/у) — чтобы ЭБУ считал нагрузку с нуля.",
        "when": "После установки нового или другого сажевого фильтра.",
        "how": "Выбрать тип фильтра (новый/б/у) и подтвердить запись — счётчики "
               "массы сажи и золы переписываются в EEPROM.",
        "writes": True,
    }),
    (r"dpf|regenerat|partikel|russ|soot", {
        "name": "Регенерация сажевого фильтра (DPF)",
        "what": "Принудительный прожиг сажи: контроль массы сажи, температур "
                "до/после DPF, давления и статуса регенерации.",
        "when": "Высокая загрузка DPF, когда штатная регенерация не проходит "
                "(короткие поездки), горит лампа сажевого фильтра.",
        "how": "Двигатель прогрет, авто на улице (выхлоп горячий!). Запустить "
               "сервисную регенерацию и дождаться падения массы сажи (~20 мин).",
        "writes": False,
    }),
    (r"nmk|nullmeng|zero.?quantity|mengenabgleich|injector|injekt", {
        "name": "Калибровка форсунок (NMK / коды впрыска)",
        "what": "Обучение/запись поправок нулевой и малой подачи по каждой "
                "форсунке (плавность хода, тихий ХХ).",
        "when": "После замены форсунок или ТНВД, при ошибках неравномерности.",
        "how": "Прогретый двигатель на ХХ; запустить — поправки пишутся в ЭБУ "
               "(для замены форсунок сначала ввести их IMA/коды).",
        "writes": True,
    }),
    (r"aktoren?_?lernen|actuator|stell", {
        "name": "Обучение актуаторов",
        "what": "ЭБУ заново узнаёт крайние положения приводов: впускной дроссель, "
                "вихревые заслонки (Swirl Flap), клапаны EGR (HP/LP).",
        "when": "После чистки/замены этих узлов или замены ЭБУ.",
        "how": "Зажигание вкл., двигатель заглушен; запустить — приводы проходят "
               "в упоры, значения сохраняются в EEPROM (DT_STO_*).",
        "writes": True,
    }),
    (r"leerlauf|idle", {
        "name": "Адаптация холостого хода",
        "what": "Адаптация регулятора ХХ / нулевых положений после вмешательства.",
        "when": "После чистки дросселя, замены датчиков, сброса адаптаций.",
        "how": "Прогретый двигатель на ХХ, без нагрузки; запустить обучение.",
        "writes": True,
    }),
    (r"throttle|drossel|dk[-_ ]?winkel", {
        "name": "Адаптация дроссельной заслонки",
        "what": "Обучение крайних положений и нуля впускного дросселя.",
        "when": "После чистки/замены дроссельного узла.",
        "how": "Зажигание вкл., двигатель заглушен; запустить адаптацию.",
        "writes": True,
    }),
    (r"\bald\b|ald[_ ]?lernen|drive.?reg|drivetest|fahr", {
        "name": "ALD — дорожная калибровка впрыска",
        "what": "Калибровка параметров впрыска и плавности по дорожному тесту.",
        "when": "После работ по топливной аппаратуре.",
        "how": "Выполняется в движении по заданному профилю (drive test).",
        "writes": True,
    }),
    (r"neutralgang|neutralsensor|n[-_ ]?gang|reverse.?sensor|getriebepos", {
        "name": "Адаптация датчика нейтрали / передач",
        "what": "Обучение положений датчика нейтрали и передач.",
        "when": "После замены датчика/КПП или по ошибке положения.",
        "how": "По регламенту процедуры; значения сохраняются в ЭБУ.",
        "writes": True,
    }),
    (r"fuelfilter|kraftstofffilter|filterbeladung", {
        "name": "Сброс ресурса топливного фильтра",
        "what": "Сброс счётчика загрязнения/ресурса топливного фильтра.",
        "when": "После замены топливного фильтра.",
        "how": "Подтвердить сброс — счётчик обнуляется.",
        "writes": True,
    }),
    (r"hdk|rail|kraftstoffdruck|fuel.?press|systemdruck|druckregel", {
        "name": "Контур давления топлива (Rail)",
        "what": "Давление в рампе (факт/требование), регулятор и клапан дозирования.",
        "when": "Диагностика давления, после ремонта ТА.",
        "how": "Наблюдение значений на ХХ и под нагрузкой.",
        "writes": False,
    }),
    (r"ladedruck|boost|lader|turbo", {
        "name": "Система наддува",
        "what": "Давление наддува (факт/требование), геометрия турбины, момент, обороты.",
        "when": "Диагностика недодува/передува, ошибок турбины.",
        "how": "Наблюдение значений на ХХ и при нагрузке (тест-драйв).",
        "writes": False,
    }),
    (r"egr|agr|abgasr[uü]ckf", {
        "name": "Система EGR (рециркуляция ОГ)",
        "what": "Положения и поправки клапанов EGR (высокого/низкого давления).",
        "when": "Диагностика EGR, после чистки/замены клапана.",
        "how": "Наблюдение значений; обучение положений — в «Обучении актуаторов».",
        "writes": False,
    }),
    (r"compression|kompress|verdicht", {
        "name": "Тест компрессии (по неравномерности)",
        "what": "Оценка компрессии по колебаниям коленвала при прокрутке.",
        "when": "Подозрение на механические проблемы цилиндров.",
        "how": "По процедуре прокрутки стартером.",
        "writes": False,
    }),
    (r"scr|adblue|harnstoff|reduktion", {
        "name": "Система SCR / AdBlue",
        "what": "Параметры дозирования AdBlue, давление, температуры, статус.",
        "when": "Диагностика SCR, ошибки AdBlue.",
        "how": "Наблюдение значений; сброс сценариев — отдельной функцией.",
        "writes": False,
    }),
    (r"\btest\b|messwert|messung|diag|servicegruppe", {
        "name": "Измерительная группа",
        "what": "Набор контрольных параметров ЭБУ для диагностики.",
        "when": "Общая диагностика узла/системы.",
        "how": "Наблюдение значений; при необходимости сравнить с нормой.",
        "writes": False,
    }),
]

PREFIXES = [
    ("DT_STO_", "сохранённое значение (EEPROM)"),
    ("DT_", "текущее значение (live)"),
    ("DL_", "текущее значение узла (live)"),
    ("ADJ_", "адаптация / поправка"),
    ("RT_", "процедура / актуаторный тест"),
    ("FN_", "функция / сервисная команда"),
    ("ON_", "включение актуатора"),
    ("OFF_", "выключение актуатора"),
    ("ST_", "управление состоянием"),
]

_CODE = re.compile(r"^(?:[A-Z]{1,3}\d{2,4}|IO[0-9A-F]+)_", re.I)


def _match(name: str, title: str = "") -> dict | None:
    hay = f"{name} {title}".lower()
    for pat, info in PROCEDURES:
        if re.search(pat, hay):
            return info
    return None


def describe_group(name: str, title: str = "", lang: str = "ru") -> dict | None:
    info = _match(name, title)
    if not info:
        return None
    # NOTE: body text (what/when/how) is curated in RU; titles + warning localize.
    out = {"title": _name(info["name"], lang), "what": info["what"],
           "when": info["when"], "how": info["how"]}
    if info.get("writes"):
        out["warn"] = _WARN_I18N.get(lang, _WARN_I18N["ru"])
    return out


def friendly_title(name: str, title: str = "", lang: str = "ru") -> str:
    """Readable name: a curated procedure name (localized) when a real procedure
    matches; otherwise keep/localize a good existing title, or clean a cryptic one."""
    t = (title or "").strip()
    good = bool(t and "\\" not in t and "/" not in t and "_" not in t
                and not t.endswith("HK") and not t.lower().endswith((".vsg", ".mwg")))
    info = _match(name, title)
    if info:
        # don't collapse a good, specific title into the generic bucket
        if info["name"] == "Измерительная группа" and good:
            return locale.localize(t, lang)
        return _name(info["name"], lang)
    if good:
        return locale.localize(t, lang)
    base = re.split(r"[\\/]", name)[-1]
    base = re.sub(r"\.(vsg|mwg)$", "", base, flags=re.I)
    base = base.replace("_", " ").strip() or name
    return locale.localize(base, lang)


def prefix_note(job: str) -> str:
    for p, note in PREFIXES:
        if job.startswith(p):
            return note
    return ""


def humanize(job: str, alias: str = "") -> str:
    if alias:
        return alias
    s = job
    for p, _ in PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
            break
    s = _CODE.sub("", s)
    s = s.replace("_", " ").strip()
    return s or job
