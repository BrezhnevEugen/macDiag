"""
Seed-key provider regression tests.

Fixtures:
  * fixtures/unlock_db_subset.json — one definition per ported provider,
    extracted from the UnlockECU db.json (MIT, github.com/jglim/UnlockECU).
  * fixtures/unlock_golden.json — frozen seed→key vectors computed by the
    ported providers (several families were verified bit-exact against the
    UnlockECU reference implementation; the rest lock in current behaviour
    so any regression in the bit-twiddling shows up immediately).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.mb import unlock

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _use_fixture_db(monkeypatch):
    monkeypatch.setattr(unlock, "DB_PATH", FIXTURES / "unlock_db_subset.json")
    monkeypatch.setattr(unlock, "_DEFS", None)
    yield
    unlock._DEFS = None   # don't leak the fixture db into other tests


def _golden():
    return json.loads((FIXTURES / "unlock_golden.json").read_text())


def test_every_ported_provider_has_a_golden_vector():
    covered = {v["provider"] for v in _golden()}
    assert covered == set(unlock.PROVIDERS)


@pytest.mark.parametrize("vec", _golden(), ids=lambda v: v["provider"])
def test_golden_vector(vec):
    key, info = unlock.generate_key(vec["ecu"], bytes.fromhex(vec["seed"]),
                                    vec["level"])
    assert key is not None, f"provider failed: {info}"
    assert key.hex() == vec["key"]
    assert info["provider"] == vec["provider"]


def test_key_length_matches_definition():
    defs = json.loads((FIXTURES / "unlock_db_subset.json").read_text())
    for d in defs:
        if not d.get("KeyLength"):
            continue
        seed = bytes(range(1, 1 + d["SeedLength"]))
        key, info = unlock.generate_key(d["EcuName"], seed,
                                        d.get("AccessLevel") or 1)
        if key is not None:   # some providers reject specific seeds — fine
            assert len(key) == d["KeyLength"], d["EcuName"]


def test_unknown_ecu_is_reported_not_raised():
    key, reason = unlock.generate_key("NO_SUCH_ECU", b"\x01\x02\x03\x04")
    assert key is None
    assert "no seed-key definition" in reason


def test_wrong_seed_length_rejected():
    vec = _golden()[0]
    seed = bytes.fromhex(vec["seed"]) + b"\x00"   # one byte too long
    key, reason = unlock.generate_key(vec["ecu"], seed, vec["level"])
    assert key is None
    assert "seed length" in reason
