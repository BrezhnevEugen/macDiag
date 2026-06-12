#!/usr/bin/env python3
"""
Focused Caesar/CBF parser that extracts COMPARAM values - in particular the real
CAN request/response identifiers - from Mercedes CBF files.

This is a partial reimplementation of jglim/CaesarSuite (MIT), porting only the
path needed to reach comparams:

    CaesarContainer -> CFFHeader -> ECU -> ECUInterface (comparam names)
                                        -> ECUVariant   -> ComParameter (values)

Caesar uses "bitflag" reads: a block begins with a bitfield; each subsequent
field is present in the stream only if its bit (LSB-first) is set, otherwise it
takes a default and consumes nothing. See CaesarReader.cs.

CAN id comparams of interest:
    CP_REQUEST_CANIDENTIFIER          tester -> ECU request id
    CP_RESPONSE_CANIDENTIFIER         ECU -> tester response id
    CP_GLOBAL_REQUEST_CANIDENTIFIER   functional/broadcast request id
    CP_BAUDRATE                       bus speed

Usage:
    python tools/caesar_comparam.py FILE.cbf [FILE2.cbf ...]
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

STUB_HEADER_SIZE = 0x410


class Reader:
    """Minimal seekable binary reader over an in-memory buffer."""

    def __init__(self, data: bytes):
        self.d = data
        self.pos = 0

    def seek(self, p: int):
        self.pos = p

    def tell(self) -> int:
        return self.pos

    def u16(self) -> int:
        v = struct.unpack_from("<H", self.d, self.pos)[0]; self.pos += 2; return v

    def i16(self) -> int:
        v = struct.unpack_from("<h", self.d, self.pos)[0]; self.pos += 2; return v

    def u32(self) -> int:
        v = struct.unpack_from("<I", self.d, self.pos)[0]; self.pos += 4; return v

    def i32(self) -> int:
        v = struct.unpack_from("<i", self.d, self.pos)[0]; self.pos += 4; return v

    def i8(self) -> int:
        v = self.d[self.pos]; self.pos += 1; return v

    def bytes(self, n: int) -> bytes:
        v = self.d[self.pos:self.pos + n]; self.pos += n; return v

    def cstr(self, at: int) -> str:
        end = self.d.index(b"\x00", at)
        # Caesar string pool is UTF-8 (CaesarReader.DefaultEncoding)
        return self.d[at:end].decode("utf-8", "replace")


class Bitflags:
    """LSB-first bitflag cursor mirroring CaesarReader.CheckAndAdvanceBitflag."""

    def __init__(self, value: int):
        self.v = value

    def next(self) -> bool:
        bit = (self.v & 1) == 1
        self.v >>= 1
        return bit


def read_field(r: Reader, bf: Bitflags, kind: str, default=0):
    """Read one bitflag field. kind in {'str','i32','i16','i8'}. For 'str' we
    only consume the 4-byte offset (we don't resolve the text here)."""
    if not bf.next():
        return default
    if kind == "str":
        r.i32()          # string offset - skip resolution
        return None
    if kind == "i32":
        return r.i32()
    if kind == "i16":
        return r.i16()
    if kind == "i8":
        return r.i8()
    raise ValueError(kind)


# --- CFF header -------------------------------------------------------------
def parse_cff(r: Reader) -> dict:
    r.seek(STUB_HEADER_SIZE)
    cff_size = r.i32()
    base = r.tell()                      # BaseAddress
    bf = Bitflags(r.u16())
    h = {"CffHeaderSize": cff_size, "BaseAddress": base}
    h["CaesarVersion"] = read_field(r, bf, "i32")
    h["GpdVersion"] = read_field(r, bf, "i32")
    h["EcuCount"] = read_field(r, bf, "i32")
    h["EcuOffset"] = read_field(r, bf, "i32")
    h["CtfOffset"] = read_field(r, bf, "i32")
    h["StringPoolSize"] = read_field(r, bf, "i32")
    return h


# --- ECU --------------------------------------------------------------------
def parse_ecu(r: Reader, base: int, data_buffer: int) -> dict:
    r.seek(base)
    bf = Bitflags(r.u32())               # 32-bit primary bitflags
    r.u16()                              # extended bitflags (unused here)
    r.i32()                              # ecuHdrIdk1

    e: dict = {"base": base}
    read_field(r, bf, "str")                                  # 1 Qualifier
    read_field(r, bf, "i32", -1)                              # 2 EcuName_CTF
    read_field(r, bf, "i32", -1)                              # 3 EcuDescription_CTF
    read_field(r, bf, "str")                                  # 4 EcuXmlVersion
    e["InterfaceBlockCount"] = read_field(r, bf, "i32")       # 5
    e["InterfaceTableOffset"] = read_field(r, bf, "i32")      # 6
    read_field(r, bf, "i32")                                  # 7 SubinterfacesCount
    read_field(r, bf, "i32")                                  # 8 SubinterfacesOffset
    read_field(r, bf, "str")                                  # 9 EcuClassName
    read_field(r, bf, "str")                                  # 10 UnkStr7
    read_field(r, bf, "str")                                  # 11 UnkStr8
    read_field(r, bf, "i16")                                  # 12 IgnitionRequired
    read_field(r, bf, "i16")                                  # 13 Unk2
    read_field(r, bf, "i16")                                  # 14 UnkBlockCount
    read_field(r, bf, "i32")                                  # 15 UnkBlockOffset
    read_field(r, bf, "i16")                                  # 16 EcuSgmlSource
    read_field(r, bf, "i32")                                  # 17 Unk6RelativeOffset
    vbo = read_field(r, bf, "i32")                            # 18 EcuVariant_BlockOffset
    e["Variant_EntryCount"] = read_field(r, bf, "i32")        # 19
    e["Variant_EntrySize"] = read_field(r, bf, "i32")         # 20
    e["Variant_BlockOffset"] = (vbo or 0) + data_buffer
    return e


def parse_interfaces(r: Reader, ecu_base: int, iface_table_off: int,
                     count: int) -> list[list[str]]:
    table = ecu_base + iface_table_off
    interfaces = []
    for i in range(count):
        r.seek(table + i * 4)
        iface_base = table + r.i32()
        r.seek(iface_base)
        bf = Bitflags(r.u32())
        read_field(r, bf, "str")                       # Qualifier
        read_field(r, bf, "i32", -1)                   # Name_CTF
        read_field(r, bf, "i32", -1)                   # Description_CTF
        read_field(r, bf, "str")                       # VersionString
        read_field(r, bf, "i32")                       # Version
        cp_count = read_field(r, bf, "i32")            # ComParamCount
        cp_list_off = read_field(r, bf, "i32")         # ComParamListOffset
        read_field(r, bf, "i16")                       # Unk6

        names = []
        cp_file_off = (cp_list_off or 0) + iface_base
        for j in range(cp_count or 0):
            r.seek(cp_file_off + j * 4)
            ptr = r.i32() + cp_file_off
            names.append(r.cstr(ptr))
        interfaces.append(names)
    return interfaces


def parse_variant_comparam_loc(r: Reader, variant_base: int,
                               block_size: int) -> tuple[int, int]:
    """Return (ComParamsCount, ComParamsOffset) for a variant."""
    block = r.d[variant_base:variant_base + block_size]
    lr = Reader(block)
    bf = Bitflags(lr.u32())
    lr.i32()                                           # skip
    read_field(lr, bf, "str")                          # 1 Qualifier
    read_field(lr, bf, "i32", -1)                      # 2 Name_CTF
    read_field(lr, bf, "i32", -1)                      # 3 Description_CTF
    read_field(lr, bf, "str")                          # 4 UnkStr1
    read_field(lr, bf, "str")                          # 5 UnkStr2
    read_field(lr, bf, "i32")                          # 6 Unk1
    read_field(lr, bf, "i32")                          # 7 MatchingPatternCount
    read_field(lr, bf, "i32")                          # 8 MatchingPatternOffset
    read_field(lr, bf, "i32")                          # 9 SubsectionB_Count
    read_field(lr, bf, "i32")                          # 10 SubsectionB_Offset
    count = read_field(lr, bf, "i32")                  # 11 ComParamsCount
    offset = read_field(lr, bf, "i32")                 # 12 ComParamsOffset
    return (count or 0), (offset or 0)


def parse_comparam(r: Reader, base: int, interfaces: list[list[str]]) -> dict:
    r.seek(base)
    bf = Bitflags(r.u16())
    cp_index = read_field(r, bf, "i16")                # ComParamIndex
    parent_iface = read_field(r, bf, "i16")            # ParentInterfaceIndex
    read_field(r, bf, "i16", 0)                        # SubinterfaceIndex
    read_field(r, bf, "i16")                           # Unk5
    read_field(r, bf, "i32")                           # Unk_CTF
    read_field(r, bf, "i16")                           # Phrase
    dump_size = read_field(r, bf, "i32") or 0          # DumpSize
    dump = b""
    if bf.next():                                      # Dump (bitflag)
        off = r.i32()
        cur = r.tell()
        r.seek(base + off)
        dump = r.bytes(dump_size)
        r.seek(cur)
    value = None
    if dump_size == 4:
        value = struct.unpack("<I", dump)[0]
    name = None
    pi = parent_iface if parent_iface is not None else -1
    if 0 <= pi < len(interfaces) and cp_index is not None \
            and 0 <= cp_index < len(interfaces[pi]):
        name = interfaces[pi][cp_index]
    return {"name": name, "value": value, "dump": dump.hex().upper(),
            "iface": pi, "index": cp_index}


def parse_file(path: Path) -> dict:
    r = Reader(path.read_bytes())
    cff = parse_cff(r)
    data_buffer = cff["StringPoolSize"] + STUB_HEADER_SIZE + cff["CffHeaderSize"] + 4
    ecu_table = cff["EcuOffset"] + cff["BaseAddress"]

    out = {"file": path.name, "ecus": []}
    for i in range(cff["EcuCount"]):
        r.seek(ecu_table + i * 4)
        ecu_base = ecu_table + r.i32()
        e = parse_ecu(r, ecu_base, data_buffer)
        interfaces = parse_interfaces(r, ecu_base, e["InterfaceTableOffset"],
                                      e["InterfaceBlockCount"])
        comparams = []
        for vi in range(e["Variant_EntryCount"]):
            r.seek(e["Variant_BlockOffset"] + vi * e["Variant_EntrySize"])
            entry_off = r.i32()
            entry_size = r.i32()
            r.u16()
            vbase = entry_off + e["Variant_BlockOffset"]
            cp_count, cp_off = parse_variant_comparam_loc(r, vbase, entry_size)
            if cp_count == 0:
                continue
            cp_base = vbase + cp_off
            r.seek(cp_base)
            offs = [r.i32() + cp_base for _ in range(cp_count)]
            for o in offs:
                cp = parse_comparam(r, o, interfaces)
                if cp["name"]:
                    comparams.append(cp)
            break   # comparams live on the base variant only
        # collect the interesting CAN ids
        wanted = ("CP_REQUEST_CANIDENTIFIER", "CP_RESPONSE_CANIDENTIFIER",
                  "CP_GLOBAL_REQUEST_CANIDENTIFIER", "CP_BAUDRATE",
                  "CP_CANPHYS_REQUEST_CANIDENTIFIER",
                  "CP_CANFUNC_REQUEST_CANIDENTIFIER")
        can = {c["name"]: c["value"] for c in comparams if c["name"] in wanted}
        out["ecus"].append({
            "interfaces": interfaces,
            "can": can,
            "comparams": {c["name"]: c["value"] for c in comparams},
        })
    return out


def main(argv):
    for a in argv[1:]:
        res = parse_file(Path(a))
        print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv)
