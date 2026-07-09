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
    addrs = sorted({_ascii(a.group()) for a in ADDR_RE.finditer(data)})
    out["addresses"] = addrs[:12]

    out["flash_service"] = bool(re.search(rb"WVC_FlashProg|FlashProg|Reprogram", data))
    out["sw_markers"] = sorted({_ascii(s) for s in
                                re.findall(rb"SW_[A-Z_]+", data)})[:8]
    return out


# --- binary flash-segment parser -------------------------------------------
# Ports CaesarSuite's CaesarFlashContainer / FlashHeader / FlashDataBlock /
# FlashSegment (jglim/CaesarSuite) onto the shared Caesar bitflag reader, to get
# the REAL structure: data blocks and their flash segments with load address,
# length and verified file offset (so bytes can be read out / hex-viewed).
def parse_flash(data: bytes) -> dict:
    from caesar_comparam import Reader, Bitflags, STUB_HEADER_SIZE
    from caesar_vc import rf_int, rf_str
    r = Reader(data)
    r.seek(STUB_HEADER_SIZE)
    cff_size = r.i32()
    base = r.tell()                       # CFF header BaseAddress
    bf = Bitflags(r.u32()); r.u16()       # FlashHeader: 32-bit bitflags + skip
    # full FlashHeader, kept under the original Caesar tag names (for the XML dump)
    H = {}
    H["FlashName"] = rf_str(r, bf, base)
    H["FlashGenerationParams"] = rf_str(r, bf, base)
    H["Unk3"] = rf_int(r, bf, 4)
    H["Unk4"] = rf_int(r, bf, 4)
    H["FileAuthor"] = rf_str(r, bf, base)
    H["FileCreationTime"] = rf_str(r, bf, base)
    H["AuthoringToolVersion"] = rf_str(r, bf, base)
    H["FTRAFOVersionString"] = rf_str(r, bf, base)
    H["FTRAFOVersionNumber"] = rf_int(r, bf, 4)
    H["CFFVersionString"] = rf_str(r, bf, base)
    H["NumberOfFlashAreas"] = rf_int(r, bf, 4)
    H["FlashDescriptionTable"] = rf_int(r, bf, 4)
    H["DataBlockTableCount"] = rf_int(r, bf, 4)
    H["DataBlockRefTable"] = rf_int(r, bf, 4)
    H["CTFHeaderTable"] = rf_int(r, bf, 4)
    H["LanguageBlockLength"] = rf_int(r, bf, 4)
    H["NumberOfECURefs"] = rf_int(r, bf, 4)
    H["ECURefTable"] = rf_int(r, bf, 4)
    H["UnkTableCount"] = rf_int(r, bf, 4)
    H["UnkTableProbably"] = rf_int(r, bf, 4)
    H["Unk15"] = rf_int(r, bf, 1)
    db_ref_table, lang_block_len = H["DataBlockRefTable"], H["LanguageBlockLength"]
    blocks = []
    for di in range(H["DataBlockTableCount"]):
        r.seek(db_ref_table + base + di * 4)
        db_base = db_ref_table + base + r.i32()
        r.seek(db_base)
        dbf = Bitflags(r.u32()); r.u16()
        B = {}
        B["Qualifier"] = rf_str(r, dbf, db_base)
        B["LongName"] = rf_int(r, dbf, 4)
        B["Description"] = rf_int(r, dbf, 4)
        B["FlashData"] = rf_int(r, dbf, 4)
        B["BlockLength"] = rf_int(r, dbf, 4)
        B["DataFormat"] = rf_int(r, dbf, 4)
        B["FileName"] = rf_int(r, dbf, 4)
        B["NumberOfFilters"] = rf_int(r, dbf, 4)
        B["FiltersOffset"] = rf_int(r, dbf, 4)
        B["NumberOfSegments"] = rf_int(r, dbf, 4)
        B["SegmentOffset"] = rf_int(r, dbf, 4)
        seg_off, flash_data = B["SegmentOffset"], B["FlashData"]
        segs = []; cursor = 0
        for si in range(B["NumberOfSegments"]):
            r.seek(seg_off + db_base + si * 4)
            seg_base = seg_off + db_base + r.i32()
            r.seek(seg_base)
            sbf = Bitflags(r.u16())                           # FlashSegment: 16-bit bitflags
            from_addr = rf_int(r, sbf, 4)
            seg_len = rf_int(r, sbf, 4)
            rf_int(r, sbf, 4)                                 # Unk3
            seg_name = rf_str(r, sbf, seg_base)
            file_off = flash_data + cff_size + lang_block_len + cursor + 0x414
            cursor += seg_len
            segs.append({"name": seg_name, "from_address": from_addr,
                         "length": seg_len, "file_offset": file_off,
                         "in_bounds": 0 <= file_off and file_off + seg_len <= len(data)})
        blocks.append({"qualifier": B["Qualifier"], "flash_data": B["FlashData"],
                       "fields": B, "segments": segs})
    return {
        "cff_header_size": cff_size, "size": len(data),
        "header": H, "blocks": blocks,
        # convenience aliases for the viewer
        "flash_name": H["FlashName"], "file_author": H["FileAuthor"],
        "file_creation_time": H["FileCreationTime"],
        "authoring_tool_version": H["AuthoringToolVersion"],
        "cff_version": H["CFFVersionString"],
    }


