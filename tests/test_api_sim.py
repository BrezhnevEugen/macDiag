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
    body = r.json()
    assert body["mode"] == "sim"
    assert body["profile"]["id"] == "w221-x164"
    assert body["adapter"]["kind"] == "simulator"
    assert "ISO15765" in body["adapter"]["capabilities"]["protocols"]


def test_adapter_self_test_reports_transport_health(client):
    r = client.post("/api/adapter/self-test")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["connected"] is True
    assert body["channel"] == {"protocol": "ISO15765", "baudrate": 500000}
    checks = {check["id"]: check for check in body["checks"]}
    assert checks["transport"]["status"] == "ok"
    assert checks["channel"]["status"] == "ok"
    assert checks["voltage"]["status"] == "ok"

    status = client.get("/api/adapter/status")
    assert status.status_code == 200
    assert status.json()["version"]["firmware"] == "OP2-SIM"

    legacy = client.get("/api/adapter/info")
    assert legacy.status_code == 200
    assert legacy.json()["adapter"]["api"] == "04.04"
    assert legacy.json()["transport"]["kind"] == "simulator"


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


def test_dtc_read_and_clear(client, tmp_path, monkeypatch):
    from backend.mb import audit
    monkeypatch.setattr(audit, "PATH", tmp_path / "action_audit.jsonl")
    client.post("/api/connect")
    r = client.get("/api/dtc")
    body = r.json()
    assert r.status_code == 200
    assert body["readable"] is True
    codes = {d["code"] for d in body["dtcs"]}
    assert {"P0170", "P0300"} <= codes           # engine demo scenario's seeded faults
    assert all(d.get("description") for d in body["dtcs"])

    cleared = client.post("/api/dtc/clear")
    assert cleared.status_code == 200
    assert cleared.json()["audit"]["outcome"] == "success"
    assert len(cleared.json()["audit"]["id"]) == 36
    after = client.get("/api/dtc").json()
    assert after["dtcs"] == []
    events = client.get("/api/audit/actions").json()["entries"]
    assert events[0]["operation"] == "dtc_clear"
    assert events[0]["id"] == cleared.json()["audit"]["id"]


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
    from backend.mb import audit, backup
    monkeypatch.setattr(backup, "PATH", tmp_path / "backups.jsonl")
    monkeypatch.setattr(audit, "PATH", tmp_path / "action_audit.jsonl")
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
    events = client.get("/api/audit/actions").json()["entries"]
    assert events[0]["operation"] == "coding_write"
    assert events[0]["outcome"] == "success"
    assert events[0]["id"] == body["audit"]["id"]


def test_coding_write_validates_hex(client):
    client.post("/api/connect")
    r = client.post("/api/coding/write", json={"did": 0x0110, "value_hex": "ZZZZ"})
    assert r.status_code in (400, 422), (
        "malformed hex must be a client error, not a 5xx")


def test_hardware_writes_require_explicit_server_opt_in(client, tmp_path, monkeypatch):
    from backend.mb import audit
    monkeypatch.setattr(audit, "PATH", tmp_path / "action_audit.jsonl")
    monkeypatch.setattr(main, "MODE", "hw")
    monkeypatch.delenv("MACDIAG_ENABLE_WRITES", raising=False)

    status = client.get("/api/status").json()
    assert status["writes"]["enabled"] is False
    assert status["writes"]["environment"] == "MACDIAG_ENABLE_WRITES"

    dtc = client.post("/api/dtc/clear")
    apply = client.post("/api/coding/apply", json={"domain": "any", "coding_hex": "AABB"})
    coding = client.post("/api/coding/write", json={"did": 0x0110, "value_hex": "AABB"})

    assert dtc.status_code == 403
    assert apply.status_code == 403
    assert coding.status_code == 403
    assert dtc.json()["operation"] == "dtc_clear"
    assert apply.json()["operation"] == "coding_apply"
    assert coding.json()["operation"] == "coding_write"
    events = client.get("/api/audit/actions").json()["entries"]
    assert [(event["operation"], event["outcome"]) for event in events] == [
        ("coding_write", "blocked"),
        ("coding_apply", "blocked"),
        ("dtc_clear", "blocked"),
    ]


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
    modules = client.get("/api/modules")
    assert modules.status_code == 200
    assert modules.json()["profile"]["id"] == "w221-x164"
    assert modules.json()["profile"]["module_count"] > 0


def test_packaged_profile_can_be_listed_and_selected_while_disconnected(client):
    client.post("/api/disconnect")
    listed = client.get("/api/profiles")
    assert listed.status_code == 200
    assert any(p["id"] == "w221-x164" for p in listed.json()["profiles"])

    selected = client.post("/api/profile", params={"name": "w221-x164"})
    assert selected.status_code == 200
    assert selected.json()["profile"]["id"] == "w221-x164"

    client.post("/api/connect")
    blocked = client.post("/api/profile", params={"name": "w221-x164"})
    assert blocked.status_code == 409


def test_gateway_modules_are_source_of_truth(client):
    client.post("/api/connect")
    r = client.get("/api/gateway/info")
    assert r.status_code == 200
    body = r.json()
    modules = body.get("modules") or []
    assert modules, body
    assert body["gateway_raw"]["can_ist_310800"].startswith("7108")
    assert body["gateway_raw"]["can_soll_310700"].startswith("7107")
    assert {s["service"] for s in body["decoded_sources"]} >= {"310800", "310700"}
    names = {m["ecu"] for m in modules}
    assert {"PTS164", "KI164"} <= names
    actual_names = {e["name"] for e in body["can_ist"] if e["present"]}
    assert {"EZS164", "SAMV164", "PTS164", "KI164"} <= actual_names
    assert "EZS164" in body["can_compare"]["actual_only"]
    assert "WSS" in body["can_compare"]["configured_only"]
    assert all(m["source"] == "gateway" for m in modules)
    assert all("configured" in m for m in modules)


def test_scan_accepts_explicit_gateway_modules(client):
    client.post("/api/connect")
    r = client.get("/api/vehicle/scan", params={"modules": "PTS164,KI164"})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "gateway"
    assert [m["ecu"] for m in body["modules"]] == ["PTS164", "KI164"]


def test_unknown_module_does_not_fall_back_to_engine(client):
    client.post("/api/connect")
    r = client.get("/api/dtc", params={"module": "NO_SUCH_ECU"})
    assert r.status_code == 404
    assert "unknown module" in r.json()["detail"]
