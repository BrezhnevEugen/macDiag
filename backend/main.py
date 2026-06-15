"""
macDiag backend - FastAPI app exposing the J2534/UDS layer to the web UI.

Run:
    pip install -r requirements.txt
    python -m uvicorn backend.main:app --reload --port 8000
    open http://localhost:8000

Switch to real hardware with env var:  MACDIAG_MODE=hw
Optionally:                            MACDIAG_DRIVER=/path/to/op20pt32.dll
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .j2534 import (make_passthru, PassThruError, UDSClient, UDSError,
                    KWPClient, KWPError, ISO15765)
from .j2534.passthru import OBD_PHYS_TX_BASE, OBD_PHYS_RX_BASE, OBD_FUNCTIONAL_TX
from .mb import (MODULES, MODULES_BY_ID, CATALOG, modules_for, catalog_list,
                 DEFAULT_DASHBOARD, DIDS, decode_pid, describe_dtc)
from .mb.seedkey import get_algo

DiagError = (UDSError, KWPError)

MODE = os.environ.get("MACDIAG_MODE", "sim")  # 'sim' or 'hw'
DRIVER = os.environ.get("MACDIAG_DRIVER")

app = FastAPI(title="macDiag", version="0.1.0")


# ---------------------------------------------------------------------------
# Connection state (single active session - this is a bench tool, not a server)
# ---------------------------------------------------------------------------
class Session:
    """Holds the open J2534 device and one ISO15765 channel per CAN baudrate.

    W221/X164 are multi-bus: powertrain/chassis ECUs sit on 500k, many body
    ECUs on the 83.3k interior CAN (reached via the central gateway). Each
    baudrate needs its own channel, so channels are opened lazily and cached.
    """

    def __init__(self):
        self.bus = None
        self.channel = None          # single active ISO15765 channel
        self.baudrate = None
        self.connected = False
        self._vbatt = None           # cached battery voltage (read at connect)
        # Guards connect/disconnect/reset transitions (per-request IO is
        # serialized separately by bus.io_lock inside the UDS/KWP clients).
        self._lock = threading.RLock()

    def connect(self):
        with self._lock:
            self._connect_locked()

    def _connect_locked(self):
        if self.connected:
            return
        self.bus = make_passthru(MODE, DRIVER)
        self.bus.open()
        try:
            self.channel = self.bus.connect(ISO15765, 500000)
        except PassThruError as e:
            # ERR_CHANNEL_IN_USE (20): a stale channel from a previous run.
            # Reopen the device once to reset it.
            if "status 20" in str(e):
                try:
                    self.bus.close()
                    self.bus.open()
                    self.channel = self.bus.connect(ISO15765, 500000)
                except PassThruError:
                    raise PassThruError(
                        "канал занят (ERR_CHANNEL_IN_USE). Отключи и снова воткни "
                        "Openport по USB (сброс), затем «Подключить».")
            else:
                raise
        self.baudrate = 500000
        self.connected = True
        self._vbatt = self._read_vbatt()  # read once; status poll uses the cache

    def _channel_for(self, baudrate: int = 500000) -> int:
        """Always the single 500k diagnostic channel.

        On W221/X164 the OBD socket exposes ONE diagnostic CAN at 500 kbit/s.
        Body ECUs that physically sit on the 83.3k interior bus are reached
        THROUGH the central gateway by their CAN id - you do NOT switch the
        adapter to 83.3k (there's no 83.3k bus on the OBD pins; that just times
        out). So the per-module 'baudrate' is informational; addressing is by id.
        """
        if not self.connected:
            self.connect()
        return self.channel

    def disconnect(self):
        with self._lock:
            if self.bus and self.connected:
                try:
                    if self.channel is not None:
                        self.bus.disconnect(self.channel)
                    self.bus.close()
                finally:
                    self.channel = None
                    self.baudrate = None
                    self.connected = False

    def reset_channel(self):
        """Reopen the 500k channel — the only reliable way to clear accumulated
        flow-control filters on the Tactrix libusb build (it ignores both
        StopMsgFilter and the CLEAR_MSG_FILTERS ioctl, so filters pile up and
        StartMsgFilter eventually returns ERR_EXCEEDED_LIMIT / status 12)."""
        with self._lock, self.bus.io_lock:   # don't reconnect mid-request
            try:
                if self.channel is not None:
                    self.bus.disconnect(self.channel)
            except Exception:  # noqa: BLE001
                pass
            self.channel = self.bus.connect(ISO15765, 500000)
            time.sleep(0.02)  # let the freshly reopened channel settle before IO

    def client(self, tx: int, rx: int, protocol: str = "uds",
               baudrate: int = 500000):
        # No per-call channel reconnect: on the Tactrix libusb build repeated
        # PassThruConnect destabilises the device (status 9). One filter is kept
        # active at a time via StopMsgFilter (see passthru.set_filters); the scan
        # does a single reset_channel() up front.
        if not self.connected:
            self.connect()
        cls = KWPClient if protocol == "kwp" else UDSClient
        return cls(self.bus, self._channel_for(baudrate or 500000), tx, rx)

    def _read_vbatt(self) -> float | None:
        try:
            return self.bus.read_vbatt(self.channel)
        except Exception:  # noqa: BLE001
            try:
                return self.bus.read_vbatt()
            except Exception:  # noqa: BLE001
                return None

    def voltage(self) -> float | None:
        """Cached battery voltage. Read once at connect — NOT on every status
        poll, which otherwise spams READ_VBATT and fights the diagnostic IO."""
        return self._vbatt if self.connected else None

    def adapter_info(self) -> dict | None:
        """Adapter versions read from the device (works without a car)."""
        if not self.connected:
            return None
        try:
            return self.bus.read_version()
        except Exception:  # noqa: BLE001
            return None

    @property
    def driver_path(self):
        return getattr(self.bus, "driver_path", None)


session = Session()


def _backup_current(client, module: str | None, did: int,
                    domain: str | None = None, new_hex: str = "") -> dict:
    """Read and journal the current value of the identifier we are about to
    overwrite (see mb/backup.py). Never blocks the write: a failed read is
    recorded in the journal entry instead of raising."""
    from .mb import backup
    try:
        old = client.read_did(did).hex().upper()
        err = None
    except Exception as e:  # noqa: BLE001 — any read failure must not stop us
        old, err = None, str(e)
    return backup.record(mode=MODE, module=module, ecu=_ecu_name_for(module),
                         did=f"0x{did:X}", domain=domain,
                         old=old, read_error=err, new=new_hex.upper())


def _parse_hex(s: str, field: str = "value") -> bytes:
    """User-supplied hex string -> bytes, or a clean 400 instead of a 500."""
    try:
        return bytes.fromhex((s or "").replace(" ", ""))
    except ValueError:
        raise HTTPException(status_code=400,
                            detail=f"invalid {field}: not a hex string")


def _module_client(module_id: str | None):
    """Resolve a client for any module: a curated quick-pick id, OR any ECU name
    from the unified database (any chassis), OR fall back to generic OBD."""
    from .mb import ecu_db
    # 1. curated quick-pick (e.g. "ezs", "esp")
    if module_id and module_id in MODULES_BY_ID:
        m = MODULES_BY_ID[module_id]
        return session.client(m["tx"], m["rx"], m["protocol"],
                              m.get("baudrate") or 500000)
    # 2. any ECU in the database, addressed by its real CBF CAN ids
    if module_id:
        e = ecu_db.get(module_id)
        if not e:
            e = CATALOG.get(module_id)
        if e and e.get("can_request"):
            return session.client(e["can_request"], e["can_response"],
                                  e.get("protocol") or "uds",
                                  e.get("baudrate") or 500000)
        raise HTTPException(status_code=404, detail=f"unknown module: {module_id}")
    # 3. default: engine ECU / generic OBD physical address (UDS)
    return session.client(OBD_PHYS_TX_BASE, OBD_PHYS_RX_BASE, "uds")


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------
@app.on_event("shutdown")
def _cleanup():
    # Close the adapter cleanly on Ctrl+C so the channel isn't left in use.
    try:
        session.disconnect()
    except Exception:  # noqa: BLE001
        pass


@app.get("/api/status")
def status():
    return {"mode": MODE, "connected": session.connected,
            "driver": session.driver_path or DRIVER,
            "voltage": session.voltage() if session.connected else None}


@app.get("/api/log")
def get_log():
    """Recent diagnostic traffic (requests/responses/errors) for the debug panel."""
    from .j2534.passthru import TRACE
    return {"entries": list(TRACE)}


@app.post("/api/log/clear")
def clear_log():
    from .j2534.passthru import TRACE
    TRACE.clear()
    return {"ok": True}


@app.post("/api/mode")
def set_mode(mode: str):
    """Switch between the simulator (test data) and real hardware at runtime."""
    global MODE
    if mode not in ("sim", "hw"):
        return JSONResponse({"error": "mode должен быть sim или hw"}, status_code=400)
    session.disconnect()
    MODE = mode
    try:
        session.connect()
        return {"mode": MODE, "connected": True, "voltage": session.voltage()}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"mode": MODE, "connected": False, "error": str(e)},
                            status_code=400)


@app.post("/api/connect")
def connect():
    """Open the adapter and verify the link by reading battery voltage."""
    try:
        session.connect()
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"connected": False, "mode": MODE, "error": str(e)},
                            status_code=400)
    v = session.voltage()
    info = session.adapter_info()
    # A plausible voltage means the cable is on the car; ~0 just means it's on
    # USB only (bench). The adapter info already proves the Mac<->cable link.
    warn = None
    if MODE == "hw" and (v is None or v < 6):
        warn = (f"кабель открыт (адаптер отвечает: fw={info.get('firmware') if info else '?'}), "
                f"но напряжение = {v} В — это значит OBD не подключён к машине "
                "(на столе это норма). Воткни в OBD для реальной работы.")
    return {"connected": True, "mode": MODE, "driver": session.driver_path,
            "voltage": v, "adapter": info, "warning": warn}


@app.get("/api/adapter/info")
def adapter_info():
    """Adapter API/DLL/firmware versions - works without a car."""
    if not session.connected:
        try:
            session.connect()
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"error": str(e)}, status_code=400)
    return {"mode": MODE, "driver": session.driver_path,
            "adapter": session.adapter_info(), "voltage": session.voltage()}


@app.post("/api/disconnect")
def disconnect():
    session.disconnect()
    return {"connected": False}


@app.get("/api/vehicle/info")
def vehicle_info():
    """VIN (read from the car) + light decode + adapter/voltage for the dashboard."""
    from .mb import vehicle
    out = {"mode": MODE, "connected": session.connected,
           "voltage": session.voltage() if session.connected else None,
           "adapter": session.adapter_info() if session.connected else None,
           "vin": None, "decode": None}
    if not session.connected:
        return out
    # VIN: OBD functional broadcast (canonical mode 09) first, then engine
    # physical, then EZS / gateway. Reset the channel before each (clean filter).
    vin_detail = ""
    attempts = [
        ("obd", lambda: session.client(OBD_FUNCTIONAL_TX, OBD_PHYS_RX_BASE, "uds")),
        ("engine", lambda: _module_client(None)),
        ("ezs", lambda: _module_client("ezs")),
        ("zgw", lambda: _module_client("zgw")),
    ]
    for src, make in attempts:
        try:
            vin, vin_detail = vehicle.read_vin(make())
        except Exception as e:  # noqa: BLE001
            vin, vin_detail = None, str(e)
        if vin:
            out["vin"] = vin
            out["decode"] = vehicle.decode_vin(vin)
            out["vin_source"] = src
            break
    if not out["vin"]:
        out["vin_detail"] = vin_detail
    return out


def _dedup_by_tx(mods: list) -> list:
    """One physical ECU per CAN address — collapse curated entries that share a
    tx (e.g. petrol ME-SFI and diesel CDI both at 0x7E0)."""
    seen, out = set(), []
    for m in mods:
        tx = m.get("tx")
        if tx is None:
            out.append(m)
            continue
        if tx in seen:
            continue
        seen.add(tx)
        out.append(m)
    return out


def _present_value(value) -> bool:
    """Gateway coding values are German strings from the ZGW CBF.

    Only explicit installed/active values count as present. Unknown text stays
    false; we do not infer equipment from curated module lists.
    """
    s = str(value or "").strip().lower()
    if not s or "nicht" in s:
        return False
    return any(word in s for word in ("vorhanden", "aktiv", "erlaubt", "present", "installed"))


def _decode_can_b_bitmap(coding: bytes, source: str) -> list[dict]:
    """Decode ZGW164 CAN-B bitmaps through the CBF's CAN-B SG bit map.

    310700 is the configured/Soll 16-byte variant coding. 310800 is an 8-byte
    actual/Ist snapshot, but ZGW164 uses the same SG bit positions for the
    visible CAN-B ECUs in this range.
    """
    from .mb import varcoding
    dec = varcoding.decode("ZGW164", "VCD_CAN_B_Soll_Konfiguration", coding)
    out = []
    for f in (dec or {}).get("fragments", []):
        name = f.get("name")
        if not name:
            continue
        out.append({"name": name, "value": f.get("current"),
                    "present": _present_value(f.get("current")),
                    "bit": f.get("byte_bit_pos"), "source": source})
    return out


def _gateway_module(name: str, present: bool = True) -> dict:
    """One ECU exactly as reported by the gateway, enriched only by exact CBF/DB
    matches. If no CAN ids are known, keep it visible but not probeable."""
    from .mb import ecu_db
    ecu = (name or "").strip()
    curated = next((m for m in MODULES if m.get("cbf") == ecu or m.get("id") == ecu), None)
    meta = ecu_db.get(ecu) or CATALOG.get(ecu) or {}
    label = curated.get("name") if curated else ecu
    tx = meta.get("can_request")
    rx = meta.get("can_response")
    protocol = meta.get("protocol") or (curated or {}).get("protocol") or "uds"
    if tx is None and curated and curated.get("id_source") == "cbf":
        tx, rx = curated.get("tx"), curated.get("rx")
        protocol = curated.get("protocol", protocol)
    return {
        "id": ecu if meta or not curated else curated["id"],
        "ecu": ecu,
        "cbf": ecu,
        "name": label,
        "protocol": protocol,
        "tx": tx,
        "rx": rx,
        "baudrate": meta.get("baudrate") or (curated or {}).get("baudrate"),
        "chassis": meta.get("chassis") or (curated or {}).get("chassis", []),
        "source": "gateway",
        "configured": bool(present),
        "address_known": tx is not None and rx is not None,
    }


def _scan_targets(chassis: str | None = None, modules: str | None = None) -> list[dict]:
    if modules:
        names = [m.strip() for m in modules.split(",") if m.strip()]
        return _dedup_by_tx([_gateway_module(name) for name in names])
    return _dedup_by_tx(modules_for(chassis))


def _scan_module(m: dict) -> dict:
    """Probe one ECU: state = online (read DTCs) | present (answered, can't read)
    | silent (no response) | adapter_error (J2534 failure). One flow-control
    filter is kept active via StopMsgFilter; no channel reconnect here (repeated
    PassThruConnect destabilises the Tactrix build)."""
    state, n, detail = "silent", 0, ""
    if not m.get("address_known", m.get("tx") is not None and m.get("rx") is not None):
        return {"id": m["id"], "ecu": m.get("ecu") or m.get("cbf"), "name": m["name"],
                "cbf": m.get("cbf"), "protocol": m.get("protocol"), "tx": m.get("tx"),
                "state": "configured", "online": False, "dtc": 0,
                "detail": "reported by gateway, but no CAN id found in CBF catalog",
                "source": m.get("source"), "address_known": False}
    try:
        cl = _module_client(m["id"])
        if not cl.ping():            # fast presence probe (avoids long timeouts)
            state, n, detail = "silent", 0, ""
        else:
            res = cl.read_dtcs()
            detail = res.get("detail", "")
            state, n = ("online", len(res["dtcs"])) if res["readable"] else ("present", 0)
    except Exception as e:  # noqa: BLE001 - adapter/transport error
        state, n, detail = "adapter_error", 0, str(e)
    return {"id": m["id"], "ecu": m.get("ecu") or m.get("cbf"), "name": m["name"],
            "cbf": m.get("cbf"), "protocol": m["protocol"], "tx": m.get("tx"),
            "state": state, "online": state in ("online", "present"),
            "dtc": n, "detail": detail, "source": m.get("source"),
            "address_known": m.get("address_known", True)}


@app.get("/api/vehicle/scan")
def vehicle_scan(chassis: str | None = None, modules: str | None = None):
    """Scan either explicit gateway ECU names, or the curated chassis fallback."""
    if not session.connected:
        return JSONResponse({"error": "не подключено"}, status_code=400)
    try:
        session.reset_channel()   # one clean channel for the whole scan
    except Exception:  # noqa: BLE001
        pass
    mods = _scan_targets(chassis, modules)
    rows = [_scan_module(m) for m in mods]
    return {"chassis": chassis, "source": "gateway" if modules else "curated",
            "modules": rows,
            "online": sum(1 for r in rows if r["online"]),
            "total_dtc": sum(r["dtc"] for r in rows if r["state"] == "online"),
            "adapter_error": any(r["state"] == "adapter_error" for r in rows),
            "protocols": sorted({(m.get("protocol") or "").upper() for m in mods
                                 if m.get("address_known", True)})}


@app.get("/api/vehicle/scan/stream")
def vehicle_scan_stream(chassis: str | None = None, modules: str | None = None):
    """Same scan, streamed via Server-Sent Events so each ECU card appears as
    soon as it's probed (start -> module… -> done)."""
    if not session.connected:
        return JSONResponse({"error": "не подключено"}, status_code=400)
    import json as _json
    from fastapi.responses import StreamingResponse
    mods = _scan_targets(chassis, modules)
    try:
        session.reset_channel()   # one clean channel for the whole scan
    except Exception:  # noqa: BLE001
        pass

    def gen():
        def sse(obj):
            return f"data: {_json.dumps(obj, ensure_ascii=False)}\n\n"
        online = total = 0
        adapter_error = False
        yield sse({"type": "start", "count": len(mods),
                   "source": "gateway" if modules else "curated",
                   "protocols": sorted({(m.get("protocol") or "").upper() for m in mods
                                        if m.get("address_known", True)})})
        for m in mods:
            row = _scan_module(m)
            if row["online"]:
                online += 1
            if row["state"] == "online":
                total += row["dtc"]
            if row["state"] == "adapter_error":
                adapter_error = True
            yield sse({"type": "module", "module": row,
                       "online": online, "total_dtc": total})
        yield sse({"type": "done", "online": online, "total_dtc": total,
                   "adapter_error": adapter_error})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store",
                                      "X-Accel-Buffering": "no"})


