"""
DAS-style diagnostic drill-down context for a DTC.

Given a fault code (and the ECU it came from) we assemble a guided panel:
  * localized description + area,
  * probable causes (curated per code / per area),
  * a check-list of next steps,
  * media descriptors (generated SVG schematics; WIS images once mounted).

Linked measurement/service groups are attached by the API layer (it already
knows the ECU's groups). All text is localized ru / en / de.

This is authored knowledge layered on the data we have — it is NOT the Mercedes
WIS/Xentry guided-diagnostics content (that needs the WIS dataset, see wis.py).
"""

from __future__ import annotations

from . import dtc

LANGS = ("ru", "en", "de")


def _pick(d: dict, lang: str):
    return d.get(lang) or d.get("en") or next(iter(d.values()))


# Per-code probable causes (override the per-area defaults).
CAUSES = {
    "B1535": {
        "ru": ["Обрыв/окисление разъёма блока сиденья", "Просадка питания или массы блока",
               "Внутренняя неисправность модуля (под замену)", "Проблема шины LIN/CAN до модуля"],
        "en": ["Open/corroded seat-module connector", "Low supply or ground at the module",
               "Internal module fault (replace)", "LIN/CAN bus issue to the module"],
        "de": ["Offener/korrodierter Stecker am Sitzmodul", "Niedrige Versorgung oder Masse am Modul",
               "Interner Modulfehler (ersetzen)", "LIN/CAN-Bus-Problem zum Modul"],
    },
    "C1525": {
        "ru": ["Датчик давления в тормозном контуре вне диапазона", "Воздух в контуре / низкий уровень ДОТ",
               "Неисправность гидроблока ESP", "Помехи по питанию или массе блока ESP"],
        "en": ["Brake-circuit pressure sensor out of range", "Air in the circuit / low brake fluid",
               "ESP hydraulic unit fault", "Supply/ground disturbance at the ESP unit"],
        "de": ["Bremsdrucksensor außerhalb des Bereichs", "Luft im Kreis / niedriger Bremsflüssigkeitsstand",
               "Defekt der ESP-Hydraulikeinheit", "Versorgungs-/Masseproblem am ESP-Steuergerät"],
    },
}

# Per-area defaults, keyed by the code's first letter.
AREA_CAUSES = {
    "P": {
        "ru": ["Датчик или исполнитель вне допуска", "Проводка/разъём в цепи", "Подсос воздуха/негерметичность (впуск)", "Износ или загрязнение компонента"],
        "en": ["Sensor or actuator out of tolerance", "Wiring/connector in the circuit", "Air leak/unmetered air (intake)", "Worn or contaminated component"],
        "de": ["Sensor oder Aktuator außerhalb der Toleranz", "Verkabelung/Stecker im Stromkreis", "Falschluft/Undichtigkeit (Ansaugung)", "Verschlissene oder verschmutzte Komponente"],
    },
    "C": {
        "ru": ["Датчик колеса/давления вне допуска", "Проводка или разъём датчика", "Механический износ узла", "Питание/масса блока"],
        "en": ["Wheel/pressure sensor out of tolerance", "Sensor wiring or connector", "Mechanical wear of the assembly", "Module supply/ground"],
        "de": ["Rad-/Drucksensor außerhalb der Toleranz", "Sensorverkabelung oder Stecker", "Mechanischer Verschleiß der Baugruppe", "Versorgung/Masse des Steuergeräts"],
    },
    "B": {
        "ru": ["Разъём или проводка модуля", "Питание и масса модуля", "Внутренняя неисправность модуля", "Конфликт кодирования/версий ПО"],
        "en": ["Module connector or wiring", "Module supply and ground", "Internal module fault", "Coding/software-version conflict"],
        "de": ["Modulstecker oder Verkabelung", "Versorgung und Masse des Moduls", "Interner Modulfehler", "Codierungs-/Softwareversions-Konflikt"],
    },
    "U": {
        "ru": ["Обрыв или замыкание CAN", "Один из ЭБУ не отвечает (питание)", "Проблема терминаторов/топологии шины", "Спящий или неинициализированный узел"],
        "en": ["CAN open or short", "An ECU not answering (power)", "Bus terminator/topology issue", "Sleeping or uninitialized node"],
        "de": ["CAN-Unterbrechung oder Kurzschluss", "Ein Steuergerät antwortet nicht (Strom)", "Abschlusswiderstand/Topologie-Problem", "Schlafender oder nicht initialisierter Knoten"],
    },
}
_UNK_CAUSES = {"ru": ["Причина не классифицирована — см. шаги проверки"],
               "en": ["Cause not classified — see the check steps"],
               "de": ["Ursache nicht klassifiziert — siehe Prüfschritte"]}

