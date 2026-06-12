"""
API smoke tests against the simulator (no hardware, no proprietary data).

The FastAPI app is exercised through TestClient exactly as the SPA uses it:
connect → vehicle info → DTC read/clear → identify → live WebSocket stream.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import backend.main as main


@pytest.fixture(scope="module")
def client():
    assert main.MODE == "sim", "API tests must run against the simulator"
    with TestClient(main.app) as c:
        yield c
    main.session.disconnect()


def test_status(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    assert r.json()["mode"] == "sim"


def test_connect_reports_voltage(client):
    r = client.post("/api/connect")
    assert r.status_code == 200
    body = r.json()
    assert body["connected"] is True
    assert 10 < (body.get("voltage") or 0) < 16


def test_vehicle_info_vin(client):
    client.post("/api/connect")
    r = client.get("/api/vehicle/info")
    body = r.json()
    assert len(body["vin"]) == 17
    assert body["decode"]["valid"] is True


def test_dtc_read_and_clear(client):
    client.post("/api/connect")
    r = client.get("/api/dtc")
    body = r.json()
    assert r.status_code == 200
    assert body["readable"] is True
    codes = {d["code"] for d in body["dtcs"]}
    assert {"B1535", "C1525"} <= codes          # simulator's two seeded faults
    assert all(d.get("description") for d in body["dtcs"])

    assert client.post("/api/dtc/clear").status_code == 200
    after = client.get("/api/dtc").json()
    assert after["dtcs"] == []


def test_identify(client):
    client.post("/api/connect")
    r = client.get("/api/identify")
    assert r.status_code == 200
    assert isinstance(r.json().get("info"), dict)


def test_security_unlock_sim(client):
    client.post("/api/connect")
    r = client.post("/api/security/unlock")
    assert r.status_code == 200
    body = r.json()
    # either the real provider chain or the sim fallback must produce a verdict
    assert "unlocked" in body
    assert body.get("seed"), "seed must be reported for the audit trail"


def test_coding_write_backs_up_old_value(client, tmp_path, monkeypatch):
    from backend.mb import backup
    monkeypatch.setattr(backup, "PATH", tmp_path / "backups.jsonl")
    client.post("/api/connect")
    r = client.post("/api/coding/write",
                    json={"did": 0x0110, "value_hex": "AABB", "unlock": True})
    body = r.json()
    assert body["ok"] is True
    bkp = body["backup"]
    assert bkp["saved"] is True
    assert bkp["new"] == "AABB"
    assert bkp["old"] or bkp["read_error"]      # old value read, or failure recorded
    entries = client.get("/api/coding/backups").json()["entries"]
    assert entries and entries[0]["new"] == "AABB"


def test_coding_write_validates_hex(client):
    client.post("/api/connect")
    r = client.post("/api/coding/write", json={"did": 0x0110, "value_hex": "ZZZZ"})
    assert r.status_code in (400, 422), (
        "malformed hex must be a client error, not a 5xx")


def test_ws_live_stream_and_pid_selection(client):
    client.post("/api/connect")
    with client.websocket_connect("/ws/live") as ws:
        frame = ws.receive_json()
        assert "frame" in frame and len(frame["frame"]) > 0
        ws.send_json({"pids": [12, 13]})
        for _ in range(5):                      # selection applies within a few frames
            got = [p.get("pid") for p in ws.receive_json()["frame"]]
            if got == [12, 13]:
                break
        else:
            pytest.fail(f"pid selection not applied, last frame: {got}")


def test_catalog_endpoints_do_not_crash_without_db(client):
    # with or without ecu_db.sqlite these must answer cleanly
    assert client.get("/api/db/stats").status_code == 200
    assert client.get("/api/modules").status_code == 200