# Mercedes-proprietary READ flow per target: open the extended diagnostic
# session (MB uses 0x10 0x92, NOT 0x10 0x03), then read with the real CBF jobs.
# READ-ONLY: never the 0x3B/0x28/0x29/flash write jobs.
_GW = {
    "zgw": {"session": "1092", "reqs": [
        ("CAN-Ist config (установлено)", "310800"),
        ("CAN-Soll config (должно быть)", "310700"),
        ("CAN error status", "310500"),
        ("variant code 38B", "300101"),
        ("ZGW system state", "2300100D01"),
        ("version (OS)", "21E0"),
    ]},
    "ezs": {"session": "1092", "reqs": [
        ("VIN 1A90", "1A90"),
        ("VIN/FIN 2105", "2105"),
        ("version", "21E0"),
    ]},
    "_default": {"session": "1092", "reqs": [
        ("VIN 1A90", "1A90"),
        ("version 21E0", "21E0"),
        ("variant code 300101", "300101"),
    ]},
}


@app.get("/api/gateway/probe")
def gateway_probe(target: str = "zgw,ezs"):
    """Query the gateway/EZS the Mercedes way: open the extended diagnostic
    session (0x10 0x92) first, THEN read the real CBF jobs (CAN configuration =
    installed ECUs, variant coding, versions, VIN). Read-only; every exchange
    goes to the trace log so the equipment list is visible."""
    if not session.connected:
        return JSONResponse({"error": "не подключено"}, status_code=400)
    try:
        session.reset_channel()
    except Exception:  # noqa: BLE001
        pass
    out = []
    for tid in [t.strip() for t in target.split(",") if t.strip()]:
        try:
            cl = _module_client(tid)
        except Exception as e:  # noqa: BLE001
            out.append({"target": tid, "error": str(e)})
            continue
        spec = _GW.get(tid, _GW["_default"])
        results = []
        reqs = [("session ext", spec["session"])] + spec["reqs"]
        for label, hexreq in reqs:
            try:
                resp = cl.raw_request(bytes.fromhex(hexreq))
                results.append({"label": label, "req": hexreq.upper(),
                                "resp": resp.hex().upper()})
            except Exception as e:  # noqa: BLE001
                results.append({"label": label, "req": hexreq.upper(), "error": str(e)})
        mod = MODULES_BY_ID.get(tid, {})
        out.append({"target": tid, "name": mod.get("name", tid),
                    "tx": mod.get("tx"), "protocol": getattr(cl, "protocol", "uds"),
                    "results": results})
    return {"probed": out}


