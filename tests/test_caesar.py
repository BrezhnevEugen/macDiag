"""
Caesar/CBF parser tests against a real Vediamo CBF.

These need the proprietary data library (gitignored), so they self-skip when
./data/cbf is absent — locally they pin the parser to known-good values
(EZS164: KWP over the 83.3k interior CAN, req 0x4E0 / resp 0x5FF).
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EZS = ROOT / "data" / "cbf" / "EZS164.cbf"

pytestmark = pytest.mark.skipif(not EZS.exists(),
                                reason="proprietary CBF library not present")


def test_parse_cbf_ezs164():
    from parse_cbf import parse_cbf
    info = parse_cbf(EZS)
    assert info["ecu"] == "EZS164"
    assert info["protocol"] == "kwp"


def test_comparam_real_can_ids():
    from caesar_comparam import parse_file
    cp = parse_file(EZS)["ecus"][0]["can"]
    assert cp["CP_REQUEST_CANIDENTIFIER"] == 0x4E0
    assert cp["CP_RESPONSE_CANIDENTIFIER"] == 0x5FF
    assert cp["CP_BAUDRATE"] == 83333


def test_ecu_db_has_ezs164_ids():
    db = ROOT / "data" / "ecu_db.sqlite"
    if not db.exists():
        pytest.skip("ecu_db.sqlite not built")
    import sqlite3
    row = sqlite3.connect(db).execute(
        "SELECT can_request, can_response, baudrate FROM ecu WHERE name='EZS164'"
    ).fetchone()
    assert row == (0x4E0, 0x5FF, 83333)
