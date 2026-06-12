"""
Real Security-Access (0x27) seed -> key generation.

Ported from jglim/UnlockECU (MIT) - the security functions are reverse-engineered
and reimplemented, with NO proprietary binary blobs. Each ECU's algorithm and
constants live in `unlock_db.json` (the UnlockECU `db.json`), mapping:

    EcuName -> { AccessLevel, SeedLength, KeyLength, Provider, Parameters[] }

We port the most common Mercedes "security providers" here and look up the per-
ECU definition + constants from that database. Providers not yet ported return
None (the caller then reports that the algorithm is unavailable rather than
sending a wrong key).

Get the database (MIT, ~1.4MB):
    curl -L -o backend/mb/unlock_db.json \
      https://raw.githubusercontent.com/jglim/UnlockECU/main/UnlockECU/db.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# env-overridable so it can live in a mounted data volume (Docker)
_DEF_UNLOCK = Path(__file__).resolve().parent.parent.parent / "data" / "unlock_db.json"
if not _DEF_UNLOCK.exists():
    _DEF_UNLOCK = Path(__file__).with_name("unlock_db.json")
DB_PATH = Path(os.environ.get("MACDIAG_UNLOCK_DB", str(_DEF_UNLOCK)))

U32 = 0xFFFFFFFF


def _be(b: bytes, off: int = 0, n: int = 4) -> int:
    v = 0
    for i in range(n):
        v = (v << 8) | b[off + i]
    return v


def _hex(s: str) -> bytes:
    return bytes.fromhex(s)


# --- bit/byte helpers (mirror UnlockECU SecurityProvider) -------------------
def _get_bit(b: int, pos: int) -> int:
    return (b >> pos) & 1


def _get_byte(v: int, pos: int) -> int:
    return (v >> (8 * pos)) & 0xFF


def _expand_nibbles(data: bytes) -> list[int]:
    out = []
    for b in data:
        out.append((b >> 4) & 0xF)
        out.append(b & 0xF)
    return out


def _collapse_nibbles(nib: list[int]) -> bytes:
    return bytes((nib[i * 2] << 4) | nib[i * 2 + 1] for i in range(len(nib) // 2))


def _rotl32(v: int, n: int) -> int:
    v &= U32; n %= 32
    return ((v << n) | (v >> (32 - n))) & U32 if n else v


def _rotr32(v: int, n: int) -> int:
    v &= U32; n %= 32
    return ((v >> n) | (v << (32 - n))) & U32 if n else v


def _rotl16(v: int, n: int) -> int:
    v &= 0xFFFF; n %= 16
    return ((v << n) | (v >> (16 - n))) & 0xFFFF if n else v


def _count_ones(v: int) -> int:
    return bin(v & U32).count("1")


# ---------------------------------------------------------------------------
# Security providers (ported from UnlockECU/Security/*.cs)
# Each: fn(seed: bytes, level: int, params: dict[str, Parameter]) -> bytes | None
# A Parameter is {"Key","Value","DataType"} where Value is hex.
# ---------------------------------------------------------------------------
def _p_bytes(params: dict, key: str) -> bytes:
    return _hex(params[key]["Value"])


def _p_long(params: dict, key: str) -> int:
    return int(params[key]["Value"], 16)


def _p_byte(params: dict, key: str) -> int:
    return int(params[key]["Value"], 16) & 0xFF


def _p_int(params: dict, key: str) -> int:
    return int(params[key]["Value"], 16)


def daimler_standard(seed, level, params):
    """DaimlerStandardSecurityAlgo - hardcoded kA/kC. 8-byte seed -> 4-byte key."""
    if len(seed) != 8:
        return None
    crypto = _be(_p_bytes(params, "K"))
    kA, kC = 1103515245, 12345
    a = _be(seed, 0, 4)
    b = _be(seed, 4, 4)
    key = ((kA * a + kC) ^ (kA * b + kC) ^ crypto) & U32
    return key.to_bytes(4, "big")


def daimler_standard_mod(seed, level, params):
    """DaimlerStandardSecurityAlgoMod - kA/kC from parameters."""
    if len(seed) != 8:
        return None
    crypto = _be(_p_bytes(params, "K"))
    kA = _p_long(params, "kA")
    kC = _p_long(params, "kC")
    a = _be(seed, 0, 4)
    b = _be(seed, 4, 4)
    key = ((kA * a + kC) ^ (kA * b + kC) ^ crypto) & U32
    return key.to_bytes(4, "big")


def powertrain_boschconti_1(seed, level, params):
    """PowertrainBoschContiSecurityAlgo1 (e.g. ME97/MED97). 2-byte seed/key."""
    if len(seed) != 2:
        return None
    ub = _p_bytes(params, "ubTable")
    mask = _p_bytes(params, "Mask")
    s = seed[1] | (seed[0] << 8)
    m = mask[1] | (mask[0] << 8)
    b1 = (s & m & 0x4000) >> 12
    b2 = (s & m & 0x200) >> 8
    b3 = (s & m & 0x100) >> 8
    key = (ub[b1 | b2 | b3] * s) & 0xFFFFFFFF
    return bytes([(key >> 16) & 0xFF, (key >> 8) & 0xFF])


def xor_algo(seed, level, params):
    """XorAlgo - key = seed XOR constant (same length)."""
    k = _p_bytes(params, "Key") if "Key" in params else _p_bytes(params, "K")
    n = min(len(seed), len(k))
    return bytes(seed[i] ^ k[i] for i in range(n))


def daimler_standard_refg(seed, level, params):
    """DaimlerStandardSecurityAlgoRefG - fixed kA0/kA1/kC0/kC1, key 'K_refG'."""
    if len(seed) != 8:
        return None
    crypto = _be(_p_bytes(params, "K_refG"))
    kA0, kA1, kC0, kC1 = 3040238857, 4126034881, 2094854071, 3555108353
    a = _be(seed, 0, 4)
    b = _be(seed, 4, 4)
    key = ((kA0 * a + kC0) ^ (kA1 * b + kC1) ^ crypto) & U32
    return key.to_bytes(4, "big")


def vgs(seed, level, params):
    """VGSSecurityAlgo (e.g. VGSNAG2). 4-byte seed/key. key=K*(K^seed)."""
    if len(seed) != 4:
        return None
    k = _be(_p_bytes(params, "K"))
    s = _be(seed, 0, 4)
    key = (k * (k ^ s)) & U32
    return key.to_bytes(4, "big")


def vgs_2bytes(seed, level, params):
    """VGSSecurityAlgo2Bytes. 2-byte seed/key (note: seed is little-endian)."""
    if len(seed) != 2:
        return None
    kb = _p_bytes(params, "K")
    k = kb[1] | (kb[0] << 8)
    s = seed[0] | (seed[1] << 8)
    key = (k * (k ^ s)) & 0xFFFFFFFF
    return bytes([(key >> 8) & 0xFF, key & 0xFF])


def vgs_ext(seed, level, params):
    """VGSSecurityAlgoExt. 4-byte. key = M * (X ^ seed)."""
    if len(seed) != 4:
        return None
    m = _be(_p_bytes(params, "M"))
    x = _be(_p_bytes(params, "X"))
    s = _be(seed, 0, 4)
    key = (m * (x ^ s)) & U32
    return key.to_bytes(4, "big")


def esp_level1(seed, level, params):
    """ESPSecurityAlgoLevel1. 2-byte. key = 4*((s>>3)^s)^s."""
    if len(seed) != 2:
        return None
    s = seed[1] | (seed[0] << 8)
    key = (4 * ((s >> 3) ^ s) ^ s) & 0xFFFFFFFF
    return bytes([(key >> 8) & 0xFF, key & 0xFF])


def powertrain_boschconti_2(seed, level, params):
    """PowertrainBoschContiSecurityAlgo2 (MED97/SIM271CNG). 2-byte."""
    if len(seed) != 2:
        return None
    table = _p_bytes(params, "Table")
    uw = _p_bytes(params, "uwMasc")
    s = seed[1] | (seed[0] << 8)
    m = uw[1] | (uw[0] << 8)
    sa, sb, act = 1, 1, 0
    for _ in range(16):
        if sa & m:
            if sa & s:
                act |= sb
            sb *= 2
        sa *= 2
    key = ((table[act] * s) >> 8) & 0xFFFF
    return bytes([(key >> 8) & 0xFF, key & 0xFF])


def ic172_algo1(seed, level, params):
    """IC172Algo1 (IC172 level 7). 8-byte seed/key."""
    if len(seed) != 8:
        return None
    seed_input = _expand_nibbles(bytes([seed[0], seed[2], seed[4], seed[6]]))
    pool = [
        [0xEF, 0xCD, 0xAB, 0x89, 0x67, 0x45, 0x23, 0x01],
        [0x45, 0x67, 0x01, 0x23, 0xCD, 0xEF, 0x89, 0xAB],
        [0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0xCD, 0xEF],
        [0x89, 0xAB, 0xCD, 0xEF, 0x01, 0x23, 0x45, 0x67],
        [0x54, 0x76, 0x10, 0x32, 0xDC, 0xFE, 0x98, 0xBA],
        [0xEF, 0xCD, 0xAB, 0x89, 0x67, 0x45, 0x23, 0x01],
        [0x89, 0xAB, 0xCD, 0xEF, 0x01, 0x23, 0x45, 0x67],
        [0xBA, 0x98, 0xFE, 0xDC, 0x32, 0x10, 0x76, 0x54],
    ]
    transp = [5, 2, 7, 4, 1, 6, 3, 0]
    inter = [0] * 8
    for i in range(8):
        inter[i] = _expand_nibbles(bytes(pool[i]))[seed_input[transp[i]]]
    assembled = _collapse_nibbles(inter)
    return assembled[:4] + bytes([0x55, 0x45, 0x43, 0x55])


def ic172_algo2(seed, level, params):
    """IC172Algo2 (IC172 level 113). 4-byte seed/key."""
    if len(seed) != 4:
        return None
    pool = [
        [0, -1, -2, -3, -4, -5, -6, -7, -8, -9, -10, -11, -12, -13, -14, -15],
        [251, 252, 253, 254, 255, 256, 257, 258, 243, 244, 245, 246, 247, 248, 249, 250],
        [0, 1, -2, -1, 4, 5, 2, 3, 8, 9, 6, 7, 12, 13, 10, 11],
        [73, 72, 75, 74, 69, 68, 71, 70, 81, 80, 83, 82, 77, 76, 79, 78],
        [0, -1, -2, -3, 4, 3, 2, 1, 8, 7, 6, 5, 12, 11, 10, 9],
        [203, 202, 205, 204, 207, 206, 209, 208, 195, 194, 197, 196, 199, 198, 201, 200],
        [0, 1, 2, 3, -4, -3, -2, -1, 8, 9, 10, 11, 4, 5, 6, 7],
        [185, 184, 183, 182, 181, 180, 179, 178, 193, 192, 191, 190, 189, 188, 187, 186],
    ]
    nib = _expand_nibbles(seed)
    res = 0
    for i in range(8):
        res += pool[i][nib[i]] << ((7 - i) * 4)
    return (res & U32).to_bytes(4, "big")


# --- Powertrain matrix family (PowertrainSecurityAlgo / 2 / Delphi / NFZ) ---
def _d_value(b2, b1, b0, matrix) -> int:
    j = (1 if b0 else 0) | (2 if b1 else 0) | (4 if b2 else 0)
    m = matrix[j]
    return (m[3] | (m[2] << 8) | (m[1] << 16) | (m[0] << 24)) & U32


def _g_value_a1(b2, b1, b0, matrix) -> int:
    j = (1 if b0 else 0) | (2 if b1 else 0) | (4 if b2 else 0)
    m = matrix[j]
    return (m[2] | (m[1] << 8) | (m[0] << 16) | (m[3] << 24)) & U32


def _g_value_a2(b2, b1, b0, matrix) -> int:
    j = (1 if b0 else 0) | (2 if b1 else 0) | (4 if b2 else 0)
    m = matrix[j]
    return (m[0] | (m[3] << 8) | (m[2] << 16) | (m[1] << 24)) & U32


def _matrix_xx(params, prefix) -> list:
    return [[_p_byte(params, f"{prefix}{r}{c}") for c in range(4)] for r in range(8)]


def powertrain_algo(seed, level, params):
    """PowertrainSecurityAlgo. 4-byte. matrix X.., i1..i6, j1..j6."""
    if len(seed) != 4:
        return None
    matrix = _matrix_xx(params, "X")
    i = [_p_int(params, f"i{n}") for n in range(1, 7)]
    j = [_p_int(params, f"j{n}") for n in range(1, 7)]
    ws = bytes([seed[3], seed[2], seed[1], seed[0]])
    y = ws[i[0]] ^ ws[i[1]]
    d = _d_value(_get_bit(ws[i[2]], j[0]), _get_bit(ws[i[3]], j[1]), _get_bit(y, j[2]), matrix)
    s = int.from_bytes(ws, "little")
    dx = (s ^ d) & U32
    g = _g_value_a1(_get_bit(ws[i[4]], j[3]), _get_bit(y, j[4]),
                    _get_bit(_get_byte(dx, i[5]), j[5]), matrix)
    return ((dx ^ g) & U32).to_bytes(4, "big")


def powertrain_algo2(seed, level, params):
    """PowertrainSecurityAlgo2. matrix XX.., ii.., jj.. (different g ordering)."""
    if len(seed) != 4:
        return None
    matrix = _matrix_xx(params, "XX")
    i = [_p_int(params, f"ii{n}") for n in range(1, 7)]
    j = [_p_int(params, f"jj{n}") for n in range(1, 7)]
    ws = bytes([seed[3], seed[2], seed[1], seed[0]])
    y = ws[i[0]] ^ ws[i[1]]
    d = _d_value(_get_bit(ws[i[2]], j[0]), _get_bit(ws[i[3]], j[1]), _get_bit(y, j[2]), matrix)
    s = int.from_bytes(ws, "little")
    dx = (s ^ d) & U32
    g = _g_value_a2(_get_bit(ws[i[4]], j[3]), _get_bit(y, j[4]),
                    _get_bit(_get_byte(dx, i[5]), j[5]), matrix)
    return ((dx ^ g) & U32).to_bytes(4, "big")


def _matrix_dg(params, prefix) -> list:
    return [_p_bytes(params, f"{prefix}_{n}") for n in range(8)]


def powertrain_delphi(seed, level, params):
    """PowertrainDelphiSecurityAlgo (CRD2/CRD3/CRD3S2). D_VALUE/G_VALUE matrices."""
    if len(seed) != 4:
        return None
    dm = _matrix_dg(params, "D_VALUE")
    gm = _matrix_dg(params, "G_VALUE")
    ws = bytes([seed[3], seed[2], seed[1], seed[0]])
    y = ws[1] ^ ws[0]
    d = _d_value(_get_bit(ws[1] ^ ws[0], 3), _get_bit(ws[2], 3), _get_bit(ws[3], 6), dm)
    s = int.from_bytes(ws, "little")
    dx = (s ^ d) & U32
    g = _d_value(_get_bit(_get_byte(dx, 1), 2), _get_bit(y, 7), _get_bit(ws[1], 3), gm)
    return ((dx ^ g) & U32).to_bytes(4, "big")


def powertrain_nfz(seed, level, params):
    """PowertrainSecurityAlgoNFZ. D_VALUE/G_VALUE matrices, fixed bit picks."""
    if len(seed) != 4:
        return None
    dm = _matrix_dg(params, "D_VALUE")
    gm = _matrix_dg(params, "G_VALUE")
    ws = bytes([seed[3], seed[2], seed[1], seed[0]])
    d = _d_value(_get_bit(ws[3] ^ ws[1], 1), _get_bit(ws[2], 4), _get_bit(ws[0], 6), dm)
    s = int.from_bytes(ws, "little")
    dx = (s ^ d) & U32
    g = _d_value(_get_bit(ws[2], 6), _get_bit(ws[0], 1), _get_bit(_get_byte(dx, 3), 4), gm)
    return ((dx ^ g) & U32).to_bytes(4, "big")


_PT3_XOR = 0x40088C88
_PT3_BITS = [3, 7, 10, 11, 15, 19, 30]
_PT3_TABLE = [
    0x45D145D1, 0x406E47C6, 0x5450C446, 0x51EFC651, 0x47CE507A, 0x4271526D, 0x3121A3DA, 0x349EA1CD,
    0x0CECABBF, 0x0953A9A8, 0x105B10DF, 0x15E412C8, 0x3E1D91A6, 0x3BA293B1, 0xA316122F, 0xA6A91038,
    0x545044C6, 0x51EF46D1, 0x45D1C551, 0x406EC746, 0x3121235A, 0x349E214D, 0x47CED0FA, 0x4271D2ED,
    0x105B905F, 0x15E49248, 0x0CEC2B3F, 0x09532928, 0xA31692AF, 0xA6A990B8, 0x3E1D1126, 0x3BA21331,
    0xC4CE5450, 0xA54D2082, 0xD54FD5C7, 0xD3A2D322, 0xC6D141FB, 0xA7523529, 0xB03EB25B, 0xB6D3B4BE,
    0xD921E349, 0x884CB829, 0x442A60C0, 0x94FB0349, 0xEBD0D950, 0xBABD8230, 0xF7676230, 0x27B601B9,
    0xD54F5547, 0xD3A253A2, 0xC4CED4D0, 0xA54DA002, 0xB03E32DB, 0xB6D3343E, 0xC6D1C17B, 0xA752B5A9,
    0x442AE040, 0x94FB83C9, 0xD92163C9, 0x884C38A9, 0xF767E2B0, 0x27B68139, 0xEBD059D0, 0xBABD02B0,
    0xE3BF18F8, 0xDDA62A01, 0x9550EB58, 0xAB49D9A1, 0xE1A00D53, 0xDFB93FAA, 0xF0218CC4, 0xCE38BE3D,
    0xA1CAE9CA, 0x9FD3DB33, 0x3CC16A43, 0x02D858BA, 0x933BD3D3, 0xAD22E12A, 0x8F8C68B3, 0xB1955A4A,
    0x95506BD8, 0xAB495921, 0xE3BF9878, 0xDDA6AA81, 0xF0210C44, 0xCE383EBD, 0xE1A08DD3, 0xDFB9BF2A,
    0x3CC1EAC3, 0x02D8D83A, 0xA1CA694A, 0x9FD35BB3, 0x8F8CE833, 0xB195DACA, 0x933B5353, 0xAD2261AA,
    0x5A4815E4, 0x5CB8A6A1, 0x4BC99473, 0x4D392736, 0x5857004F, 0x5EA7B30A, 0x2EB8F3EF, 0x284840AA,
    0x103A4AD8, 0x16CAF99D, 0x0C8DF1B8, 0x0A7D42FD, 0x22CB70C1, 0x243BC384, 0xBFC0F348, 0xB930400D,
    0x4BC914F3, 0x4D39A7B6, 0x5A489564, 0x5CB82621, 0x2EB8736F, 0x2848C02A, 0x585780CF, 0x5EA7338A,
    0x0C8D7138, 0x0A7DC27D, 0x103ACA58, 0x16CA791D, 0xBFC073C8, 0xB930C08D, 0x22CBF041, 0x243B4304,
]


def powertrain_algo3(seed, level, params):
    """PowertrainSecurityAlgo3 (CRD3 level 1). 4-byte, no params, fixed table."""
    if len(seed) != 4:
        return None
    s = _be(seed, 0, 4)
    remap = 0
    for i, pos in enumerate(_PT3_BITS):
        if s & (1 << pos):
            remap |= (1 << i)
    key = (s ^ (s & _PT3_XOR) ^ _PT3_TABLE[remap]) & U32
    return key.to_bytes(4, "big")


# --- instrument cluster providers -------------------------------------------
def ki221_algo1(seed, level, params):
    """KI221Algo1 (W221 cluster). 8-byte seed -> 7-byte key."""
    if len(seed) != 8:
        return None
    lvl = _p_byte(params, "Level")
    k = bytearray(_p_bytes(params, "K"))
    root = _be(bytes(k))
    k[0] ^= seed[6]; k[1] ^= seed[4]; k[2] ^= seed[2]; k[3] ^= seed[0]
    rs = int.from_bytes(bytes([k[0], k[3], k[2], k[1]]), "little")
    inter = ((((rs << 29) & U32) + (rs >> 3)) & U32) ^ root
    key = (((inter >> 25) + ((inter << 7) & U32)) & U32)
    kb = key.to_bytes(4, "big")
    return bytes([lvl, kb[0], kb[3], kb[2], kb[1], 0, 0])


def ki221_algo2(seed, level, params):
    """KI221Algo2. 4-byte. key = (seed ^ Xor) + Add  (Xor/Add little-endian)."""
    if len(seed) != 4:
        return None
    xor = int.from_bytes(_p_bytes(params, "Xor"), "little")
    add = int.from_bytes(_p_bytes(params, "Add"), "little")
    return (((_be(seed, 0, 4) ^ xor) + add) & U32).to_bytes(4, "big")


def ki_algo1(seed, level, params):
    """KIAlgo1 (KI211 family). 8-byte seed -> 7-byte key."""
    if len(seed) != 8:
        return None
    lvl = _p_byte(params, "Level")
    root = _be(_p_bytes(params, "K"))
    sr = int.from_bytes(bytes([seed[2], seed[6], seed[0], seed[4]]), "little")
    rot = (sr & 7) + 2
    for _ in range(rot):
        msb = ((root >> 0) ^ (root >> 7) ^ (root >> 17) ^ (root >> 26)) & 1
        root = (root & 0x7FFFFFFF) | (0x80000000 if msb else 0)
        root = _rotr32(root, 1)
    sh, sl = (sr >> 16) & 0xFFFF, sr & 0xFFFF
    for _ in range(2):
        sh = _rotl16((sh ^ sl) & 0xFFFF, rot)
        tangled = (sh + (root & 0xFFFF)) & 0xFFFF
        root >>= 16
        sh, sl = sl, tangled
    pb = ((sl | (sh << 16)) & U32).to_bytes(4, "little")
    return bytes([lvl, pb[0], pb[1], pb[3], pb[2], 0xFF, 0xFF])


def ki203_algo(seed, level, params):
    """KI203Algo. 4-byte. rotate/xor with root key (BE), rotate by popcount."""
    if len(seed) != 4:
        return None
    root = _be(_p_bytes(params, "K"))
    val = (seed[2] | (seed[0] << 8) | (seed[3] << 16) | (seed[1] << 24)) & U32
    val = _rotr32(_rotl32(val, 3) ^ root, _count_ones(root))
    return bytes([_get_byte(val, 0), _get_byte(val, 2),
                  _get_byte(val, 3), _get_byte(val, 1)])


# --- IC204 (W204/W221 'IC' cluster, NEC V850) -------------------------------
def _ic204_rotr(buf: bytearray, off: int, length: int):
    if length == 0 or length > 8:
        return
    carries = [buf[off + i] & 1 for i in range(length)]
    for i in range(length):
        ci = length - 1 if i == 0 else i - 1
        sh = (buf[off + i] >> 1) & 0x7F
        buf[off + i] = sh | (0x80 if carries[ci] else 0)


def _ic204_salt(salt: bytes) -> bytes:
    g = bytearray(0x14)
    g[0x0C:0x14] = salt[:8]
    for i in range(4): g[i] = g[0x10 + i]
    for i in range(4): g[0x04 + i] = g[0x0C + i]
    for i in range(4): g[0x08 + i] = g[i]
    t0, t1, t2, t3 = g[0x08], g[0x09], g[0x0A], g[0x0B]
    g[0x02], g[0x00], g[0x01], g[0x03] = t0, t1, t3, t2
    for _ in range((t2 & 0x0F) + 1): _ic204_rotr(g, 0, 4)
    for _ in range((g[0x0B] & 0x0F) + 1): _ic204_rotr(g, 0x08, 4)
    for i in range(4): g[i] ^= g[0x08 + i]
    for i in range(4): g[0x08 + i] = g[0x04 + i]
    t0, t1, t2, t3 = g[0x08], g[0x09], g[0x0A], g[0x0B]
    g[0x06], g[0x04], g[0x05], g[0x07] = t0, t1, t3, t2
    for _ in range((g[0x0A] & 0x0F) + 1): _ic204_rotr(g, 0x04, 4)
    for _ in range((g[0x0B] & 0x0F) + 1): _ic204_rotr(g, 0x08, 4)
    for i in range(4): g[0x04 + i] ^= g[0x08 + i]
    for i in range(4): g[0x10 + i] = g[i]
    for i in range(4): g[0x0C + i] = g[0x04 + i]
    return bytes(g[0x0C:0x14])


def _ic204_fb(ws: bytearray):
    fb = (ws[0x08] >> 3) & 1
    fb ^= ws[0x09] & 1
    fb ^= (ws[0x0A] >> 1) & 1
    fb ^= (ws[0x0B] >> 7) & 1
    fb ^= (ws[0x0C] >> 5) & 1
    fb ^= (ws[0x0D] >> 2) & 1
    fb ^= (ws[0x0E] >> 6) & 1
    fb ^= (ws[0x0F] >> 4) & 1
    ws[0x0F] = (ws[0x0F] & 0x7F) | (fb << 7)


def _le32(b, o): return b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)


def _le32s(b, o, v):
    b[o] = v & 0xFF; b[o + 1] = (v >> 8) & 0xFF
    b[o + 2] = (v >> 16) & 0xFF; b[o + 3] = (v >> 24) & 0xFF


def ic204(seed, level, params):
    """IC204 (W204/W221 cluster, NEC V850). 8-byte seed/key, param 'Salt' (8B)."""
    salt = _p_bytes(params, "Salt")
    if len(seed) != 8 or len(salt) != 8:
        return None
    lv = {1: 1, 3: 3, 9: 5, 0xD: 7}.get(level, (level + 1) // 2)
    if lv < 1 or lv > 7:
        return None
    ws = bytearray(0x20)
    for i, si in enumerate((7, 4, 3, 6, 5, 1, 0, 2)):
        ws[0x10 + i] = seed[si]
    cnt = (ws[0x10 + lv] & 0x07) + 2
    ws[0x08:0x10] = _ic204_salt(salt)
    for _ in range(cnt):
        _ic204_fb(ws); _ic204_rotr(ws, 0x08, 8)
    ws[0x00:0x08] = ws[0x10:0x18]
    for _ in range(2):
        for i in range(4): ws[0x10 + i] ^= ws[0x14 + i]
        for _ in range((ws[lv] & 0x03) + 1): _ic204_rotr(ws, 0x10, 4)
        _le32s(ws, 0x10, (_le32(ws, 0x10) + _le32(ws, 0x08)) & U32)
        ws[0x14:0x18] = ws[0x00:0x04]; ws[0x00:0x08] = ws[0x10:0x18]
        for i in range(4): ws[0x10 + i] ^= ws[0x14 + i]
        for _ in range((ws[lv] & 0x03) + 1): _ic204_rotr(ws, 0x10, 4)
        _le32s(ws, 0x10, (_le32(ws, 0x10) + _le32(ws, 0x0C)) & U32)
        ws[0x14:0x18] = ws[0x00:0x04]; ws[0x00:0x08] = ws[0x10:0x18]
    return bytes([ws[3], ws[5], ws[6], ws[1], ws[0], ws[7], ws[4], ws[2]])


PROVIDERS = {
    "DaimlerStandardSecurityAlgo": daimler_standard,
    "DaimlerStandardSecurityAlgoMod": daimler_standard_mod,
    "DaimlerStandardSecurityAlgoRefG": daimler_standard_refg,
    "PowertrainBoschContiSecurityAlgo1": powertrain_boschconti_1,
    "PowertrainBoschContiSecurityAlgo2": powertrain_boschconti_2,
    "PowertrainSecurityAlgo": powertrain_algo,
    "PowertrainSecurityAlgo2": powertrain_algo2,
    "PowertrainSecurityAlgo3": powertrain_algo3,
    "PowertrainSecurityAlgoNFZ": powertrain_nfz,
    "PowertrainDelphiSecurityAlgo": powertrain_delphi,
    "VGSSecurityAlgo": vgs,
    "VGSSecurityAlgo2Bytes": vgs_2bytes,
    "VGSSecurityAlgoExt": vgs_ext,
    "IC172Algo1": ic172_algo1,
    "IC172Algo2": ic172_algo2,
    "IC204": ic204,
    "KI221Algo1": ki221_algo1,
    "KI221Algo2": ki221_algo2,
    "KIAlgo1": ki_algo1,
    "KI203Algo": ki203_algo,
    "ESPSecurityAlgoLevel1": esp_level1,
    "XorAlgo": xor_algo,
}


# ---------------------------------------------------------------------------
# Definition database
# ---------------------------------------------------------------------------
_DEFS: dict | None = None


def _load_defs() -> dict:
    global _DEFS
    if _DEFS is not None:
        return _DEFS
    _DEFS = {}
    if DB_PATH.exists():
        try:
            data = json.loads(DB_PATH.read_text(encoding="utf-8"))
            entries = data if isinstance(data, list) else data.get("Definitions", [])
            for d in entries:
                name = d.get("EcuName")
                if name:
                    _DEFS.setdefault(name, []).append(d)
                for alias in d.get("Aliases", []) or []:
                    _DEFS.setdefault(alias, []).append(d)
        except Exception:  # noqa: BLE001
            pass
    return _DEFS


def available() -> bool:
    return bool(_load_defs())


def find_definition(ecu_name: str, level: int) -> dict | None:
    defs = _load_defs().get(ecu_name, [])
    for d in defs:
        if d.get("AccessLevel") == level:
            return d
    return defs[0] if defs else None


def levels_for(ecu_name: str) -> list[dict]:
    """All access levels defined for an ECU, with provider + ported flag."""
    out = []
    for d in _load_defs().get(ecu_name, []):
        out.append({
            "level": d.get("AccessLevel"),
            "provider": d.get("Provider"),
            "seed_length": d.get("SeedLength"),
            "key_length": d.get("KeyLength"),
            "ported": d.get("Provider") in PROVIDERS,
        })
    return sorted(out, key=lambda x: (x["level"] is None, x["level"]))


def _params_map(d: dict) -> dict:
    return {p["Key"]: p for p in d.get("Parameters", []) or []}


def generate_key(ecu_name: str, seed: bytes, level: int = 1):
    """Return (key_bytes, info) or (None, reason)."""
    d = find_definition(ecu_name, level)
    if not d:
        return None, f"no seed-key definition for '{ecu_name}'"
    provider = d.get("Provider")
    fn = PROVIDERS.get(provider)
    if fn is None:
        return None, f"provider '{provider}' not ported yet"
    exp = d.get("SeedLength")
    if exp and len(seed) != exp:
        return None, f"seed length {len(seed)} != expected {exp}"
    try:
        key = fn(seed, level, _params_map(d))
    except Exception as e:  # noqa: BLE001
        return None, f"provider error: {e}"
    if key is None:
        return None, f"provider '{provider}' rejected the seed"
    return key, {"provider": provider, "origin": d.get("Origin")}


def provider_for(ecu_name: str) -> str | None:
    d = find_definition(ecu_name, 1)
    return d.get("Provider") if d else None