@app.get("/api/gateway/info")
def gateway_info():
    """Read the car's configuration from the central gateway and DECODE it:
    engine / chassis / body + equipment options (global variant code) and the
    configured ECU list (CAN-B config). Opens session 0x1092 first (MB)."""
    if not session.connected:
        return JSONResponse({"error": "не подключено"}, status_code=400)
    from .mb import varcoding
    out = {"engine": None, "chassis": None, "body": None,
           "options": [], "ecus": [], "can_ist": [], "modules": [],
           "gateway_raw": {}, "decoded_sources": []}
    try:
        session.reset_channel()
        cl = _module_client("zgw")
        cl.raw_request(bytes.fromhex("1092"))                 # extended session
        # global variant code -> equipment / engine
        try:
            resp = cl.raw_request(bytes.fromhex("300101"))
            dec = varcoding.decode("ZGW164", "VCD_Global_Code", resp[3:])  # strip 70 01 01
            for f in (dec or {}).get("fragments", []):
                nm, cur = f.get("name", ""), f.get("current")
                if cur is None:
                    continue
                if nm.startswith("Motor"):
                    out["engine"] = cur
                elif nm.startswith("Baureihe"):
                    out["chassis"] = cur
                elif nm.startswith("Karosserie"):
                    out["body"] = cur
                out["options"].append({"name": nm, "value": cur})
        except Exception as e:  # noqa: BLE001
            out["code_error"] = str(e)
        # CAN-Ist is a real gateway snapshot too. It is shorter than CAN-Soll,
        # but the ZGW164 CBF uses the same CAN-B SG bit positions for ECU names.
        try:
            resp = cl.raw_request(bytes.fromhex("310800"))
            out["gateway_raw"]["can_ist_310800"] = resp.hex().upper()
            out["can_ist"] = _decode_can_b_bitmap(resp[2:], "310800")
            out["decoded_sources"].append(
                {"service": "310800", "domain": "VCD_CAN_B_Soll_Konfiguration",
                 "label": "CAN-B Ist Konfiguration"})
        except Exception as e:  # noqa: BLE001
            out["can_ist_error"] = str(e)
        # CAN-B configured ECU list
        try:
            resp = cl.raw_request(bytes.fromhex("310700"))
            out["gateway_raw"]["can_soll_310700"] = resp.hex().upper()
            out["ecus"] = _decode_can_b_bitmap(resp[2:], "310700")
            out["modules"] = [_gateway_module(e["name"], e["present"])
                              for e in out["ecus"] if e["present"] and e.get("name")]
            out["decoded_sources"].append(
                {"service": "310700", "domain": "VCD_CAN_B_Soll_Konfiguration",
                 "label": "CAN-B Soll Konfiguration"})
        except Exception as e:  # noqa: BLE001
            out["ecu_error"] = str(e)
        actual = {e["name"] for e in out["can_ist"] if e.get("present")}
        configured = {e["name"] for e in out["ecus"] if e.get("present")}
        if actual or configured:
            out["can_compare"] = {
                "actual": sorted(actual),
                "configured": sorted(configured),
                "both": sorted(actual & configured),
                "actual_only": sorted(actual - configured),
                "configured_only": sorted(configured - actual),
            }
        # chassis token for the app (e.g. "BR 164" + body "X…" -> "X164")
        import re as _re
        num = _re.search(r"\d{3}", out.get("chassis") or "")
        body0 = (out.get("body") or "").strip()[:1].upper()
        if num and body0 in "WXCRSAVT":
            out["chassis_token"] = body0 + num.group(0)
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)
    return out


