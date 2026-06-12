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

    # chassis association: scan content for BRxxx / Wxxx / Baureihe tokens
    chassis = set()
    CH_MAP = {rb"BR164": "X164", rb"W164": "X164", rb"Baureihe 164": "X164",
              rb"BR221": "W221", rb"W221": "W221", rb"Baureihe 221": "W221",
              rb"BR251": "W251", rb"BR216": "C216"}
    for tok, name in CH_MAP.items():
        if tok in data:
            chassis.add(name)
    out["chassis"] = sorted(chassis)

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
