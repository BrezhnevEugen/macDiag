#!/usr/bin/env python3
"""
Caesar/CBF variant-coding parser: extracts VC domains, fragments (coding
parameters) and subfragments (named enum options), and decodes/encodes a coding
string into human-readable options.

Partial port of jglim/CaesarSuite (MIT): CFFHeader -> CTF language strings ->
ECU -> VCDomain -> VCFragment -> VCSubfragment.

Bit order: coding bytes are expanded LSB-first per byte (BitUtility little-endian),
ByteBitPos indexes into that bit array.

Usage:
    python tools/caesar_vc.py FILE.cbf                 # list domains + fragments
    python tools/caesar_vc.py FILE.cbf --coding HEX    # decode a coding string
"""

from __future__ import annotations

import json
import math
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from caesar_comparam import Reader, Bitflags, parse_cff, STUB_HEADER_SIZE  # noqa


FRAG_LEN_TABLE = [0, 1, 4, 8, 0x10, 0x20, 0x40]
PRESENTATION_RE = re.compile(rb"PRES_[A-Za-z0-9_]{2,120}\x00")
PRESENTATION_TYPES = {
    "BYTE": ("ubyte", 1),
    "UBYTE": ("ubyte", 1),
    "SBYTE": ("sbyte", 1),
    "WORD": ("uword", 2),
    "UWORD": ("uword", 2),
    "SWORD": ("sword", 2),
    "DWORD": ("ulong", 4),
    "UDWORD": ("ulong", 4),
    "ULONG": ("ulong", 4),
    "SLONG": ("slong", 4),
    "FLOAT": ("float", 4),
    "DOUBLE": ("double", 8),
}
PRESENTATION_SCALE_RE = re.compile(r"^(N?BIN|DEC)(\d+)$", re.I)
PRESENTATION_UNITS = {
    "A": "A",
    "ADCNT": "count",
    "AFR": "AFR",
    "AS": "A*s",
    "BAR": "bar",
    "C": "deg C",
    "CELS": "deg C",
    "CELSIUS": "deg C",
    "CNT": "count",
    "CNTS": "count",
    "DEG": "deg",
    "DEGC": "deg C",
    "EDEG": "deg",
    "G": "g",
    "H": "h",
    "HZ": "Hz",
    "HPA": "hPa",
    "K": "K",
    "KG": "kg",
    "KM": "km",
    "KMH": "km/h",
    "L": "l",
    "M3": "m3",
    "MA": "mA",
    "MG": "mg",
    "MGS": "mg/stroke",
    "MIN": "min",
    "MM": "mm",
    "MM3": "mm3",
    "MS": "ms",
    "MV": "mV",
    "NM": "Nm",
    "OHM": "Ohm",
    "PERCENT": "%",
    "PPM": "ppm",
    "PRC": "%",
    "RPM": "rpm",
    "S": "s",
    "STR": "stroke",
    "UM": "um",
    "US": "us",
    "V": "V",
    "VOLT": "V",
    "VOLTAGE": "V",
    "VOLTS": "V",
}
PRESENTATION_UNIT_COMBOS = [
    (("G", "S"), "g/s"),
    (("KG", "H"), "kg/h"),
    (("KM", "H"), "km/h"),
    (("L", "1000KM"), "l/1000km"),
    (("M3", "H"), "m3/h"),
    (("MG", "STR"), "mg/stroke"),
    (("MM3", "STR"), "mm3/stroke"),
]


# --- bitflag field helpers that RESOLVE strings/dumps -----------------------
def rf_int(r: Reader, bf: Bitflags, size: int, default: int = 0) -> int:
    if not bf.next():
        return default
    if size == 4:
        return r.i32()
    if size == 2:
        return r.i16()
    if size == 1:
        return r.i8()
    raise ValueError(size)


def rf_str(r: Reader, bf: Bitflags, base: int) -> str | None:
    if not bf.next():
        return None
    off = r.i32()
    cur = r.tell()
    s = r.cstr(off + base)
    r.seek(cur)
    return s


def rf_dump(r: Reader, bf: Bitflags, size: int, base: int) -> bytes:
    if not bf.next():
        return b""
    off = r.i32()
    cur = r.tell()
    r.seek(off + base)
    d = r.bytes(size)
    r.seek(cur)
    return d


