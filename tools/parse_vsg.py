#!/usr/bin/env python3
"""
Parse Vediamo .vsg (Service Group) XML into a measurement/service group.

A .vsg is an engineer-built screen: a list of diagnostic jobs to read/trigger,
with alias, unit, limits and value maps. Job-name prefixes:
    DT_   data parameter (live measurement, read)
    ADJ_  adjustment / adaptation value (read)
    RT_/FN_ routine / actuator test (service procedure)
    ON_/OFF_/ST_  actuator control

We classify a group as 'service' if it contains routines/actuators (RT_/ON_/OFF_
or an <actors> block) and 'measurement' otherwise.

Usage:
    python tools/parse_vsg.py FILE.vsg
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _num(v):
    try:
        f = float(v)
        return int(f) if f == int(f) else round(f, 4)
    except (TypeError, ValueError):
        return None


def parse_vsg(path: Path) -> dict:
    raw = path.read_text(encoding="latin-1", errors="replace")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        # some files have stray ampersands; sanitize
        root = ET.fromstring(re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;)", "&amp;", raw))

    title = ""
    ecu = ""
    dw = root.find(".//diagwin")
    if dw is not None:
        title = (dw.get("title") or "").strip()

    services = []
    has_routine = False
    for s in root.findall(".//service"):
        job = (s.text or "").strip()
        if not job:
            continue
        e = (s.get("ECU") or "").lstrip("? ").strip()
        ecu = ecu or e
        valmap = {}
        for k in s.findall("valmap/key"):
            valmap[_num(k.get("value"))] = (k.text or "").strip()
        kind = ("routine" if job.startswith(("RT_", "FN_", "ON_", "OFF_", "ST_"))
                else "adapt" if job.startswith("ADJ_")
                else "data")
        if kind == "routine":
            has_routine = True
        services.append({
            "job": job, "ecu": e, "alias": (s.get("alias") or "").strip(),
            "unit": (s.get("unit") or "").strip(), "kind": kind,
            "low": _num(s.get("lowlimit")), "high": _num(s.get("uplimit")),
            "valmap": valmap or None,
        })

    # some files put a Windows path / filename in the title attribute instead
    # of a readable name - fall back to the .vsg file name in that case
    if (not title or "\\" in title or "/" in title
            or title.lower().endswith((".vsg", ".mwg", ".mvg"))):
        title = path.stem.replace("_", " ")
    kind = "service" if has_routine else "measurement"
    return {"file": path.name, "title": title, "ecu": ecu,
            "kind": kind, "count": len(services), "services": services}


def main(argv):
    for a in argv[1:]:
        print(json.dumps(parse_vsg(Path(a)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv)
