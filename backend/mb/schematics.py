"""
Generated SVG schematics (no external data needed) for the drill-down panel:

  * can_topology  — OBD port → central gateway → ECUs, colored by protocol,
                    labelled with the diagnostic CAN id; the focused ECU is
                    highlighted.
  * cylinder_layout — schematic engine cylinder/injector map.

Returned as raw SVG strings; the API serves them with image/svg+xml. Colors
match the app's dark theme.
"""

from __future__ import annotations

from html import escape

_BG = "#0d1117"
_PANEL = "#161b22"
_LINE = "#2a2f37"
_TXT = "#e6edf3"
_MUTED = "#8b949e"
_UDS = "#388bfd"
_KWP = "#d29922"
_ACCENT = "#1f6feb"
_OK = "#3fb950"
_HL = "#ffd33d"  # focus highlight (gold)

_T = {
    "can_title": {"ru": "Топология диагностической CAN (500 кбит/с)",
                  "en": "Diagnostic CAN topology (500 kbit/s)",
                  "de": "Diagnose-CAN-Topologie (500 kbit/s)"},
    "obd": {"ru": "OBD-II", "en": "OBD-II", "de": "OBD-II"},
    "gw": {"ru": "Центральный шлюз (ZGW/EZS)", "en": "Central gateway (ZGW/EZS)", "de": "Zentrales Gateway (ZGW/EZS)"},
    "note": {"ru": "Кузовные ЭБУ адресуются через шлюз по CAN-id (внутр. шина 83.3к не на пинах OBD).",
             "en": "Body ECUs are addressed through the gateway by CAN id (internal 83.3k bus is not on the OBD pins).",
             "de": "Karosserie-Steuergeräte werden über das Gateway per CAN-ID adressiert (interner 83,3k-Bus liegt nicht an den OBD-Pins)."},
    "cyl_title": {"ru": "Расположение цилиндров / форсунок (схема)",
                  "en": "Cylinder / injector layout (schematic)",
                  "de": "Zylinder- / Injektoranordnung (Schema)"},
    "cyl_note": {"ru": "Схематично. Нумерация и банк зависят от мотора (V6/V8/рядный).",
                 "en": "Schematic. Numbering and bank depend on the engine (V6/V8/inline).",
                 "de": "Schematisch. Nummerierung und Bank hängen vom Motor ab (V6/V8/Reihe)."},
    "focus_tag": {"ru": "эта ошибка", "en": "this fault", "de": "dieser Fehler"},
}


def _pick(d, lang):
    return d.get(lang) or d.get("en")


def _canid(x):
    try:
        return "0x%X" % int(x)
    except Exception:
        return "—"


# Bus lanes behind the central gateway, each with its own "wire" colour.
BUSES = [
    {"key": "can_c", "color": "#3fb950", "speed": "500 kbit/s",
     "name": {"ru": "CAN-C · Привод", "en": "CAN-C · Powertrain", "de": "CAN-C · Antrieb"}},
    {"key": "chassis", "color": "#e3603b", "speed": "500 kbit/s",
     "name": {"ru": "CAN · Шасси / ESP", "en": "CAN · Chassis / ESP", "de": "CAN · Fahrwerk / ESP"}},
    {"key": "can_b", "color": "#388bfd", "speed": "83.3 kbit/s",
     "name": {"ru": "CAN-B · Салон", "en": "CAN-B · Interior", "de": "CAN-B · Innenraum"}},
]
_BUS_BY_KEY = {b["key"]: b for b in BUSES}

# LIN sub-nets hang off body masters (SAM/KLA/EZS), below CAN-B. We don't have
# LIN slaves in the catalog, so these are typical authored groupings (schematic).
LIN_BUS = {"key": "lin", "color": "#a371f7", "speed": "~19.2 kbit/s",
           "name": {"ru": "LIN · подсети", "en": "LIN · sub-nets", "de": "LIN · Subnetze"},
           "note": {"ru": "схематично, типовые узлы", "en": "schematic, typical nodes",
                    "de": "schematisch, typische Knoten"}}
