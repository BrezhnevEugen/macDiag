"""
Flash (ECU reprogramming) module - SCAFFOLD, read-only.

Iteration 1 (this file): identify and catalogue flash images (CFF), read ECU
software/hardware versions and reprogramming status over diagnostics. NO writing.

Iteration 2 (future, separate): the actual flash sequence (programming session ->
security access -> erase routine -> RequestDownload/TransferData/TransferExit ->
checksum/signature validation). Intentionally NOT implemented here: a wrong or
interrupted flash can brick an ECU. The write entrypoint raises NotImplementedError
on purpose, and must only be built with hard safety gates (CRC/signature checks,
power monitoring, abort/recovery) and bench testing first.

CFF library directory comes from env MACDIAG_CFF_DIR (mounted data volume).
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))
import parse_cff as _cff  # noqa: E402

CFF_DIR = Path(os.environ.get("MACDIAG_CFF_DIR",
                              str(Path(__file__).resolve().parent.parent.parent / "data" / "cff")))

# Standard MB identification DIDs (read-only)
VERSION_DIDS = {
    0xF190: "VIN",
    0xF187: "MB part number",
    0xF153: "HW version",
    0xF150: "HW part number",
    0xF195: "SW version",
    0xF151: "SW part number",
    0xF17C: "boot SW id",
}


# --- CFF library (read-only catalogue) --------------------------------------
def available() -> bool:
    return CFF_DIR.exists() and any(CFF_DIR.rglob("*.cff")) if CFF_DIR.exists() else False


@lru_cache(maxsize=1)
def _index() -> dict:
    idx = {}
    if CFF_DIR.exists():
        for p in CFF_DIR.rglob("*"):
            if p.suffix.lower() == ".cff":
                idx.setdefault(p.stem, p)
    return idx


def library(q: str | None = None, chassis: str | None = None,
            limit: int = 300) -> list[dict]:
    """List flash images with light metadata (lazy header parse)."""
    out = []
    for name, p in sorted(_index().items()):
        if q and q.lower() not in name.lower():
            continue
        try:
            meta = _cff.parse_cff(p)
        except Exception:  # noqa: BLE001
            meta = {"file": p.name, "ecu": name, "error": "parse failed"}
        if chassis and meta.get("chassis_hint") and \
                chassis.lstrip("WXCRS") != meta["chassis_hint"]:
            continue
        out.append({"name": name, "ecu": meta.get("ecu"),
                    "part_numbers": meta.get("part_numbers", []),
                    "chassis_hint": meta.get("chassis_hint"),
                    "segments": meta.get("segments", []),
                    "date": meta.get("header", {}).get("DATE")})
        if len(out) >= limit:
            break
    return out


def cff_info(name: str) -> dict | None:
    p = _index().get(name)
    if not p:
        return None
    return _cff.parse_cff(p)


# --- ECU read-only checks (over diagnostics) --------------------------------
def read_versions(client) -> dict:
    """Read identification DIDs from a connected ECU. Read-only."""
    out = {}
    for did, label in VERSION_DIDS.items():
        try:
            raw = client.read_did(did)
            out[label] = raw.decode("ascii", "replace").strip()
        except Exception:  # noqa: BLE001
            out[label] = None
    return out


# --- write path: intentionally not implemented ------------------------------
def program(*_args, **_kwargs):
    raise NotImplementedError(
        "Flashing is a future iteration. Writing firmware can brick an ECU and "
        "must only be implemented with full safety gates (CRC/signature, power "
        "monitoring, abort/recovery) and bench testing. Read-only for now."
    )