# --- CTF language string table ----------------------------------------------
def load_ctf_strings(r: Reader, cff: dict) -> list[str]:
    base = cff["BaseAddress"] + cff["CtfOffset"]
    r.seek(base)
    bf = Bitflags(r.u16())
    rf_int(r, bf, 4)                          # CtfUnk1
    rf_str(r, bf, base)                       # Qualifier
    rf_int(r, bf, 2)                          # CtfUnk3
    rf_int(r, bf, 4)                          # CtfUnk4
    lang_count = rf_int(r, bf, 4)            # CtfLanguageCount
    lang_tbl_off = rf_int(r, bf, 4)         # CtfLanguageTableOffset
    rf_str(r, bf, base)                       # CtfUnkString
    if lang_count <= 0:
        return []
    lang_tbl = lang_tbl_off + base
    r.seek(lang_tbl)
    lang_addr = r.i32() + lang_tbl           # first language
    # language record
    r.seek(lang_addr)
    bf = Bitflags(r.u16())
    rf_str(r, bf, lang_addr)                  # Qualifier
    rf_int(r, bf, 2)                          # LanguageIndex
    rf_int(r, bf, 4)                          # StringPoolSize
    rf_int(r, bf, 4)                          # MaybeOffset
    count = rf_int(r, bf, 4)                 # StringCount
    table = cff["CffHeaderSize"] + STUB_HEADER_SIZE + 4
    out = []
    for i in range(count):
        r.seek(table + i * 4)
        soff = r.i32()
        out.append(r.cstr(table + soff))
    return out


def ctf(strings: list[str], idx: int) -> str:
    if idx is None or idx < 0 or idx >= len(strings):
        return ""
    return strings[idx]


def _presentation_tokens(name: str) -> list[str]:
    return [t.upper() for t in re.split(r"[_\s]+", name or "") if t]


def _presentation_unit(tokens: list[str]) -> str:
    ignored = {"PRES", "CON", "CM", "NA"}
    raw_tokens = set(PRESENTATION_TYPES) | {"BYTES", "HEXDUMP", "ASCII"}
    candidates = []
    for t in tokens:
        if t in ignored or t in raw_tokens:
            continue
        if t.isdigit() or PRESENTATION_SCALE_RE.match(t):
            continue
        candidates.append(t)
    for combo, unit in PRESENTATION_UNIT_COMBOS:
        for i in range(len(candidates) - len(combo) + 1):
            if tuple(candidates[i:i + len(combo)]) == combo:
                return unit
    for t in candidates:
        unit = PRESENTATION_UNITS.get(t)
        if unit:
            return unit
    return ""


def _presentation_scale(tokens: list[str]) -> dict:
    for t in tokens:
        m = PRESENTATION_SCALE_RE.match(t)
        if not m:
            continue
        kind = m.group(1).upper()
        power = int(m.group(2))
        if kind == "BIN":
            divisor = 2 ** power
            return {"scale_kind": "binary",
                    "formula": "x" if divisor == 1 else f"x / {divisor}"}
        if kind == "DEC":
            divisor = 10 ** power
            return {"scale_kind": "decimal",
                    "formula": "x" if divisor == 1 else f"x / {divisor}"}
        return {"scale_kind": "", "formula": ""}
    return {"scale_kind": "", "formula": ""}


def _num(v: float) -> str:
    for places in range(0, 7):
        rounded = round(v, places)
        if abs(v - rounded) <= max(1e-8, abs(v) * 1e-6):
            v = rounded
            break
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.9g}"


def _linear_formula(factor: float, offset: float) -> str:
    if abs(factor) < 1e-12 and abs(offset) < 1e-12:
        return ""
    parts = []
    if abs(factor - 1.0) < 1e-9:
        parts.append("x")
    elif abs(factor + 1.0) < 1e-9:
        parts.append("-x")
    else:
        parts.append(f"x * {_num(factor)}")
    if abs(offset) >= 1e-9:
        op = "+" if offset > 0 else "-"
        parts.append(f"{op} {_num(abs(offset))}")
    return " ".join(parts)


def _raw_type_from_range(low: int, high: int) -> tuple[str, int]:
    if low < 0:
        if -0x80 <= low and high <= 0x7F:
            return "sbyte", 1
        if -0x8000 <= low and high <= 0x7FFF:
            return "sword", 2
        if -0x80000000 <= low and high <= 0x7FFFFFFF:
            return "slong", 4
        return "bytes", 0
    if high <= 0xFF:
        return "ubyte", 1
    if high <= 0xFFFF:
        return "uword", 2
    if high <= 0xFFFFFFFF:
        return "ulong", 4
    return "bytes", 0


