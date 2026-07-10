"""
Variant coding for macDiag - decode/encode a coding string into named options.

Uses tools/caesar_vc.py to parse VC domains/fragments/subfragments from the
ECU's CBF file. CBF files live in the user's Vediamo library (not shipped); set
the directory via env var MACDIAG_CBF_DIR (defaults to ./cbf).

Read/write on the car: each domain exposes a read service (RVC_..._Lesen) and a
write service (WVC_..._Schreiben). The coding bytes are obtained from the ECU
via that read service, decoded here, edited, then written back.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))
import caesar_vc as vc  # noqa: E402

CBF_DIR = Path(os.environ.get("MACDIAG_CBF_DIR",
                              str(Path(__file__).resolve().parent.parent.parent / "data" / "cbf")))


@lru_cache(maxsize=1)
def _index() -> dict:
    """ecu name (upper) -> CBF path."""
    idx = {}
    if CBF_DIR.exists():
        for p in CBF_DIR.rglob("*"):
            if p.suffix.lower() == ".cbf":
                idx[p.stem.upper()] = p
    return idx


def available() -> bool:
    return bool(_index())


def cbf_for(ecu: str) -> Path | None:
    return _index().get((ecu or "").upper())


@lru_cache(maxsize=32)
def _parsed(ecu: str):
    p = cbf_for(ecu)
    if not p:
        return None
    return vc.parse_vc(p)


def list_domains(ecu: str) -> list[dict]:
    res = _parsed(ecu)
    if not res:
        return []
    out = []
    seen = set()
    for d in res["domains"]:
        if "error" in d:
            continue
        # Some CBFs repeat the same VC domain in multiple internal variant
        # blocks. _find_domain() intentionally resolves the first match, so
        # expose that same stable choice once instead of returning duplicate
        # select options (and duplicate React keys) to API clients.
        if d["domain"] in seen:
            continue
        seen.add(d["domain"])
        out.append({
            "domain": d["domain"], "dump_size": d["dump_size"],
            "read_service": d["read_service"], "write_service": d["write_service"],
            "read_lid": d.get("read_lid"), "write_lid": d.get("write_lid"),
            "sec_level": d.get("write_sec_level"),
            "fragment_count": len(d["fragments"]),
        })
    return out


def _find_domain(ecu: str, domain: str) -> dict | None:
    res = _parsed(ecu)
    if not res:
        return None
    for d in res["domains"]:
        if d.get("domain") == domain:
            return d
    return None


def domain_meta(ecu: str, domain: str) -> dict | None:
    d = _find_domain(ecu, domain)
    if not d:
        return None
    return {"dump_size": d["dump_size"], "read_service": d["read_service"],
            "write_service": d["write_service"],
            "read_lid": d.get("read_lid"), "write_lid": d.get("write_lid"),
            "read_sid": d.get("read_sid"), "write_sid": d.get("write_sid"),
            "read_sec_level": d.get("read_sec_level"),
            "write_sec_level": d.get("write_sec_level")}


def decode(ecu: str, domain: str, coding: bytes) -> dict | None:
    d = _find_domain(ecu, domain)
    if not d:
        return None
    frags = [vc.decode_fragment(f, coding) for f in d["fragments"]]
    return {"domain": d["domain"], "dump_size": d["dump_size"],
            "read_service": d["read_service"], "write_service": d["write_service"],
            "coding": coding.hex().upper(), "fragments": frags}


def coding_xml(ecu: str) -> str | None:
    """Lay the CBF's variant-coding structure out as XML, element-per-tag
    (domains -> fragments -> bit position/length -> options) - the CxF-Viewer
    style 'which bytes mean what' dump, from the static CBF (no live values)."""
    from xml.sax.saxutils import escape, quoteattr
    res = _parsed(ecu)
    if not res:
        return None
    domains = [d for d in res["domains"] if "error" not in d]
    L = ['<?xml version="1.0" encoding="UTF-8"?>',
         f'<CaesarCbfCoding ecu={quoteattr(ecu)} domains="{len(domains)}">']
    for d in domains:
        frags = [vc.decode_fragment(f, bytes(d["dump_size"])) for f in d["fragments"]]
        L.append(f'  <VcDomain name={quoteattr(d["domain"])} dumpSize="{d["dump_size"]}" '
                 f'readService={quoteattr(d.get("read_service") or "")} '
                 f'writeService={quoteattr(d.get("write_service") or "")}>')
        for fr in frags:
            L.append(f'    <Fragment name={quoteattr(str(fr.get("name") or ""))} '
                     f'byteBitPos="{fr.get("byte_bit_pos")}" bitLength="{fr.get("bit_length")}">')
            for i, opt in enumerate(fr.get("options") or []):
                L.append(f'      <Option index="{i}">{escape(str(opt))}</Option>')
            L.append('    </Fragment>')
        L.append('  </VcDomain>')
    L.append('</CaesarCbfCoding>')
    return "\n".join(L)


def encode(ecu: str, domain: str, coding: bytes,
           fragment_name: str, option: str) -> bytes | None:
    d = _find_domain(ecu, domain)
    if not d:
        return None
    frag = next((f for f in d["fragments"] if f["name"] == fragment_name), None)
    if frag is None:
        raise ValueError(f"fragment '{fragment_name}' not found")
    return vc.set_option(frag, coding, option)