LIN_NETS = [
    {"master": "SAM-V", "slaves": {"ru": "двери перед · зеркала · датчик дождя/света",
                                   "en": "front doors · mirrors · rain/light sensor",
                                   "de": "Vordertüren · Spiegel · Regen-/Lichtsensor"}},
    {"master": "SAM-H", "slaves": {"ru": "двери зад · шторки",
                                   "en": "rear doors · sunblinds", "de": "Hintertüren · Rollos"}},
    {"master": "KLA", "slaves": {"ru": "сервоприводы заслонок · датчик точки росы · задний климат",
                                 "en": "flap servos · dew-point sensor · rear A/C",
                                 "de": "Klappenstellmotoren · Taupunktsensor · Fond-Klima"}},
    {"master": "EZS", "slaves": {"ru": "рулевой модуль (SCM) · подрулевые",
                                 "en": "steering column module (SCM)", "de": "Lenksäulenmodul (SCM)"}},
]


_LIN_MASTER_ID = {"SAM-V": "samv", "SAM-H": "samh", "KLA": "kla", "EZS": "ezs"}


def _lin_cards(lang: str) -> list[dict]:
    return [{"name": f'LIN @ {n["master"]}', "lin": True,
             "slaves": _pick(n["slaves"], lang),
             "mid": _LIN_MASTER_ID.get(n["master"])} for n in LIN_NETS]


def _bus_of(m: dict) -> str:
    hay = f" {m.get('id','')} {m.get('name','')} {m.get('cbf','')} ".lower()
    if any(k in hay for k in ("esp", " abs", "/abs", " bas", "/bas", "sbc", "brake")):
        return "chassis"
    if any(k in hay for k in ("engine", "motor", "me9", "me2", "crd", "cdi", "tcm",
                              "vgs", "transmission", "getrieb", "fscm", "fuel")):
        return "can_c"
    return "can_b"


