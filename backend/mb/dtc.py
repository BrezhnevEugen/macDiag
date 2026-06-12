"""Light DTC description helper. Generic SAE descriptions + a few MB-specific.

Descriptions are localized (ru / en / de) via the `lang` argument.
"""

# code -> {en, ru, de}
MB_DTC = {
    "B1535": {
        "en": "Driver seat control module - communication / internal fault",
        "ru": "Блок управления сиденьем водителя — связь / внутренняя неисправность",
        "de": "Steuergerät Fahrersitz — Kommunikation / interner Fehler",
    },
    "C1525": {
        "en": "ESP - hydraulic unit / pressure sensor implausible",
        "ru": "ESP — гидроблок / датчик давления недостоверен",
        "de": "ESP — Hydraulikeinheit / Drucksensor unplausibel",
    },
    "P0170": {
        "en": "Fuel trim malfunction (bank 1)",
        "ru": "Неисправность топливной коррекции (банк 1)",
        "de": "Gemischadaption fehlerhaft (Bank 1)",
    },
    "P0300": {
        "en": "Random/multiple cylinder misfire detected",
        "ru": "Случайные/множественные пропуски зажигания",
        "de": "Zufällige/mehrere Verbrennungsaussetzer erkannt",
    },
    "P2004": {
        "en": "Intake manifold runner control stuck open (bank 1)",
        "ru": "Заслонка впускного коллектора заклинила открытой (банк 1)",
        "de": "Saugrohrklappe klemmt offen (Bank 1)",
    },
    "U0100": {
        "en": "Lost communication with ECM/PCM",
        "ru": "Потеря связи с ЭБУ двигателя (ECM/PCM)",
        "de": "Kommunikation mit Motorsteuergerät (ECM/PCM) verloren",
    },
}

PREFIX = {
    "P": {"en": "Powertrain", "ru": "Двигатель/трансмиссия", "de": "Antrieb"},
    "C": {"en": "Chassis", "ru": "Шасси", "de": "Fahrwerk"},
    "B": {"en": "Body", "ru": "Кузов", "de": "Karosserie"},
    "U": {"en": "Network", "ru": "Сеть/CAN", "de": "Netzwerk"},
}
_UNKNOWN = {"en": "Unknown", "ru": "Неизвестно", "de": "Unbekannt"}

_FALLBACK = {
    "en": "{area} fault - see model service manual for {code}",
    "ru": "{area}: неисправность — см. сервисное руководство по {code}",
    "de": "{area}: Fehler — siehe Werkstatthandbuch zu {code}",
}


def _pick(d: dict, lang: str) -> str:
    return d.get(lang) or d.get("en") or next(iter(d.values()))


def describe(code: str, lang: str = "ru") -> str:
    if lang not in ("ru", "en", "de"):
        lang = "ru"
    if code in MB_DTC:
        return _pick(MB_DTC[code], lang)
    area = _pick(PREFIX.get(code[:1], _UNKNOWN), lang)
    return _FALLBACK.get(lang, _FALLBACK["ru"]).format(area=area, code=code)