@app.get("/api/modules")
def get_modules(chassis: str | None = None):
    return {"modules": modules_for(chassis)}


@app.get("/api/measure/ecus")
def measure_ecus():
    """ECUs that have measurement/service groups (.vsg)."""
    from .mb import measurements
    return {"available": measurements.available(), "ecus": measurements.ecus_with_groups()}


@app.get("/api/measure/groups")
def measure_groups(module: str | None = None, lang: str = "ru"):
    """Measurement dashboards + service procedures for an ECU (from .vsg)."""
    from .mb import measurements
    ecu = _ecu_name_for(module) or module
    return measurements.groups_for(ecu or "", lang)


@app.get("/api/measure/group")
def measure_group(path: str, lang: str = "ru"):
    from .mb import measurements
    g = measurements.get_group(path, lang)
    if not g:
        return JSONResponse({"error": "group not found"}, status_code=404)
    return g


@app.get("/api/measure/read")
def measure_read(path: str, module: str | None = None):
    """Current values for a measurement group's parameters.
    On hardware, read raw values via the group's ECU; in sim, synthesize."""
    from .mb import measurements
    hw = MODE == "hw"
    client = None
    if hw and session.connected:
        ecu = measurements.group_ecu(path)
        if ecu:
            try:
                client = _module_client(ecu)
            except Exception:  # noqa: BLE001
                client = None
    return {"path": path, "values": measurements.read_values(path, hw=hw, client=client)}