# Check-list of next steps, per area.
AREA_CHECKS = {
    "P": {
        "ru": ["Сними freeze-frame и условия возникновения", "Открой связанную группу измерений — сравни факт с нормой",
               "Проверь разъём/проводку цепи (визуально и сопротивление)", "Запусти актуаторный тест, если он есть",
               "Сотри ошибку и проверь повторно на прогретом ДВС"],
        "en": ["Read the freeze-frame and the conditions", "Open the linked measurement group — compare actual vs. spec",
               "Check the circuit connector/wiring (visual + resistance)", "Run the actuator test if available",
               "Clear the fault and recheck on a warm engine"],
        "de": ["Freeze-Frame und Bedingungen auslesen", "Verknüpfte Messwertgruppe öffnen — Ist mit Soll vergleichen",
               "Stecker/Verkabelung prüfen (Sicht + Widerstand)", "Aktuatortest ausführen, falls vorhanden",
               "Fehler löschen und am warmen Motor erneut prüfen"],
    },
    "C": {
        "ru": ["Сравни показания датчиков в группе измерений", "Проверь уровень и состояние тормозной жидкости",
               "Проверь разъёмы датчиков колёс/давления", "Сотри ошибку и проверь в движении"],
        "en": ["Compare the sensor readings in the measurement group", "Check brake-fluid level and condition",
               "Check the wheel/pressure sensor connectors", "Clear the fault and test on the road"],
        "de": ["Sensorwerte in der Messwertgruppe vergleichen", "Bremsflüssigkeitsstand und -zustand prüfen",
               "Stecker der Rad-/Drucksensoren prüfen", "Fehler löschen und auf der Straße prüfen"],
    },
    "B": {
        "ru": ["Проверь питание и массу модуля", "Осмотри разъём на окисление/влагу",
               "Сравни версию ПО и кодирование", "Сотри ошибку и проверь повторно"],
        "en": ["Check the module supply and ground", "Inspect the connector for corrosion/moisture",
               "Compare software version and coding", "Clear the fault and recheck"],
        "de": ["Versorgung und Masse des Moduls prüfen", "Stecker auf Korrosion/Feuchtigkeit prüfen",
               "Softwareversion und Codierung vergleichen", "Fehler löschen und erneut prüfen"],
    },
    "U": {
        "ru": ["Посмотри в «Сканировании», какие ЭБУ офлайн", "Проверь питание офлайн-узлов",
               "Измерь сопротивление CAN (≈60 Ом между H и L)", "Найди обрыв/замыкание в жгуте"],
        "en": ["See which ECUs are offline in the Scan", "Check power to the offline nodes",
               "Measure CAN resistance (≈60 Ω between H and L)", "Find the open/short in the harness"],
        "de": ["Im Scan prüfen, welche Steuergeräte offline sind", "Stromversorgung der Offline-Knoten prüfen",
               "CAN-Widerstand messen (≈60 Ω zwischen H und L)", "Unterbrechung/Kurzschluss im Kabelbaum finden"],
    },
}
_UNK_CHECKS = {"ru": ["Сними freeze-frame", "Сравни связанные параметры с нормой", "Проверь проводку и разъёмы", "Сотри и проверь повторно"],
               "en": ["Read the freeze-frame", "Compare the linked parameters vs. spec", "Check wiring and connectors", "Clear and recheck"],
               "de": ["Freeze-Frame auslesen", "Verknüpfte Parameter mit Soll vergleichen", "Verkabelung und Stecker prüfen", "Löschen und erneut prüfen"]}

_PANEL = {
    "causes": {"ru": "Вероятные причины", "en": "Probable causes", "de": "Mögliche Ursachen"},
    "checks": {"ru": "Шаги проверки", "en": "Check steps", "de": "Prüfschritte"},
    "area": {"ru": "Область", "en": "Area", "de": "Bereich"},
    "schem": {"ru": "Схема: топология CAN-шины", "en": "Schematic: CAN bus topology", "de": "Schema: CAN-Bus-Topologie"},
    "cyl": {"ru": "Схема: расположение цилиндров", "en": "Schematic: cylinder layout", "de": "Schema: Zylinderanordnung"},
}

_ENGINE_HINT = ("CR", "ME", "MED", "SIM", "PLD", "CDI", "MOTOR", "ENGINE", "ДВИГ")


def _is_engine(module: dict | None) -> bool:
    if not module:
        return False
    hay = (str(module.get("cbf", "")) + " " + str(module.get("name", ""))).upper()
    return any(h in hay for h in _ENGINE_HINT)


def context(code: str, lang: str = "ru", module: dict | None = None) -> dict:
    if lang not in LANGS:
        lang = "ru"
    letter = (code[:1] or "").upper()
    causes = _pick(CAUSES.get(code) or AREA_CAUSES.get(letter, _UNK_CAUSES), lang)
    checks = _pick(AREA_CHECKS.get(letter, _UNK_CHECKS), lang)
    area = dtc._pick(dtc.PREFIX.get(letter, dtc._UNKNOWN), lang)

    mod_q = ""
    if module and module.get("id"):
        mod_q = "&module=" + str(module["id"])
    media = [{
        "kind": "schematic", "type": "can_topology",
        "title": _pick(_PANEL["schem"], lang),
        "src": "/api/diag/schematic?type=can_topology" + mod_q,
    }]
    if _is_engine(module):
        media.append({
            "kind": "schematic", "type": "cylinder_layout",
            "title": _pick(_PANEL["cyl"], lang),
            "src": "/api/diag/schematic?type=cylinder_layout" + mod_q,
        })

    return {
        "code": code,
        "description": dtc.describe(code, lang),
        "area": area,
        "causes": causes,
        "checks": checks,
        "media": media,
        "labels": {k: _pick(v, lang) for k, v in _PANEL.items()},
    }
