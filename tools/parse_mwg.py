#!/usr/bin/env python3
"""
Parse Vediamo/Ecoute .mwg measurement windows.

Two formats occur in the local Vediamo data:
  * Ecoute INI files with [Entries] ServiceN=ECU:JOB lines.
  * XML service-group files that are structurally the same as .vsg files.

The returned shape intentionally matches tools/parse_vsg.py so the backend can
index both sources through one measurement/service API.
"""

from __future__ import annotations

import configparser
import json
import re
import sys
from pathlib import Path

import parse_vsg


_SERVICE_RE = re.compile(r"^([^:]+):(.+)$")


def _kind(job: str) -> str:
    if job.startswith(("RT_", "FN_", "ON_", "OFF_", "ST_")):
        return "routine"
    if job.startswith("ADJ_"):
        return "adapt"
    return "data"


def _title(path: Path, raw: str) -> str:
    for line in raw.splitlines()[:8]:
        line = line.strip()
        if not line.startswith(";"):
            continue
        text = line[1:].strip()
        if not text or text.lower().startswith(("version:", "system:", "datum:")):
            continue
        text = text.replace("\\", "/").rsplit("/", 1)[-1]
        return re.sub(r"\.mwg$", "", text, flags=re.I).replace("_", " ").strip()
    return path.stem.replace("_", " ")


def parse_mwg(path: Path) -> dict:
    raw = path.read_text(encoding="latin-1", errors="replace")
    if raw.lstrip().startswith("<"):
        return parse_vsg.parse_vsg(path)

    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    cp.read_string(raw)

    services = []
    ecu = ""
    entries = cp["Entries"] if cp.has_section("Entries") else {}
    try:
        count = int(entries.get("Count", "0"))
    except ValueError:
        count = 0
    keys = [f"Service{i}" for i in range(1, count + 1)] if count else sorted(
        k for k in entries if k.lower().startswith("service"))

    for key in keys:
        val = (entries.get(key) or "").strip()
        if not val or val.startswith("$"):
            continue
        m = _SERVICE_RE.match(val)
        if not m:
            continue
        e, job = m.group(1).strip(), m.group(2).strip()
        if not e or not job:
            continue
        ecu = ecu or e
        services.append({
            "job": job, "ecu": e, "alias": "", "unit": "",
            "kind": _kind(job), "low": None, "high": None, "valmap": None,
        })

    kind = "service" if any(s["kind"] == "routine" for s in services) else "measurement"
    return {"file": path.name, "title": _title(path, raw), "ecu": ecu,
            "kind": kind, "count": len(services), "services": services}


def main(argv):
    for a in argv[1:]:
        print(json.dumps(parse_mwg(Path(a)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv)