@app.get("/api/catalog")
def get_catalog(chassis: str | None = None, q: str | None = None,
                protocol: str | None = None, limit: int = 500):
    """Pull ECUs from the unified Vediamo CBF database on demand."""
    ecus = catalog_list(chassis=chassis, q=q, protocol=protocol, limit=limit)
    return {"ecus": ecus, "count": len(ecus)}


@app.get("/api/db/stats")
def db_stats():
    from .mb import ecu_db
    return ecu_db.stats()


# ---------------------------------------------------------------------------
# Flash (reprogramming) - SCAFFOLD, read-only. Writing is a future iteration.
# ---------------------------------------------------------------------------
@app.get("/api/flash/library")
def flash_library(q: str | None = None, chassis: str | None = None):
    """Catalogue of CFF flash images in the data volume (read-only)."""
    from .mb import flash
    return {"available": flash.available(),
            "images": flash.library(q=q, chassis=chassis)}


@app.get("/api/flash/cff/{name}")
def flash_cff(name: str):
    from .mb import flash
    info = flash.cff_info(name)
    if not info:
        return JSONResponse({"error": "not found"}, status_code=404)
    return info


@app.get("/api/flash/versions")
def flash_versions(module: str | None = None):
    """Read SW/HW version identifiers from a connected ECU (read-only)."""
    from .mb import flash
    try:
        return {"module": module, "versions": flash.read_versions(_module_client(module))}
    except DiagError as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.post("/api/flash/program")
