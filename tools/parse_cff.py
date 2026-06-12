#!/usr/bin/env python3
"""
Read-only CFF (flash image) metadata extractor.

CFF is the Caesar flash-container format (`CFF-TRANSLATOR-VERSION` header, sibling
of CBF). This pulls the human-meaningful metadata that lives as text: ECU, part
number, build date, fingerprint (chassis hint), flash segments (Applikation /
Parameterdaten / Bootloader), their load addresses, and SW version markers.

It does NOT decode/decrypt the flash payload or drive any programming - that is a
deliberate future iteration (see backend/mb/flash.py). This is purely for
identifying and cataloguing flash files.

Usage:
    python tools/parse_cff.py FILE.cff
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PART_RE = re.compile(rb"\b(\d{10}_\d{3})\b")
ADDR_RE = re.compile(rb"0x[0-9A-Fa-f]{6,8}")
SEG_HINTS = (b"Applikation", b"Parameterdaten", b"Bootloader", b"Bedatung",
             b"Flashdaten", b"Kalibrationsdaten")


def _ascii(b: bytes) -> str:
    return b.decode("latin-1", "replace")


def parse_cff(path: Path) -> dict:
    data = path.read_bytes()
    head = data[:1024]
    out: dict = {"file": path.name, "size": len(data)}

    for line in _ascii(head).split("\n"):
        if ":" in line:
            k, _, v = line.partition(":")
            if k in ("CFF-TRANSLATOR-VERSION", "DATE", "FINGERPRINT", "CFF"):
                out.setdefault("header", {})[k] = v.strip()

    m = re.search(rb"CFF:([A-Za-z0-9_]+)", head)
    out["ecu"] = _ascii(m.group(1)) if m else path.stem

    # fingerprint's first number is a Baureihe hint (e.g. 221.x -> W221)
    fp = out.get("header", {}).get("FINGERPRINT", "")
    out["chassis_hint"] = fp.split(".")[0] if fp else ""

    parts, seen = [], set()
    for m in PART_RE.finditer(data):
        s = _ascii(m.group(1))
        if s not in seen:
            seen.add(s); parts.append(s)
    out["part_numbers"] = parts[:10]

    # flash segments present (by name) + any explicit load addresses
    segs = [_ascii(h) for h in SEG_HINTS if h in data]
    out["segments"] = segs
    addrs = sorted({_ascii(a) for a in ADDR_RE.finditer(data)})
    out["addresses"] = addrs[:12]

    out["flash_service"] = bool(re.search(rb"WVC_FlashProg|FlashProg|Reprogram", data))
    out["sw_markers"] = sorted({_ascii(s) for s in
                                re.findall(rb"SW_[A-Z_]+", data)})[:8]
    return out


def main(argv):
    for a in argv[1:]:
        print(json.dumps(parse_cff(Path(a)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv)