def parse_flash_file(path) -> dict:
    return parse_flash(Path(path).read_bytes())


def flash_to_xml(name: str, parsed: dict) -> str:
    """Lay the parsed CFF out as XML, element-per-tag (header / data block /
    segment fields under their original Caesar names)."""
    from xml.sax.saxutils import escape, quoteattr
    HEXTAGS = {"FlashData", "SegmentOffset", "FiltersOffset", "FlashDescriptionTable",
               "DataBlockRefTable", "CTFHeaderTable", "ECURefTable"}

    def el(tag, val, ind, hexed=False):
        if val is None:
            return f"{ind}<{tag}/>"
        txt = f"0x{val:X}" if (hexed and isinstance(val, int)) else escape(str(val))
        return f"{ind}<{tag}>{txt}</{tag}>"

    L = ['<?xml version="1.0" encoding="UTF-8"?>',
         f'<CaesarFlashContainer file={quoteattr(name + ".cff")} '
         f'size="{parsed.get("size", 0)}" cffHeaderSize="{parsed.get("cff_header_size", 0)}">',
         '  <FlashHeader>']
    for k, v in (parsed.get("header") or {}).items():
        L.append(el(k, v, "    ", k in HEXTAGS))
    L.append('  </FlashHeader>')
    blocks = parsed.get("blocks") or []
    L.append(f'  <DataBlocks count="{len(blocks)}">')
    for b in blocks:
        L.append('    <FlashDataBlock>')
        for k, v in (b.get("fields") or {}).items():
            L.append(el(k, v, "      ", k in HEXTAGS))
        segs = b.get("segments") or []
        L.append(f'      <FlashSegments count="{len(segs)}">')
        for s in segs:
            L.append('        <FlashSegment>')
            L.append(el("SegmentName", s.get("name"), "          "))
            L.append(f'          <FromAddress>0x{s.get("from_address", 0):X}</FromAddress>')
            L.append(f'          <SegmentLength>0x{s.get("length", 0):X}</SegmentLength>')
            L.append(f'          <FileOffset>0x{s.get("file_offset", 0):X}</FileOffset>')
            L.append(f'          <InBounds>{str(bool(s.get("in_bounds"))).lower()}</InBounds>')
            L.append('        </FlashSegment>')
        L.append('      </FlashSegments>')
        L.append('    </FlashDataBlock>')
    L.append('  </DataBlocks>')
    L.append('</CaesarFlashContainer>')
    return "\n".join(L)


def main(argv):
    for a in argv[1:]:
        print(json.dumps(parse_cff(Path(a)), ensure_ascii=False, indent=2))
        print(json.dumps(parse_flash_file(Path(a)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv)