def flash_program():
    """Writing firmware is intentionally not implemented (future iteration)."""
    return JSONResponse(
        {"error": "flashing not implemented - read-only scaffold (iteration 2)"},
        status_code=501)


@app.get("/api/catalog/{name}")
def get_ecu(name: str):
    from .mb import ecu_db
    e = ecu_db.get(name)
    if not e:
        return JSONResponse({"error": "not found"}, status_code=404)
    return e


@app.get("/api/dtc")
def read_dtc(module: str | None = None, lang: str = "ru"):
    try:
        client = _module_client(module)
        res = client.read_dtcs()
        dtcs = res["dtcs"]
        for d in dtcs:
            d["description"] = describe_dtc(d["code"], lang)
        if res["readable"]:
            status = "ok"          # answered; dtcs may be empty = no faults
        elif res["responded"]:
            status = "present"     # on the bus but won't report DTCs (NRC)
        else:
            status = "no_response"  # silent / not fitted / wrong address
        return {"module": module, "status": status, "responded": res["responded"],
                "readable": res["readable"], "via": res.get("via"),
                "detail": res.get("detail"), "dtcs": dtcs}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 - adapter/transport error (e.g. status 12)
        return {"module": module, "status": "adapter_error", "responded": False,
                "readable": False, "detail": str(e), "dtcs": []}


@app.post("/api/dtc/clear")
def clear_dtc(module: str | None = None):
    try:
        client = _module_client(module)
        client.clear_dtcs()
        return {"cleared": True, "module": module}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/diag/context")
def diag_context(code: str, module: str | None = None, lang: str = "ru"):
    """DAS-style drill-down for a fault: causes, check-list, linked groups,
    schematics + any real WIS/StarFinder pictures."""
    from .mb import diag, media, measurements
    mod = MODULES_BY_ID.get(module) if module else None
    ctx = diag.context(code, lang, mod)
    # linked measurement / service groups for the originating ECU
    ecu = _ecu_name_for(module) or module
    if ecu:
        try:
            g = measurements.groups_for(ecu, lang)
            ctx["linked"] = {"measurement": g["measurement"], "service": g["service"]}
        except Exception:  # noqa: BLE001
            ctx["linked"] = {"measurement": [], "service": []}
    # real pictures from configured providers (appended after generated schematics)
    before = len(ctx["media"])
    try:
        ctx["media"] += media.lookup(code, mod, lang)
    except Exception:  # noqa: BLE001
        pass
    # tell the UI why there may be no real pinout, so the panel can explain
    sf = next((p for p in media.status() if p["provider"] == "starfinder"), {})
    ctx["starfinder"] = {
        "configured": bool(sf.get("configured")),
        "archives": len(sf.get("archives") or []),
        "images": len(ctx["media"]) - before,
        "module_selected": mod is not None,
        "mapped": bool(mod and media.COMPONENT_CODE.get(str(mod.get("id", "")).lower())),
    }
    try:
        ctx["component"] = media.component_for(mod)
    except Exception:  # noqa: BLE001
        ctx["component"] = {}
    return ctx


@app.get("/api/diag/sf/{series}/{inner:path}")
def diag_sf_file(series: str, inner: str):
    """Serve a StarFinder file (description page, image, css) from a chassis
    archive — used to open sysinfo description docs."""
    from fastapi.responses import Response
    from .mb import media
    out = media.serve_path(series, inner)
    if not out:
        return JSONResponse({"error": "not found"}, status_code=404)
    data, mime = out
    return Response(content=data, media_type=mime, headers={"Cache-Control": "no-store"})


@app.get("/api/diag/schematic")
def diag_schematic(type: str = "can_topology", module: str | None = None, lang: str = "ru"):
    """Generated SVG schematic (image/svg+xml)."""
    from fastapi.responses import Response
    from .mb import schematics
    if type == "cylinder_layout":
        svg = schematics.cylinder_layout(MODULES_BY_ID.get(module), lang=lang)
    else:
        svg = schematics.can_topology(MODULES, highlight_id=module, lang=lang)
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/api/diag/providers")
def diag_providers():
    """Which external picture providers (WIS / StarFinder) are configured."""
    from .mb import media
    return {"providers": media.status()}


