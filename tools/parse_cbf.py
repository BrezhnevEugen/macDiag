#!/usr/bin/env python3
"""
CBF (Caesar Binary Format) metadata extractor for Vediamo / DAS ECU files.

This does NOT fully decode the proprietary Caesar block structure (that is a
large reverse-engineering effort, see the CaesarSuite project). It reliably
extracts the human-meaningful metadata that lives as text in every CBF:

    * ECU name, CBF translator/target version, build date, fingerprint
    * communication template  -> diagnostic protocol (KWP2000CAN vs UDS/HSCAN)
    * Teilenummern (MB part numbers)
    * variant names (e.g. W164_0006)
    * bus configurations (LSCAN/HSCAN + baudrate)
    * COMPARAM names (incl. the CAN-identifier parameters - names only)
    * diagnostic job / service identifiers

Usage:
    python tools/parse_cbf.py FILE.cbf [FILE2.cbf ...]      # print JSON
    python tools/parse_cbf.py --dir DIR --out catalog.json  # scan a folder
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HEADER_KEYS = ("CBF-TRANSLATOR-VERSION", "TARGET-RELEASE", "DATE",
               "GPD-TRANSLATOR-VERSION", "FINGERPRINT", "CBF", "LANGUAGE")

# protocol templates seen in MB CBFs
PROTO_TEMPLATES = {
    "KWP2000CAN": "kwp",      # KWP2000 over CAN
    "KWP2000": "kwp",
    "UDS": "uds",
    "HSCAN": "uds",
    "DIOGENES": "uds",
}

PART_RE = re.compile(rb"(\d{3} \d{3} \d{2} \d{2})")
VARIANT_RE = re.compile(rb"[A-Z]\d{3}_\d{4}")
BAUD_RE = re.compile(rb"([LH]SCAN)\s*\(([^)]*?(\d{2,4}(?:\.\d)?))\)")
# COMPARAM names
CP_RE = re.compile(rb"CP_[A-Z0-9_]+")
# candidate job/service identifiers: long upper tokens with underscores/digits
JOB_RE = re.compile(rb"[A-Z][A-Z0-9_]{4,40}")
# vehicle chassis codes: body letter + 3-digit Mercedes Baureihe (e.g. W221).
# Restricted to the real <body><Baureihe> codes that actually exist, so a valid
# Baureihe number paired with an impossible body (e.g. "S140", "A117") from
# random binary is not mistaken for a car.
CHASSIS_RE = re.compile(rb"\b([WXSCARV]\d{3})\b")
REAL_CHASSIS = {
    "W168", "W169", "W176", "W177",                                  # A
    "W245", "W246", "W247",                                          # B
    "W202", "W203", "W204", "W205", "S202", "S203", "S204", "S205",  # C sedan/estate
    "C204", "C205", "A205",                                          # C coupe/cabrio
    "W210", "W211", "W212", "W213", "S210", "S211", "S212", "S213",  # E sedan/estate
    "C207", "C238", "A207", "A238",                                  # E coupe/cabrio
    "W140", "W220", "W221", "W222", "V221", "V222",                  # S sedan/LWB
    "C215", "C216", "C217", "A217",                                  # S/CL coupe/cabrio
    "W219", "C218", "C257", "X218",                                  # CLS
    "C208", "A208", "C209", "A209",                                  # CLK
    "R129", "R230", "R231",                                          # SL
    "R170", "R171", "R172",                                          # SLK/SLC
    "C190", "C197", "R197",                                          # SLS / AMG GT
    "W163", "W164", "W166", "W167", "C292", "C167",                  # ML/GLE
    "X164", "X166", "X167",                                          # GL/GLS
    "X204", "X253", "C253",                                          # GLK/GLC
    "X156", "X117", "C117",                                          # GLA/CLA
    "W463", "W461",                                                  # G
    "W251", "V251",                                                  # R
    "W447", "W639", "W638", "W414",                                  # Vito/V/Vaneo
    "W240", "X222",                                                  # Maybach
    "W905", "W906", "W907",                                          # Sprinter
}


def _ascii(bs: bytes) -> str:
    return bs.decode("latin-1", "replace")


def parse_cbf(path: Path) -> dict:
    data = path.read_bytes()
    head = data[:512]
    out: dict = {"file": path.name, "size": len(data)}

    # header lines (NL-separated KEY:VALUE)
    for line in _ascii(head).split("\n"):
        if ":" in line:
            k, _, v = line.partition(":")
            if k in HEADER_KEYS:
                out.setdefault("header", {})[k] = v.strip()

    # ECU name: first 'CBF:<name>' value or filename stem
    m = re.search(rb"CBF:([A-Za-z0-9_]+)", head)
    out["ecu"] = _ascii(m.group(1)) if m else path.stem

    # protocol template ("Based on template: KWP2000CAN 1.2.8")
    tm = re.search(rb"Based on template:\s*([A-Za-z0-9 .]+)", data)
    template = _ascii(tm.group(1)).strip() if tm else ""
    out["template"] = template
    proto = "uds"
    for key, p in PROTO_TEMPLATES.items():
        if key in template.upper():
            proto = p
            break
    out["protocol"] = proto

    # part numbers (dedup, keep order)
    parts, seen = [], set()
    for m in PART_RE.finditer(data):
        s = _ascii(m.group(1))
        if s not in seen:
            seen.add(s); parts.append(s)
    out["part_numbers"] = parts[:20]

    # variants
    out["variants"] = sorted({_ascii(m.group(0)) for m in VARIANT_RE.finditer(data)})

    # bus configs
    buses = {}
    for m in BAUD_RE.finditer(data):
        buses[_ascii(m.group(1))] = _ascii(m.group(3))
    out["bus"] = buses

    # comparam names
    out["comparams"] = sorted({_ascii(m.group(0)) for m in CP_RE.finditer(data)})

    # chassis association: pull <body><Baureihe> tokens the ECU mentions
    # (W221, X164, S212, C216, R231, …), validating the 3-digit Baureihe against
    # the real Mercedes series so random binary bytes are not mistaken for cars.
    # Body letters: W sedan, S estate, C coupe, A cabrio, R roadster, X SUV,
    # V long/MPV. Shared ECUs are correctly tagged with every car they serve.
    counts: dict[str, int] = {}
    for m in CHASSIS_RE.finditer(data):
        code = m.group(1).decode()
        if code in REAL_CHASSIS:
            counts[code] = counts.get(code, 0) + 1
    # require the code to recur: a lone match is usually random binary, a real
    # platform association is referenced repeatedly in the descriptor.
    out["chassis"] = sorted(c for c, n in counts.items() if n >= 2)

    # diagnostic jobs / services (filter out noise & known non-jobs)
    NOISE = {"ORIGINAL", "LANGUAGE", "VERSION", "TARGET", "FINGERPRINT",
             "TRANSLATOR", "SELECTION", "DOCUMENT", "ENTITY", "PROTOCOL"}
    jobs, jseen = [], set()
    for m in JOB_RE.finditer(data):
        s = _ascii(m.group(0))
        if s in jseen or s in NOISE or s.startswith("CP_"):
            continue
        if any(s.startswith(p) for p in ("DE", "DTD", "XML", "GPD", "DIOGENES")):
            continue
        jseen.add(s); jobs.append(s)
    out["jobs"] = jobs[:120]

    return out


def main(argv):
    if "--dir" in argv:
        d = Path(argv[argv.index("--dir") + 1])
        files = sorted(p for p in d.iterdir()
                       if p.suffix.lower() == ".cbf")
        catalog = []
        for f in files:
            try:
                catalog.append(parse_cbf(f))
            except Exception as e:  # noqa: BLE001
                catalog.append({"file": f.name, "error": str(e)})
        out = json.dumps(catalog, ensure_ascii=False, indent=2)
        if "--out" in argv:
            Path(argv[argv.index("--out") + 1]).write_text(out, encoding="utf-8")
            print(f"wrote {len(catalog)} entries")
        else:
            print(out)
        return
    for a in argv[1:]:
        print(json.dumps(parse_cbf(Path(a)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv)
