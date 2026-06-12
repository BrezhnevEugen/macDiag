"""Vehicle identification: read VIN over diagnostics and decode it (light)."""

from __future__ import annotations

import re

_VIN_OK = re.compile(r"[^A-HJ-NPR-Z0-9]")

# Mercedes WMI (first 3 VIN chars) -> region / body family
WMI = {
    "WDB": "Mercedes-Benz (седан, Германия)",
    "WDD": "Mercedes-Benz (легковой, Германия)",
    "WDC": "Mercedes-Benz SUV (M/GL/GLK/R, Германия)",
    "WDF": "Mercedes-Benz (фургон: Sprinter/Vito)",
    "WMX": "Mercedes-AMG",
    "4JG": "Mercedes-Benz SUV (США, Tuscaloosa — M/GL/GLE/GLS)",
    "55S": "Mercedes-Benz (США)",
}

# 10th VIN char -> model year (1980-2039 cycle; we map the relevant window)
_YEAR = {**{str(d): 2000 + d for d in range(1, 10)},  # 1..9 -> 2001..2009
         "A": 2010, "B": 2011, "C": 2012, "D": 2013, "E": 2014, "F": 2015,
         "G": 2016, "H": 2017, "J": 2018, "K": 2019, "L": 2020, "M": 2021,
         "N": 2022, "P": 2023, "R": 2024, "S": 2025}


def decode_vin(vin: str) -> dict:
    vin = (vin or "").strip().upper()
    out = {"vin": vin, "valid": len(vin) == 17}
    if len(vin) < 11:
        return out
    out["wmi"] = vin[:3]
    out["maker"] = WMI.get(vin[:3], "неизвестный изготовитель")
    out["year"] = _YEAR.get(vin[9])
    out["plant"] = vin[10]
    # MB body/chassis digits live in the VDS (chars 4-8); expose them raw
    out["vds"] = vin[3:8]
    return out


def _clean_vin(s: str) -> str:
    return _VIN_OK.sub("", (s or "").upper())


def _vin_from_mode09(resp: bytes) -> str | None:
    """Parse an OBD mode-09 PID-02 response: 0x49 0x02 [count] <17 ASCII>."""
    if not resp:
        return None
    i = resp.find(b"\x49\x02")
    tail = resp[i + 2:] if i >= 0 else resp
    ascii_txt = "".join(chr(b) for b in tail if 0x30 <= b <= 0x5A or 0x61 <= b <= 0x7A)
    v = _clean_vin(ascii_txt)
    return v[-17:] if len(v) >= 17 else (v if len(v) >= 11 else None)


# DIDs / services that carry the VIN, tried in order
def read_vin(client) -> tuple[str | None, str]:
    """UDS ReadDataByIdentifier 0xF190, then OBD mode 09 PID 02. Returns
    (vin_or_None, reason) so the UI can show *why* it failed."""
    detail = "блок не ответил"
    # MB readEcuIdentification 0x1A 0x90 (the real Mercedes VIN service)
    try:
        resp = client.raw_request(bytes([0x1A, 0x90]))
        if resp and resp[0] == 0x5A:
            v = _clean_vin(resp[2:].decode("ascii", "ignore"))
            if len(v) >= 11:
                return (v[-17:] if len(v) >= 17 else v), "ok (1A90)"
        detail = "1A90: VIN не распознан"
    except Exception as e:  # noqa: BLE001
        detail = f"1A90: {e}"
    try:
        raw = client.read_did(0xF190)
        v = _clean_vin(raw.decode("ascii", "ignore"))
        if len(v) >= 11:
            return (v[-17:] if len(v) >= 17 else v), "ok (UDS 0xF190)"
        detail = "0xF190: пустой ответ"
    except Exception as e:  # noqa: BLE001
        detail = f"0xF190: {e}"
    try:
        resp = client.raw_request(bytes([0x09, 0x02]))
        v = _vin_from_mode09(resp)
        if v:
            return v, "ok (OBD mode 09)"
        detail = "OBD mode 09: VIN не распознан"
    except Exception as e:  # noqa: BLE001
        detail = f"OBD mode 09: {e}"
    return None, detail