@app.get("/api/diag/media/raw")
def diag_media_raw(token: str):
    """Stream a real provider image (from a StarFinder .asar or a plain file)."""
    from fastapi.responses import Response
    from .mb import media
    out = media.read_media(token)
    if not out:
        return JSONResponse({"error": "not found"}, status_code=404)
    data, mime = out
    # no-store so a previously cached (broken) render never sticks
    return Response(content=data, media_type=mime,
                    headers={"Cache-Control": "no-store"})


@app.get("/api/identify")
def identify(module: str | None = None):
    """Read identifying DIDs (VIN, part number, SW version)."""
    out = {}
    try:
        client = _module_client(module)
        for did, label in DIDS.items():
            try:
                raw = client.read_did(did)
                out[label] = raw.decode("ascii", "replace").strip()
            except DiagError:
                out[label] = None
        return {"module": module, "info": out}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=502)


def _ecu_name_for(module: str | None) -> str | None:
    """CBF/ECU name used to look up the real seed-key definition."""
    if module and module in MODULES_BY_ID:
        return MODULES_BY_ID[module].get("cbf")
    return module


def _security_unlock(client, module: str | None, level: int = 1) -> dict:
    """Run the 0x27 seed/key exchange at a given *logical* access level.

    UDS sub-functions: requestSeed = 2*level-1 (odd), sendKey = 2*level (even).
    Prefers a REAL algorithm from the UnlockECU database (ported providers in
    mb/unlock.py) selected by ECU name AND level. Falls back to the simulator
    toy algorithm so the demo keeps working without the database.
    """
    from .mb import unlock
    seed_sf = 2 * level - 1
    key_sf = 2 * level
    seed = client.request_seed(seed_sf)
    if all(b == 0 for b in seed):
        return {"unlocked": True, "note": "already unlocked (zero seed)",
                "level": level}

    ecu_name = _ecu_name_for(module)
    key = info = None
    if ecu_name:
        key, info = unlock.generate_key(ecu_name, seed, level)

    used = "unlockecu"
    if key is None:                       # fall back to the simulator algorithm
        algo = get_algo(module)
        if algo is None:
            raise UDSError(
                f"no seed-key for '{ecu_name}' level {level}: "
                f"{info or 'no definition'}")
        key = algo(seed, level)
        used = "sim"

    client.send_key(key, key_sf)
    return {"unlocked": True, "seed": seed.hex().upper(), "level": level,
            "seed_subfn": seed_sf, "key_subfn": key_sf, "algo": used,
            "provider": (info or {}).get("provider")
            if isinstance(info, dict) else None}


@app.get("/api/security/info")
def security_info(module: str | None = None, level: int = 1):
    """Which seed-key provider/definition applies to this ECU."""
    from .mb import unlock
    ecu_name = _ecu_name_for(module)
    d = unlock.find_definition(ecu_name, level) if ecu_name else None
    return {
        "ecu": ecu_name,
        "db_available": unlock.available(),
        "provider": d.get("Provider") if d else None,
        "seed_length": d.get("SeedLength") if d else None,
        "key_length": d.get("KeyLength") if d else None,
        "ported": bool(d and d.get("Provider") in unlock.PROVIDERS),
        "levels": unlock.levels_for(ecu_name) if ecu_name else [],
    }


@app.post("/api/security/unlock")
def security_unlock(module: str | None = None, level: int = 1):
    try:
        client = _module_client(module)
        client.session(0x03 if client.protocol == "uds" else 0x85)
        return _security_unlock(client, module, level)
    except HTTPException:
        raise
    except DiagError as e:
        return JSONResponse({"unlocked": False, "error": str(e)}, status_code=502)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"unlocked": False, "error": str(e)}, status_code=500)


@app.get("/api/coding/domains")
def coding_domains(module: str | None = None):
    """VC domains for an ECU (variant coding), parsed from its CBF."""
    from .mb import varcoding
    ecu = _ecu_name_for(module) or module
    return {"ecu": ecu, "available": varcoding.available(),
            "domains": varcoding.list_domains(ecu) if ecu else []}


@app.get("/api/coding/read")
def coding_read(module: str | None = None, domain: str = "", lid: str = ""):
    """Read the live coding string for a VC domain from the ECU, then decode it.

    `lid` is the read identifier (hex) the ECU uses for this domain's
    RVC_..._Lesen service (1 byte for KWP local id, 2 bytes for UDS DID). It's
    not auto-extractable from the CBF service blob - find it in Vediamo or via a
    trace. The decode/encode itself is fully automatic.
    """
    from .mb import varcoding
    ecu = _ecu_name_for(module) or module
    meta = varcoding.domain_meta(ecu, domain)
    if not meta:
        return JSONResponse({"error": "domain/CBF not found"}, status_code=404)
    # LID is auto-extracted from the CBF service (read_lid); override only if given
    use_lid = lid or meta.get("read_lid")
    if not use_lid:
        return JSONResponse({"error": "no read identifier for this domain"},
                            status_code=400)
    try:
        client = _module_client(module)
        raw = client.read_did(int(use_lid, 16))
        size = meta["dump_size"]
        coding = (raw + bytes(size))[:size]          # pad/trim to dump size
        res = varcoding.decode(ecu, domain, coding)
        res["read_service"] = meta["read_service"]
        res["lid"] = use_lid
        return res
    except DiagError as e:
        return JSONResponse({"error": str(e)}, status_code=502)