def can_topology(modules: list[dict], highlight_id: str | None = None,
                 lang: str = "ru") -> str:
    """Layered topology: OBD → central gateway → separate bus lanes, each lane
    drawn with its own 'wire' colour and the ECUs that sit on it."""
    margin, W, cw, ch, cgap, rvgap, cols = 20, 1180, 210, 64, 18, 16, 5
    hl = (highlight_id or "").lower()
    cx = W / 2

    # group ECUs into CAN bus lanes on the gateway spine (skip the gateway itself)
    lanes = []
    for b in BUSES:
        mods = [m for m in modules
                if _bus_of(m) == b["key"] and str(m.get("id", "")).lower() != "zgw"]
        if mods:
            lanes.append((b, mods))

    # lay lanes out vertically, remembering each lane's bus-line Y
    lanes_pos, cur = [], 132
    for b, mods in lanes:
        label_y = cur
        bus_y = cur + 36
        cards_top = bus_y + 30
        rows = (len(mods) + cols - 1) // cols
        bottom = cards_top + rows * ch + (rows - 1) * rvgap
        lanes_pos.append((b, mods, label_y, bus_y, cards_top, rows))
        cur = bottom + 44
    last_bus_y = lanes_pos[-1][3] if lanes_pos else 132
    # LIN zone sits below the CAN lanes; it does NOT branch off the gateway —
    # each LIN sub-net connects to its master ECU (drawn after the lanes).
    lin_label_y = cur
    lin_cards_top = lin_label_y + 34
    H = lin_cards_top + ch + 24

    gw_y, gw_h = 30, 46
    gw_w, gw_x = 300, cx - 150
    obd_x, obd_y = 20, 30
    parts = [
        f'<svg viewBox="0 0 {W} {int(H)}" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Roboto,sans-serif">',
        f'<defs><filter id="glow" x="-50%" y="-50%" width="200%" height="200%">'
        f'<feDropShadow dx="0" dy="0" stdDeviation="7" flood-color="{_HL}" flood-opacity="0.95"/></filter></defs>',
        f'<rect x="0" y="0" width="{W}" height="{int(H)}" fill="{_BG}"/>',
        f'<rect x="{obd_x}" y="{obd_y}" width="132" height="46" rx="8" fill="{_PANEL}" stroke="{_OK}"/>',
        f'<text x="{obd_x+66}" y="{obd_y+29}" fill="{_OK}" font-size="16" text-anchor="middle">{escape(_pick(_T["obd"], lang))}</text>',
        f'<line x1="{obd_x+132}" y1="{obd_y+23}" x2="{gw_x}" y2="{gw_y+23}" stroke="{_OK}" stroke-width="2.5"/>',
        f'<rect x="{gw_x}" y="{gw_y}" width="{gw_w}" height="{gw_h}" rx="10" fill="{_PANEL}" stroke="{_ACCENT}" stroke-width="2.5"/>',
        f'<text x="{cx}" y="{gw_y+29}" fill="{_TXT}" font-size="16" text-anchor="middle" font-weight="600">{escape(_pick(_T["gw"], lang))}</text>',
        # backbone spine from the gateway down through all lanes
        f'<line x1="{cx}" y1="{gw_y+gw_h}" x2="{cx}" y2="{last_bus_y}" stroke="{_LINE}" stroke-width="2"/>',
    ]

    focus_parts = []
    master_centers = {}  # ECU id -> (cx, bottom_y, x) for LIN masters
    for b, mods, label_y, bus_y, cards_top, rows in lanes_pos:
        color = b["color"]
        # bus trunk line + branch node on the spine
        parts.append(f'<line x1="{margin}" y1="{bus_y}" x2="{W-margin}" y2="{bus_y}" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<circle cx="{cx}" cy="{bus_y}" r="6" fill="{color}"/>')
        # lane label: colour swatch + name · speed
        lbl = f'{_pick(b["name"], lang)} · {b["speed"]}'
        parts.append(f'<rect x="{margin}" y="{label_y}" width="14" height="14" rx="3" fill="{color}"/>')
        parts.append(f'<text x="{margin+22}" y="{label_y+12}" fill="{_TXT}" font-size="15" font-weight="600">{escape(lbl)}</text>')
        if b.get("note"):
            parts.append(f'<text x="{margin+22+len(lbl)*8+18}" y="{label_y+12}" fill="{_MUTED}" font-size="13">{escape(_pick(b["note"], lang))}</text>')
        for j, m in enumerate(mods):
            r, c = divmod(j, cols)
            x = margin + c * (cw + cgap)
            y = cards_top + r * (ch + rvgap)
            proto = (m.get("protocol") or "uds").lower()
            pcol = _KWP if proto == "kwp" else _UDS
            focus = bool(hl) and hl in (str(m.get("id", "")).lower(), str(m.get("cbf", "")).lower())
            # stub from bus line down to the card
            parts.append(f'<line x1="{x+cw/2}" y1="{bus_y}" x2="{x+cw/2}" y2="{y}" stroke="{color}" stroke-width="1.6"/>')
            sink = focus_parts if focus else parts
            bstroke = _HL if focus else color
            bsw = 4 if focus else 2
            bfill = "#2a2410" if focus else _PANEL
            filt = ' filter="url(#glow)"' if focus else ""
            sink.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="10" fill="{bfill}" stroke="{bstroke}" stroke-width="{bsw}"{filt}/>')
            name = (m.get("name") or m.get("id") or "")[:30]
            sink.append(f'<text x="{x+12}" y="{y+27}" fill="{_TXT}" font-size="15" font-weight="{"600" if focus else "500"}">{escape(name)}</text>')
            if m.get("lin"):
                sub = (m.get("slaves") or "")[:36]
                sink.append(f'<text x="{x+12}" y="{y+48}" fill="{color}" font-size="12">{escape(sub)}</text>')
            else:
                sink.append(f'<text x="{x+12}" y="{y+48}" fill="{pcol}" font-size="14" font-family="monospace">{proto.upper()} · {_canid(m.get("tx"))}</text>')
            if focus:
                tag = _pick(_T["focus_tag"], lang)
                tw = 14 + len(tag) * 8
                sink.append(f'<rect x="{x+cw-tw}" y="{y-15}" width="{tw}" height="22" rx="11" fill="{_HL}"/>')
                sink.append(f'<text x="{x+cw-tw/2}" y="{y+1}" fill="#1a1400" font-size="13" font-weight="700" text-anchor="middle">{escape(tag)}</text>')
            mid = str(m.get("id", "")).lower()
            if mid in _LIN_MASTER_ID.values():
                master_centers[mid] = (x + cw / 2, y + ch, x)

    parts.extend(focus_parts)

    # ---- LIN sub-nets: each connects to its master ECU, not to the gateway ----
    lcolor = LIN_BUS["color"]
    lbl = f'{_pick(LIN_BUS["name"], lang)} · {LIN_BUS["speed"]}'
    parts.append(f'<rect x="{margin}" y="{lin_label_y}" width="14" height="14" rx="3" fill="{lcolor}"/>')
    parts.append(f'<text x="{margin+22}" y="{lin_label_y+12}" fill="{_TXT}" font-size="15" font-weight="600">{escape(lbl)}</text>')
    parts.append(f'<text x="{margin+22+len(lbl)*8+18}" y="{lin_label_y+12}" fill="{_MUTED}" font-size="13">{escape(_pick(LIN_BUS["note"], lang))}</text>')
    fallback_x = margin
    conns, cards = [], []
    for card in _lin_cards(lang):
        mc = master_centers.get(card.get("mid"))
        if mc:
            mcx, mbottom, lx = mc  # align the LIN card under its master column
        else:
            lx = fallback_x
            fallback_x += cw + cgap
        ly = lin_cards_top
        lcx = lx + cw / 2
        cards.append(f'<rect x="{lx}" y="{ly}" width="{cw}" height="{ch}" rx="10" fill="{_PANEL}" stroke="{lcolor}" stroke-width="2"/>')
        cards.append(f'<text x="{lx+12}" y="{ly+27}" fill="{_TXT}" font-size="15" font-weight="500">{escape(card["name"])}</text>')
        cards.append(f'<text x="{lx+12}" y="{ly+48}" fill="{lcolor}" font-size="12">{escape((card.get("slaves") or "")[:36])}</text>')
        if mc:
            # orthogonal connector routed through the column gutter (no card crossing)
            gut = min(lx + cw + cgap / 2, W - margin - 4)
            conns.append(
                f'<path d="M {mcx} {mbottom} V {mbottom+8} H {gut} V {ly-10} H {lcx} V {ly}" '
                f'fill="none" stroke="{lcolor}" stroke-width="2.5"/>')
    parts.extend(conns)   # under the cards
    parts.extend(cards)

    parts.append("</svg>")
    return "".join(parts)