def _presentation_enum_meta(data: bytes, pos: int, kind: int, method: int) -> dict | None:
    """Recognize compact enum/range records after a PRES_* qualifier."""
    if kind < 8 or kind % 4 != 0 or method != kind + 0x0E:
        return None
    count = kind // 4
    entry = pos + kind
    if entry + count * 14 > len(data):
        return None
    lows = []
    highs = []
    for i in range(count):
        off = entry + i * 14
        marker = struct.unpack_from("<H", data, off)[0]
        if marker != 0x0403:
            return None
        low, high = struct.unpack_from("<ii", data, off + 2)
        lows.append(low)
        highs.append(high)
    nonnegative_highs = [v for v in highs if v >= 0]
    if not nonnegative_highs:
        return None
    low = min([v for v in lows if v >= 0] or [0])
    high = max(nonnegative_highs)
    raw_type, byte_len = _raw_type_from_range(low, high)
    return {
        "raw_type": raw_type,
        "byte_len": byte_len,
        "scale_kind": "enum",
        "formula": "",
        "source": "cbf_presentation_enum_record",
    }


def presentation_meta(name: str) -> dict:
    """Infer coarse output metadata from a PRES_* qualifier.

    This is not yet the Caesar output-presentation formula parser; it gives the
    DB a stable first hook for coverage and future scaling work.
    """
    up = (name or "").upper()
    tokens = _presentation_tokens(name)
    raw_type = ""
    byte_len = 0
    scale = {"scale_kind": "", "formula": ""}
    if "HEXDUMP" in up:
        raw_type = "hexdump"
        m = re.search(r"HEXDUMP[_\s]*(\d+)(?:[_\s]*(?:BYTE|BYTES))?", up)
        if m:
            byte_len = int(m.group(1))
    elif re.search(r"\d+\s*BYTE\s*DUMP", up):
        raw_type = "hexdump"
        m = re.search(r"(\d+)\s*BYTE\s*DUMP", up)
        byte_len = int(m.group(1)) if m else 0
    elif re.search(r"\d+\s*BYTE\s*BCD", up):
        raw_type = "bcd"
        m = re.search(r"(\d+)\s*BYTE\s*BCD", up)
        byte_len = int(m.group(1)) if m else 0
        scale = {"scale_kind": "bcd", "formula": "bcd"}
    elif "BOOL" in up and "1BIT" in up:
        raw_type = "bool"
        byte_len = 1
        scale = {"scale_kind": "boolean",
                 "formula": "x == 0" if "INVERT" in up else "x != 0"}
    elif re.search(r"(^|_)BIT[_\s]*(JA|YES|TRUE|NEIN|NO|FALSE|AKTIV|ACTIVE)(?:_|$)", up):
        raw_type = "bool"
        byte_len = 1
        scale = {"scale_kind": "boolean", "formula": "x != 0"}
    elif re.search(r"(^|_)(?:1\s*BIT|BIT_?1|UNSIGNED_?1BIT|.*_1BIT)(?:_|$)", up):
        raw_type = "bool"
        byte_len = 1
        scale = {"scale_kind": "boolean", "formula": "x != 0"}
    elif re.search(
        r"(NEIN[_\s]*JA|JA[_\s]*NEIN|YES[_\s]*NO|NO[_\s]*YES|"
        r"FALSE[_\s]*TRUE|TRUE[_\s]*FALSE|INAKTIV[_\s]*AKTIV|"
        r"AUS[_\s]*EIN|OFF[_\s]*ON|NULL[_\s]*EINS)",
        up,
    ):
        raw_type = "ubyte"
        byte_len = 1
        scale = {"scale_kind": "enum", "formula": ""}
    elif re.search(r"(^|_)BCD(?:_|$)", up):
        raw_type = "bcd"
        m = re.search(r"(^|_)BCD[_\s]*(\d+)(?:_|$)", up)
        if m:
            byte_len = (int(m.group(2)) + 1) // 2
        scale = {"scale_kind": "bcd", "formula": "bcd"}
    elif re.search(r"IDENTICAL_UINT_(?:DEC|HEX)_(\d+)_BYTES?", up):
        byte_len = int(re.search(r"IDENTICAL_UINT_(?:DEC|HEX)_(\d+)_BYTES?", up).group(1))
        raw_type = {1: "ubyte", 2: "uword", 4: "ulong", 8: "bytes"}.get(byte_len, "bytes")
    elif re.search(r"IDENTICAL_INT_(?:DEC|HEX)_(\d+)_BYTES?", up):
        byte_len = int(re.search(r"IDENTICAL_INT_(?:DEC|HEX)_(\d+)_BYTES?", up).group(1))
        raw_type = {1: "sbyte", 2: "sword", 4: "slong", 8: "bytes"}.get(byte_len, "bytes")
    elif re.search(r"(^|_)BLK\d*S?(?:_|$)", up):
        raw_type = "block"
        scale = {"scale_kind": "block", "formula": ""}
    elif "ASCII" in up:
        m = re.search(r"(\d+)\s*BYTE\s*ASCII", up)
        raw_type = "ascii"
        byte_len = int(m.group(1)) if m else 0
    else:
        for token, (found_type, found_len) in PRESENTATION_TYPES.items():
            if re.search(rf"(^|_){token}($|_)", up):
                raw_type = found_type
                byte_len = found_len
                break
        m = re.search(r"(^|_)(\d+)\s*BYTE($|_)", up)
        if m:
            raw_type = "bytes"
            byte_len = int(m.group(2))
        m = re.search(r"UNSIGNED[_\s]*(\d+)BIT", up)
        if not raw_type and m:
            bit_len = int(m.group(1))
            raw_type = "ubyte" if bit_len <= 8 else "uword" if bit_len <= 16 else "ulong"
            byte_len = max(1, (bit_len + 7) // 8)
            scale = {"scale_kind": "bitfield", "formula": ""}
        m = re.search(r"SESSION[_\s]*TYPE[_\s]*(\d+)BIT", up)
        if not raw_type and m:
            bit_len = int(m.group(1))
            raw_type = "ubyte" if bit_len <= 8 else "uword"
            byte_len = max(1, (bit_len + 7) // 8)
            scale = {"scale_kind": "enum", "formula": ""}
    if not byte_len and tokens and tokens[-1].isdigit():
        # Many CM presentations end with the payload byte count:
        # PRES_CM_0001_DEC0_As_2.
        byte_len = int(tokens[-1])
    if not scale["scale_kind"]:
        scale = _presentation_scale(tokens)
    if not raw_type and byte_len in (1, 2, 4) and scale["scale_kind"] in {"binary", "decimal"}:
        raw_type = {1: "ubyte", 2: "uword", 4: "ulong"}[byte_len]
    return {"raw_type": raw_type, "byte_len": byte_len,
            "unit": _presentation_unit(tokens), **scale}


def presentation_raw_type(name: str) -> dict:
    meta = presentation_meta(name)
    return {"raw_type": meta["raw_type"], "byte_len": meta["byte_len"]}


def presentation_records(path: Path) -> dict[str, dict]:
    """Extract simple OutputPresentation records stored outside DiagService.

    Caesar has richer presentation objects. This recognizes common conversion
    and enum records found near the string-pool `PRES_*` qualifiers:

    - `<PRES...NUL><u32 kind=4><u16 method=0x30><float factor><float offset>`
    - `<PRES...NUL><u32 kind=4><u16 method=0x33><i32 low><i32 high>
       <float factor><float offset>`
    - compact enum records where `kind / 4` gives the value count and
      `method == kind + 0x0E`

    Unknown records are ignored and handled by presentation_meta(name).
    """
    r = Reader(path.read_bytes())
    return _presentation_records(r)


def _presentation_records(r: Reader) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for m in PRESENTATION_RE.finditer(r.d):
        name = m.group(0)[:-1].decode("latin-1", "replace")
        pos = m.end()
        if pos + 14 > len(r.d):
            continue
        kind = struct.unpack_from("<I", r.d, pos)[0]
        method = struct.unpack_from("<H", r.d, pos + 4)[0]
        low = high = None
        source = "cbf_presentation_record"
        if kind == 4 and method == 0x30:
            factor, offset = struct.unpack_from("<ff", r.d, pos + 6)
        elif kind == 4 and method == 0x33 and pos + 22 <= len(r.d):
            low, high = struct.unpack_from("<ii", r.d, pos + 6)
            factor, offset = struct.unpack_from("<ff", r.d, pos + 14)
            source = "cbf_presentation_range_record"
            if low >= high:
                continue
        else:
            enum_meta = _presentation_enum_meta(r.d, pos, kind, method)
            if not enum_meta:
                continue
            meta = presentation_meta(name)
            for key in ("raw_type", "byte_len"):
                if enum_meta.get(key) not in ("", 0, None):
                    meta[key] = enum_meta[key]
            meta["scale_kind"] = enum_meta["scale_kind"]
            meta["formula"] = enum_meta["formula"]
            meta["source"] = enum_meta["source"]
            out.setdefault(name, meta)
            continue
        if not all(math.isfinite(v) and abs(v) < 1e9 for v in (factor, offset)):
            continue
        formula = _linear_formula(factor, offset)
        if not formula:
            continue
        meta = presentation_meta(name)
        if low is not None and not meta.get("raw_type"):
            raw_type, byte_len = _raw_type_from_range(low, high or 0)
            meta["raw_type"] = raw_type
            meta["byte_len"] = byte_len
        meta.update({"scale_kind": "linear", "formula": formula,
                     "source": source})
        out.setdefault(name, meta)
    return out


# --- ECU header: reach the VcDomain pool ------------------------------------
def _ecu_vc_pool(r: Reader, base: int, data_buffer: int) -> dict:
    r.seek(base)
    bf = Bitflags(r.u32())
    ext = r.u16()
    r.i32()                                  # ecuHdrIdk1
    # field spec: (size or 'str', adds_data_buffer)
    spec = [
        ("str", 0), (4, 0), (4, 0), ("str", 0), (4, 0), (4, 0), (4, 0), (4, 0),
        ("str", 0), ("str", 0), ("str", 0), (2, 0), (2, 0), (2, 0), (4, 0),
        (2, 0), (4, 0),
        (4, 1), (4, 0), (4, 0), (4, 0),       # 18-21 variant
        (4, 1), (4, 0), (4, 0), (4, 0),       # 22-25 diagjob
        (4, 1), (4, 0), (4, 0), (4, 0),       # 26-29 dtc
        (4, 1), (4, 0), (4, 0),               # 30-32 env (offset,count,size)
    ]
    vals = []
    for kind, db in spec:
        if kind == "str":
            rf_str(r, bf, base); vals.append(None)
        else:
            v = rf_int(r, bf, kind)
            vals.append((v + data_buffer) if db else v)
    # vals indices (0-based for fields 1..32): field22 DiagJob_BlockOffset=vals[21]
    dj_block = vals[21]                       # already + data_buffer
    dj_count = vals[22]
    dj_size = vals[23]
    # switch to extended bitflags
    bf = Bitflags(ext)
    rf_int(r, bf, 4)                          # 33 Env_BlockSize
    vc_block = rf_int(r, bf, 4) + data_buffer  # 34 VcDomain_BlockOffset
    vc_count = rf_int(r, bf, 4)              # 35 VcDomain_EntryCount
    vc_size = rf_int(r, bf, 4)              # 36 VcDomain_EntrySize
    return {"vc_block": vc_block, "vc_count": vc_count, "vc_size": vc_size,
            "dj_block": dj_block, "dj_count": dj_count, "dj_size": dj_size}


# --- DiagService: extract request bytes (SID + local id) --------------------
def _parse_diag_header(r: Reader, base: int) -> dict:
    r.seek(base)
    bf = Bitflags(r.u32())
    r.u32()                                   # extended bitflags (unused here)
    qualifier = rf_str(r, bf, base)
    name_ctf = rf_int(r, bf, 4, -1)           # Name_CTF
    desc_ctf = rf_int(r, bf, 4, -1)           # Description_CTF
    svc_type = rf_int(r, bf, 2)              # DataClass_ServiceType
    rf_int(r, bf, 2)                          # IsExecutable
    rf_int(r, bf, 2)                          # ClientAccessLevel
    sec_level = rf_int(r, bf, 2)             # SecurityAccessLevel
    rf_int(r, bf, 4); rf_int(r, bf, 4)        # T comparam count/offset
    rf_int(r, bf, 4); rf_int(r, bf, 4)        # Q
    rf_int(r, bf, 4); rf_int(r, bf, 4)        # R
    rf_str(r, bf, base)                       # InputRefNameMaybe
    rf_int(r, bf, 4); rf_int(r, bf, 4)        # U prep
    rf_int(r, bf, 4); rf_int(r, bf, 4)        # V
    req_count = rf_int(r, bf, 2)            # RequestBytes_Count (int16, per CaesarSuite)
    req_off = rf_int(r, bf, 4)             # RequestBytes_Offset
    req = b""
    # Validate against the file: a diagnostic request is short and stored right
    # after the header. Implausible count/offset means this entry's bitflags
    # drifted — discard the garbage rather than emit a bogus request.
    flen = len(r.data) if hasattr(r, "data") else (1 << 30)
    if 0 < req_count <= 0x20 and 0 <= req_off and (base + req_off + req_count) <= flen:
        try:
            r.seek(base + req_off)
            req = r.bytes(req_count)
        except Exception:  # noqa: BLE001
            req = b""
    return {"qualifier": qualifier, "request": req, "sec_level": sec_level,
            "svc_type": svc_type, "name_ctf": name_ctf, "desc_ctf": desc_ctf}


def _presentation_near(r: Reader, base: int, end: int,
                       records: dict[str, dict] | None = None) -> dict:
    """Find the first inline PRES_* qualifier inside a DiagService block."""
    limit = min(max(base, end), base + 1024, len(r.d))
    chunk = r.d[base:limit]
    m = PRESENTATION_RE.search(chunk)
    if not m:
        return {"presentation": "", "presentation_raw_type": "", "presentation_byte_len": 0}
    name = m.group(0)[:-1].decode("latin-1", "replace")
    meta = presentation_meta(name)
    source = "presentation_name" if (meta.get("unit") or meta.get("formula")) else ""
    if records and name in records:
        rec = records[name]
        for key in ("raw_type", "byte_len", "unit"):
            if rec.get(key) not in ("", 0, None):
                meta[key] = rec[key]
        if rec.get("scale_kind"):
            meta["scale_kind"] = rec["scale_kind"]
        if rec.get("formula") or rec.get("source") == "cbf_presentation_enum_record":
            meta["formula"] = rec.get("formula") or ""
        source = rec.get("source") or source
    return {"presentation": name,
            "presentation_raw_type": meta["raw_type"],
            "presentation_byte_len": meta["byte_len"],
            "presentation_unit": meta["unit"],
            "presentation_scale_kind": meta["scale_kind"],
            "presentation_formula": meta["formula"],
            "presentation_meta_source": source}


def diag_catalog(path: Path) -> dict:
    """Map diag-service qualifier -> {description, name, request, sec_level}.

    Descriptions/names are resolved through the CTF string table - this is the
    human 'what/why' for each job (used to annotate measurement parameters).
    """
    r = Reader(path.read_bytes())
    cff = parse_cff(r)
    strings = load_ctf_strings(r, cff)
    records = _presentation_records(r)
    data_buffer = cff["StringPoolSize"] + STUB_HEADER_SIZE + cff["CffHeaderSize"] + 4
    ecu_table = cff["EcuOffset"] + cff["BaseAddress"]
    out = {}
    for i in range(cff["EcuCount"]):
        r.seek(ecu_table + i * 4)
        ecu_base = ecu_table + r.i32()
        pool = _ecu_vc_pool(r, ecu_base, data_buffer)
        entries = []
        for j in range(pool.get("dj_count") or 0):
            r.seek(pool["dj_block"] + j * pool["dj_size"])
            entries.append(r.i32() + pool["dj_block"])
        entries.sort()
        for j, base in enumerate(entries):
            try:
                h = _parse_diag_header(r, base)
            except Exception:  # noqa: BLE001
                continue
            q = h.get("qualifier")
            if not q:
                continue
            end = entries[j + 1] if j + 1 < len(entries) else min(len(r.d), base + 1024)
            pres = _presentation_near(r, base, end, records)
            desc = ctf(strings, h["desc_ctf"]) or ctf(strings, h["name_ctf"])
            out[q] = {"description": desc,
                      "name": ctf(strings, h["name_ctf"]),
                      "request": h["request"].hex().upper(),
                      "sec_level": h["sec_level"],
                      "svc_type": h["svc_type"],
                      **pres}
    return out


def build_diag_requests(r: Reader, dj_block: int, dj_count: int,
                        dj_size: int) -> dict:
    """Map diag-service qualifier -> {request bytes, security level}."""
    out = {}
    for i in range(dj_count or 0):
        r.seek(dj_block + i * dj_size)
        entry_off = r.i32()
        base = entry_off + dj_block
        try:
            h = _parse_diag_header(r, base)
        except Exception:  # noqa: BLE001
            continue
        if h["qualifier"]:
            out[h["qualifier"]] = {"request": h["request"],
                                   "sec_level": h["sec_level"],
                                   "svc_type": h["svc_type"]}
    return out


def request_to_identifier(req: bytes) -> dict:
    """Derive the read/write identifier from a service's request bytes."""
    if not req:
        return {}
    sid = req[0]
    if sid in (0x21, 0x3B) and len(req) >= 2:          # KWP RDBLI / WDBLI
        return {"sid": sid, "lid": req[1], "lid_hex": f"{req[1]:02X}"}
    if sid in (0x22, 0x2E) and len(req) >= 3:          # UDS RDBI / WDBI
        did = (req[1] << 8) | req[2]
        return {"sid": sid, "lid": did, "lid_hex": f"{did:04X}"}
    return {"sid": sid, "request_hex": req.hex().upper()}


# --- VC domain / fragment / subfragment -------------------------------------
def _parse_subfragment(r: Reader, base: int, dump_size: int, strings: list) -> dict:
    r.seek(base)
    bf = Bitflags(r.u16())
    name_ctf = rf_int(r, bf, 4, -1)
    dump = rf_dump(r, bf, dump_size, base)
    desc_ctf = rf_int(r, bf, 4, -1)
    rf_str(r, bf, base)                       # QualifierUsuallyDisabled
    rf_int(r, bf, 4, -1)
    rf_int(r, bf, 2, -1)
    rf_str(r, bf, base)                       # SupplementKey
    label = ctf(strings, desc_ctf) or ctf(strings, name_ctf)
    return {"label": label, "dump": dump}


def _frag_bitlength(impl_type: int, raw_bitlen: int) -> tuple[int, bool]:
    upper = impl_type & 0xFF0
    lower = impl_type & 0xF
    if upper > 0x420:
        return (raw_bitlen, True)             # presentation-based, approximate
    if upper in (0x420, 0x320):
        return (FRAG_LEN_TABLE[lower] if lower < len(FRAG_LEN_TABLE) else 0, False)
    if upper == 0x330:
        return (raw_bitlen, False)
    return (raw_bitlen, True)                  # 0x340 ITT / unknown


def _parse_fragment(r: Reader, frag_table: int, index: int,
                    strings: list) -> dict:
    r.seek(frag_table + 10 * index)
    new_base_off = r.i32()
    byte_bit_pos = r.i32()
    impl_type = r.u16()
    fbase = frag_table + new_base_off
    r.seek(fbase)
    bf = Bitflags(r.u32())
    name_ctf = rf_int(r, bf, 4, -1)
    rf_int(r, bf, 4, -1)                      # DescriptionCTF
    rf_int(r, bf, 1)                          # ReadAccessLevel
    write_level = rf_int(r, bf, 1)           # WriteAccessLevel
    rf_int(r, bf, 2)                          # ByteOrder
    raw_bitlen = rf_int(r, bf, 4)
    rf_int(r, bf, 4)                          # IttOffset
    rf_int(r, bf, 4, -1)                      # InfoPoolIndex
    rf_int(r, bf, 4, -1)                      # MeaningB
    rf_int(r, bf, 4, -1)                      # MeaningC
    rf_int(r, bf, 2, -1)                      # CCFHandle
    dump_size = rf_int(r, bf, 4)
    rf_dump(r, bf, dump_size, fbase)          # VarcodeDump
    sub_count = rf_int(r, bf, 4)
    sub_off = rf_int(r, bf, 4)
    qualifier = rf_str(r, bf, fbase)

    bitlen, approx = _frag_bitlength(impl_type, raw_bitlen)
    subs = []
    sub_table = sub_off + fbase
    for i in range(sub_count or 0):
        r.seek(sub_table + i * 4)
        saddr = r.i32() + sub_table
        subs.append(_parse_subfragment(r, saddr, dump_size, strings))
    return {
        "name": ctf(strings, name_ctf) or qualifier or "",
        "qualifier": qualifier,
        "byte_bit_pos": byte_bit_pos,
        "bit_length": bitlen,
        "bitlen_approx": approx,
        "write_level": write_level,
        "options": subs,
    }


def _parse_domain(r: Reader, base: int, strings: list) -> dict:
    r.seek(base)
    bf = Bitflags(r.u16())
    qualifier = rf_str(r, bf, base)
    name_ctf = rf_int(r, bf, 4, -1)
    rf_int(r, bf, 4, -1)                      # DescriptionCTF
    read_svc = rf_str(r, bf, base)
    write_svc = rf_str(r, bf, base)
    frag_count = rf_int(r, bf, 4)
    frag_table = rf_int(r, bf, 4) + base
    dump_size = rf_int(r, bf, 4)
    frags = [_parse_fragment(r, frag_table, i, strings)
             for i in range(frag_count or 0)]
    return {
        "domain": qualifier or ctf(strings, name_ctf),
        "name": ctf(strings, name_ctf),
        "read_service": read_svc,
        "write_service": write_svc,
        "dump_size": dump_size,
        "fragments": frags,
    }


def parse_vc(path: Path) -> dict:
    r = Reader(path.read_bytes())
    cff = parse_cff(r)
    strings = load_ctf_strings(r, cff)
    data_buffer = cff["StringPoolSize"] + STUB_HEADER_SIZE + cff["CffHeaderSize"] + 4
    ecu_table = cff["EcuOffset"] + cff["BaseAddress"]
    out = {"file": path.name, "domains": []}
    for i in range(cff["EcuCount"]):
        r.seek(ecu_table + i * 4)
        ecu_base = ecu_table + r.i32()
        pool = _ecu_vc_pool(r, ecu_base, data_buffer)
        if not pool["vc_count"]:
            continue
        diag = build_diag_requests(r, pool["dj_block"], pool["dj_count"],
                                   pool["dj_size"])
        block = pool["vc_block"]
        for vi in range(pool["vc_count"]):
            r.seek(block + vi * pool["vc_size"])
            entry_off = r.i32()
            r.i32(); r.u32()                  # size, crc
            try:
                d = _parse_domain(r, entry_off + block, strings)
                _attach_service(d, "read", diag)
                _attach_service(d, "write", diag)
                out["domains"].append(d)
            except Exception as e:  # noqa: BLE001
                out["domains"].append({"error": str(e), "index": vi})
    return out


def _attach_service(domain: dict, which: str, diag: dict):
    name = domain.get(f"{which}_service")
    info = diag.get(name) if name else None
    if not info:
        return
    ident = request_to_identifier(info["request"])
    domain[f"{which}_request"] = info["request"].hex().upper()
    domain[f"{which}_lid"] = ident.get("lid_hex")
    domain[f"{which}_sid"] = ident.get("sid")
    domain[f"{which}_sec_level"] = info.get("sec_level")


# --- coding string decode / encode ------------------------------------------
def _bits(data: bytes) -> list[int]:
    """LSB-first per byte (BitUtility little-endian)."""
    out = []
    for b in data:
        for i in range(8):
            out.append((b >> i) & 1)
    return out


def _frombits(bits: list[int]) -> bytes:
    out = bytearray(len(bits) // 8)
    for i, bit in enumerate(bits):
        if bit:
            out[i // 8] |= (1 << (i % 8))
    return bytes(out)


def decode_fragment(frag: dict, coding: bytes) -> dict:
    bits = _bits(coding)
    pos, ln = frag["byte_bit_pos"], frag["bit_length"]
    if ln <= 0 or pos + ln > len(bits):
        return {**_frag_view(frag), "value": None, "current": None}
    affected = bits[pos:pos + ln]
    value = sum(b << i for i, b in enumerate(affected))
    current = None
    for opt in frag["options"]:
        ob = _bits(opt["dump"])[:ln]
        if ob == affected:
            current = opt["label"]
            break
    return {**_frag_view(frag), "value": value, "current": current}


def _frag_view(frag: dict) -> dict:
    return {"name": frag["name"], "byte_bit_pos": frag["byte_bit_pos"],
            "bit_length": frag["bit_length"], "approx": frag["bitlen_approx"],
            "options": [o["label"] for o in frag["options"]]}


def set_option(frag: dict, coding: bytes, option_label: str) -> bytes:
    target = next((o for o in frag["options"] if o["label"] == option_label), None)
    if target is None:
        raise ValueError(f"option '{option_label}' not in fragment '{frag['name']}'")
    bits = _bits(coding)
    pos, ln = frag["byte_bit_pos"], frag["bit_length"]
    ob = _bits(target["dump"])[:ln]
    bits[pos:pos + ln] = ob
    return _frombits(bits)


def main(argv):
    path = Path(argv[1])
    res = parse_vc(path)
    if "--coding" in argv:
        coding = bytes.fromhex(argv[argv.index("--coding") + 1])
        for d in res["domains"]:
            if "error" in d:
                continue
            print(f"\n=== {d['domain']} (dump {d['dump_size']}B, "
                  f"read {d['read_service']}, write {d['write_service']}) ===")
            for f in d["fragments"]:
                dec = decode_fragment(f, coding)
                print(f"  [{dec['byte_bit_pos']:>4}+{dec['bit_length']:<2}] "
                      f"{dec['name']}: {dec['current'] or dec['value']}")
    else:
        print(json.dumps(res, ensure_ascii=False, indent=2)[:4000])


if __name__ == "__main__":
    main(sys.argv)