class ApplyReq(BaseModel):
    module: str | None = None
    domain: str
    coding_hex: str
    lid: str | None = None          # auto from CBF if omitted
    unlock: bool = True
    level: int | None = None        # auto from service security level if omitted


@app.post("/api/coding/apply")
def coding_apply(req: ApplyReq):
    """Write an edited coding string back to the ECU (after Security Access)."""
    from .mb import varcoding
    ecu = _ecu_name_for(req.module) or req.module
    meta = varcoding.domain_meta(ecu, req.domain)
    if not meta:
        return JSONResponse({"error": "domain/CBF not found"}, status_code=404)
    use_lid = req.lid or meta.get("write_lid")
    if not use_lid:
        return JSONResponse({"error": "no write identifier for this domain"},
                            status_code=400)
    # level from the service's security level when present, else default 1
    sec_level = meta.get("write_sec_level")
    level = req.level if req.level is not None else (sec_level or 1)
    coding = _parse_hex(req.coding_hex, "coding_hex")   # validate before touching the ECU
    try:
        client = _module_client(req.module)
        client.session(0x03 if client.protocol == "uds" else 0x85)
        bkp = _backup_current(client, req.module, int(use_lid, 16),
                              domain=req.domain, new_hex=req.coding_hex)
        sec = _security_unlock(client, req.module, level) if req.unlock else None
        client.write_did(int(use_lid, 16), coding)
        return {"ok": True, "write_service": meta["write_service"],
                "lid": use_lid, "security": sec, "backup": bkp}
    except HTTPException:
        raise
    except DiagError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=502)


@app.get("/api/coding/backups")
def coding_backups(limit: int = 50):
    """Pre-write backup journal (newest first) — for manual rollback."""
    from .mb import backup
    return {"path": str(backup.PATH), "entries": backup.recent(limit)}


class DecodeReq(BaseModel):
    module: str | None = None
    domain: str
    coding_hex: str


@app.post("/api/coding/decode")
def coding_decode(req: DecodeReq):
    """Decode a coding string into named options for a VC domain."""
    from .mb import varcoding
    ecu = _ecu_name_for(req.module) or req.module
    res = varcoding.decode(ecu, req.domain, _parse_hex(req.coding_hex, "coding_hex"))
    if res is None:
        return JSONResponse({"error": "domain/CBF not found"}, status_code=404)
    return res


class EncodeReq(BaseModel):
    module: str | None = None
    domain: str
    coding_hex: str
    fragment: str
    option: str


@app.post("/api/coding/encode")
def coding_encode(req: EncodeReq):
    """Set one fragment to a named option, return the new coding string."""
    from .mb import varcoding
    ecu = _ecu_name_for(req.module) or req.module
    try:
        new = varcoding.encode(ecu, req.domain, _parse_hex(req.coding_hex, "coding_hex"),
                               req.fragment, req.option)
        if new is None:
            return JSONResponse({"error": "domain/CBF not found"}, status_code=404)
        return {"coding_hex": new.hex().upper()}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


class WriteReq(BaseModel):
    module: str | None = None
    did: int
    value_hex: str
    unlock: bool = True
    level: int = 1


@app.post("/api/coding/write")
def coding_write(req: WriteReq):
    """WriteDataByIdentifier (UDS 0x2E / KWP 0x3B) - adaptation/coding.

    Performs Security Access (0x27) first when the module requires it. Use with
    care: wrong values can disable an ECU. Read and save the current value first.
    """
    value = _parse_hex(req.value_hex, "value_hex")      # validate before touching the ECU
    try:
        client = _module_client(req.module)
        client.session(0x03 if client.protocol == "uds" else 0x85)
        bkp = _backup_current(client, req.module, req.did, new_hex=req.value_hex)
        unlocked = None
        if req.unlock:
            unlocked = _security_unlock(client, req.module, req.level)
        client.write_did(req.did, value)
        return {"ok": True, "security": unlocked, "backup": bkp}
    except HTTPException:
        raise
    except DiagError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=502)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# WebSocket: live data stream
# ---------------------------------------------------------------------------
@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await ws.accept()
    pids = list(DEFAULT_DASHBOARD)

    def _read_frame(selection: list[int]) -> list:
        # Blocking ctypes IO — runs in a worker thread; bus.io_lock inside the
        # client serializes it against concurrent REST requests.
        client = session.client(OBD_PHYS_TX_BASE, OBD_PHYS_RX_BASE)
        frame = []
        for pid in selection:
            try:
                frame.append(decode_pid(pid, client.read_pid(pid)))
            except DiagError:
                continue
        return frame

    try:
        if not session.connected:
            await asyncio.to_thread(session.connect)
        while True:
            # allow the client to update the PID selection (short poll)
            try:
                msg = await asyncio.wait_for(ws.receive_json(), timeout=0.05)
                if isinstance(msg, dict) and "pids" in msg:
                    pids = [int(p) & 0xFF for p in msg["pids"]][:32]
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                return
            except (ValueError, TypeError):
                pass   # malformed JSON / pid list — keep the old selection

            frame = await asyncio.to_thread(_read_frame, pids)
            await ws.send_json({"frame": frame})
            await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        try:
            await ws.send_json({"error": str(e)})
        except Exception:  # noqa: BLE001 — client already gone
            pass


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
