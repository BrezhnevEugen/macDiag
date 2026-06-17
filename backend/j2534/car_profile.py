"""
Real-car profile for the simulator — captured from THIS vehicle (W164/X164,
engine M273) via the trace log. Makes SimPassThru answer exactly like the car so
the whole app can be developed/tested without the vehicle.

PROFILE[tx] = {"name", "silent"?, "resp": {request_hex: response_hex | None}}
  * response_hex None  -> the ECU stayed silent (timeout)
  * "silent": True     -> ECU not fitted; everything times out
  * a request not listed on a responding ECU falls through to the generic
    synthetic logic in SimPassThru (so new flows, e.g. service 0x17, are testable)

NRC responses are 7F <sid> <nrc>. Captured verbatim.
"""

_NRC_TP = "7F3E12"      # 3E00 -> subFunctionNotSupported (present, MB body ECU)
_NRC_DTC18_12 = "7F1812"
_NRC_DTC18_11 = "7F1811"

PROFILE = {
    # ---- central gateway (ZGW, UDS) — opens with session 0x1092 ----
    0x4E4: {"name": "ZGW", "resp": {
        "1092": "5092",
        "310800": "7108BD359A2804400600",
        "310700": "71070080BD75DAE940402701000000000000",
        "310500": "71050000000000000000",
        "300101": "700101110A20938AFA91921800000200000000050018000080680D"
                  "0000000000000000000000000000",
        "2300100D01": "6302",
        "21E0": "61E0681222080114034302490233014999990202",
        "3E00": _NRC_TP, "1A90": "7F1A12", "22F190": "7F2280", "0902": "7F0980",
        "1902FF": "7F1980", "18FFFF00": _NRC_DTC18_12, "03": "7F0380",
    }},
    # ---- EZS / EIS (KWP) ----
    0x4E0: {"name": "EZS", "resp": {
        "3E00": "7E00", "18FFFF00": _NRC_DTC18_11, "1A90": "7F1A11",
        "2190": "7F2111", "0902": "7F0911", "2105": "7F2111", "2106": "7F2111",
        "21E0": "7F2111", "1092": "7F1012", "22F190": None,
    }},
    # ---- engine (ME-SFI M273, UDS @ 0x7E0): OBD mode 03 works ----
    # VIN (1A90/22F190/0902) was not captured on this car — left silent so the
    # emulator is honest; the real VIN is read from the car on hardware, and
    # identity (engine/chassis/equipment) comes from the gateway global code.
    0x7E0: {"name": "engine", "resp": {
        "3E00": _NRC_TP, "1902FF": "7F1911", "18FFFF00": _NRC_DTC18_12,
        "03": "4300", "1A90": None, "22F190": None, "0902": None,
    }},
    0x7E1: {"name": "VGS", "resp": {
        "3E00": "7E00", "1902FF": "7F1911", "18FFFF00": _NRC_DTC18_12, "03": "7F0311",
    }},
    0x5B4: {"name": "KI", "resp": {"3E00": _NRC_TP, "18FFFF00": None}},
    0x662: {"name": "SAM-V", "resp": {"3E00": _NRC_TP, "18FFFF00": None}},
    0x563: {"name": "SAM-H", "resp": {"3E00": _NRC_TP, "18FFFF00": _NRC_DTC18_12}},
    0x791: {"name": "KLA", "resp": {"3E00": _NRC_TP, "18FFFF00": _NRC_DTC18_12}},
    0x792: {"name": "MRM", "resp": {"3E00": _NRC_TP, "18FFFF00": _NRC_DTC18_12}},
    0x784: {"name": "RBS", "resp": {"3E00": _NRC_TP, "18FFFF00": _NRC_DTC18_12}},
    # ---- not fitted on this car (silent) ----
    0x778: {"name": "FSCM", "silent": True, "resp": {}},
    0x632: {"name": "ESP", "silent": True, "resp": {}},
    0x612: {"name": "EIS447(W221)", "silent": True, "resp": {}},
    0x60A: {"name": "KI(W221)", "silent": True, "resp": {}},
    0x6B2: {"name": "EPS(W221)", "silent": True, "resp": {}},
    0x6FA: {"name": "FSCM(W221)", "silent": True, "resp": {}},
}


def lookup(tx_id: int, request_hex: str):
    """Return (matched, response_or_None). matched=False -> not in profile, use
    the generic simulator. matched=True, None -> captured timeout/silent."""
    prof = PROFILE.get(tx_id)
    if prof is None:
        return False, None
    if prof.get("silent"):
        return True, None
    rh = request_hex.upper()
    if rh in prof["resp"]:
        return True, prof["resp"][rh]
    return False, None   # known ECU, request not captured -> generic synth
