"""VIN decoding (pure logic, no hardware)."""

from __future__ import annotations

from backend.mb.vehicle import decode_vin


def test_decode_simulator_vin():
    d = decode_vin("WDC1641541A123456")
    assert d["valid"] is True
    assert d["wmi"] == "WDC"
    assert "SUV" in d["maker"]
    assert d["year"] == 2001


def test_decode_short_vin_is_invalid():
    d = decode_vin("WDC123")
    assert d["valid"] is False


def test_decode_handles_garbage():
    for junk in ("", None, "   ", "!!!@@@###$$$%%%^^"):
        d = decode_vin(junk)
        assert d["valid"] is False