def cylinder_layout(module: dict | None = None, count: int = 6, lang: str = "ru") -> str:
    title = _pick(_T["cyl_title"], lang)
    note = _pick(_T["cyl_note"], lang)
    per = (count + 1) // 2
    cw, gap = 84, 16
    W = 40 + per * (cw + gap)
    H = 260
    parts = [
        f'<svg viewBox="0 0 {int(W)} {H}" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Roboto,sans-serif">',
        f'<rect width="{int(W)}" height="{H}" fill="{_BG}"/>',
        f'<text x="20" y="28" fill="{_TXT}" font-size="14" font-weight="600">{escape(title)}</text>',
    ]
    banks = [("A", 70), ("B", 150)] if count > 4 else [("", 110)]
    n = 1
    for bank, by in banks:
        if bank:
            parts.append(f'<text x="20" y="{by+30}" fill="{_MUTED}" font-size="12">{bank}</text>')
        for j in range(per):
            if n > count:
                break
            x = 40 + j * (cw + gap)
            parts.append(f'<rect x="{x}" y="{by}" width="{cw}" height="58" rx="10" fill="{_PANEL}" stroke="{_UDS}"/>')
            parts.append(f'<rect x="{x+cw/2-7}" y="{by-14}" width="14" height="16" rx="3" fill="{_KWP}"/>')  # injector
            parts.append(f'<text x="{x+cw/2}" y="{by+35}" fill="{_TXT}" font-size="18" font-weight="600" text-anchor="middle">{n}</text>')
            n += 1
    parts.append(f'<text x="20" y="{H-16}" fill="{_MUTED}" font-size="11">{escape(note)}</text>')
    parts.append("</svg>")
    return "".join(parts)
