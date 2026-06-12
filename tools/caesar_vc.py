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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from caesar_comparam import Reader, Bitflags, parse_cff, STUB_HEADER_SIZE  # noqa


FRAG_LEN_TABLE = [0, 1, 4, 8, 0x10, 0x20, 0x40]


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


def diag_catalog(path: Path) -> dict:
    """Map diag-service qualifier -> {description, name, request, sec_level}.

    Descriptions/names are resolved through the CTF string table - this is the
    human 'what/why' for each job (used to annotate measurement parameters).
    """
    r = Reader(path.read_bytes())
    cff = parse_cff(r)
    strings = load_ctf_strings(r, cff)
    data_buffer = cff["StringPoolSize"] + STUB_HEADER_SIZE + cff["CffHeaderSize"] + 4
    ecu_table = cff["EcuOffset"] + cff["BaseAddress"]
    out = {}
    for i in range(cff["EcuCount"]):
        r.seek(ecu_table + i * 4)
        ecu_base = ecu_table + r.i32()
        pool = _ecu_vc_pool(r, ecu_base, data_buffer)
        for j in range(pool.get("dj_count") or 0):
            r.seek(pool["dj_block"] + j * pool["dj_size"])
            entry_off = r.i32()
            try:
                h = _parse_diag_header(r, entry_off + pool["dj_block"])
            except Exception:  # noqa: BLE001
                continue
            q = h.get("qualifier")
            if not q:
                continue
            desc = ctf(strings, h["desc_ctf"]) or ctf(strings, h["name_ctf"])
            out[q] = {"description": desc,
                      "name": ctf(strings, h["name_ctf"]),
                      "request": h["request"].hex().upper(),
                      "sec_level": h["sec_level"]}
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
