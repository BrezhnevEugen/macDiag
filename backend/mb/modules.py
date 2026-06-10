"""
Mercedes-Benz W221 (S-Class) and X164 (GL-Class) diagnostic module map.

Both platforms (2006-2013) use a multi-CAN architecture. The OBD socket exposes
the diagnostic CAN bus; individual control units are addressed by their UDS
request/response CAN identifiers. Many MB units of this era answer KWP2000-over-
CAN; newer ones answer UDS. The PassThru/UDS layer auto-falls back where needed.

NOTE: request/response IDs below are the common MB diagnostic addressing for
these chassis. Verify against your specific car: equipment, model year and
facelift (W221 pre/post 2009) change which units are fitted and their exact IDs.
A real session should always confirm the VIN (DID 0xF190) first.

Each entry:
    id        - short key used by the API/UI
    name      - human label
    tx        - UDS request CAN ID (tester -> ECU)
    rx        - UDS response CAN ID (ECU -> tester)
    chassis   - which platforms carry this unit
    protocol  - 'uds' or 'kwp'
"""

MODULES = [
    # --- core / always present ------------------------------------------
    {"id": "ezs",  "name": "EZS / EIS (ignition switch, gateway)", "tx": 0x7E4, "rx": 0x7EC, "chassis": ["W221", "X164"], "protocol": "kwp"},
    {"id": "me",   "name": "ME-SFI engine ECU (petrol)",            "tx": 0x7E0, "rx": 0x7E8, "chassis": ["W221", "X164"], "protocol": "uds"},
    {"id": "cdi",  "name": "CDI engine ECU (diesel)",               "tx": 0x7E0, "rx": 0x7E8, "chassis": ["W221", "X164"], "protocol": "uds"},
    {"id": "722",  "name": "7G-Tronic transmission (VGS)",          "tx": 0x7E1, "rx": 0x7E9, "chassis": ["W221", "X164"], "protocol": "uds"},
    {"id": "esp",  "name": "ESP / ABS / BAS",                       "tx": 0x7E5, "rx": 0x7ED, "chassis": ["W221", "X164"], "protocol": "kwp"},
    {"id": "srs",  "name": "SRS airbag (front passenger occ.)",     "tx": 0x7E6, "rx": 0x7EE, "chassis": ["W221", "X164"], "protocol": "kwp"},

    # --- body / SAM -----------------------------------------------------
    {"id": "sam_front", "name": "Front SAM (signal/fuse module)",   "tx": 0x7C0, "rx": 0x7C8, "chassis": ["W221", "X164"], "protocol": "kwp"},
    {"id": "sam_rear",  "name": "Rear SAM (signal/fuse module)",    "tx": 0x7C1, "rx": 0x7C9, "chassis": ["W221", "X164"], "protocol": "kwp"},
    {"id": "ic",   "name": "Instrument cluster (IC)",               "tx": 0x7C4, "rx": 0x7CC, "chassis": ["W221", "X164"], "protocol": "uds"},

    # --- comfort / chassis ---------------------------------------------
    {"id": "airmatic", "name": "AIRMATIC / ABC suspension",         "tx": 0x7C5, "rx": 0x7CD, "chassis": ["W221", "X164"], "protocol": "kwp"},
    {"id": "ssm",  "name": "Signal acquisition module (SSM)",       "tx": 0x7C6, "rx": 0x7CE, "chassis": ["W221"], "protocol": "kwp"},
    {"id": "kg",  "name": "Keyless-Go control unit",                "tx": 0x7C7, "rx": 0x7CF, "chassis": ["W221"], "protocol": "kwp"},
    {"id": "drz", "name": "PTS / Parktronic",                       "tx": 0x7C2, "rx": 0x7CA, "chassis": ["W221", "X164"], "protocol": "kwp"},

    # --- transfer case (GL) --------------------------------------------
    {"id": "vg",  "name": "Transfer case VG (X164 4MATIC)",         "tx": 0x7E2, "rx": 0x7EA, "chassis": ["X164"], "protocol": "uds"},
]

MODULES_BY_ID = {m["id"].strip(): m for m in MODULES}


def modules_for(chassis: str | None = None):
    if not chassis:
        return MODULES
    return [m for m in MODULES if chassis in m["chassis"]]
