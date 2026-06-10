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
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .j2534 import make_passthru, UDSClient, UDSError, ISO15765
from .j2534.passthru import OBD_PHYS_TX_BASE, OBD_PHYS_RX_BASE
from .mb import (MODULES, MODULES_BY_ID, modules_for, DEFAULT_DASHBOARD,
                 DIDS, decode_pid, describe_dtc)

MODE = os.environ.get("MACDIAG_MODE", "sim")  # 'sim' or 'hw'
DRIVER = os.environ.get("MACDIAG_DRIVER")

app = FastAPI(title="macDiag", version="0.1.0")


# ---------------------------------------------------------------------------
# Connection state (single active session - this is a bench tool, not a server)
# ---------------------------------------------------------------------------
class Session:
    def __init__(self):
        self.bus = None
        self.channel = None
        self.connected = False

    def connect(self):
        if self.connected:
            return
        self.bus = make_passthru(MODE, DRIVER)
        self.bus.open()
        self.channel = self.bus.connect(ISO15765, 500000)
        self.connected = True

    def disconnect(self):
        if self.bus and self.connected:
            try:
                self.bus.disconnect(self.channel)
                self.bus.close()
            finally:
                self.connected = False

    def client(self, tx: int, rx: int) -> UDSClient:
        if not self.connected:
            self.connect()
        return UDSClient(self.bus, self.channel, tx, rx)


session = Session()


def _module_client(module_id: str | None) -> UDSClient:
    if module_id and module_id in MODULES_BY_ID:
        m = MODULES_BY_ID[module_id]
        return session.client(m["tx"], m["rx"])
    # default: engine ECU / generic OBD physical address
    return session.client(OBD_PHYS_TX_BASE, OBD_PHYS_RX_BASE)


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------
@app.get("/api/status")
def status():
    return {"mode": MODE, "connected": session.connected, "driver": DRIVER}


@app.post("/api/connect")
def connect():
    try:
        session.connect()
        return {"connected": True, "mode": MODE}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"connected": False, "error": str(e)}, status_code=400)


@app.post("/api/disconnect")
def disconnect():
    session.disconnect()
    return {"connected": False}


@app.get("/api/modules")
def get_modules(chassis: str | None = None):
    return {"modules": modules_for(chassis)}


@app.get("/api/dtc")
def read_dtc(module: str | None = None):
    try:
        client = _module_client(module)
        dtcs = client.read_dtcs()
        for d in dtcs:
            d["description"] = describe_dtc(d["code"])
        return {"module": module, "dtcs": dtcs}
    except UDSError as e:
        return JSONResponse({"error": str(e)}, status_code=502)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/dtc/clear")
def clear_dtc(module: str | None = None):
    try:
        client = _module_client(module)
        client.clear_dtcs()
        return {"cleared": True, "module": module}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=502)


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
            except UDSError:
                out[label] = None
        return {"module": module, "info": out}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=502)


class WriteReq(BaseModel):
    module: str | None = None
    did: int
    value_hex: str


@app.post("/api/coding/write")
def coding_write(req: WriteReq):
    """WriteDataByIdentifier - adaptation/coding. Use with care."""
    try:
        client = _module_client(req.module)
        client.session(0x03)  # extended session usually required
        client.write_did(req.did, bytes.fromhex(req.value_hex))
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=502)


# ---------------------------------------------------------------------------
# WebSocket: live data stream
# ---------------------------------------------------------------------------
@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await ws.accept()
    pids = list(DEFAULT_DASHBOARD)
    try:
        if not session.connected:
            session.connect()
        client = session.client(OBD_PHYS_TX_BASE, OBD_PHYS_RX_BASE)
        while True:
            # allow the client to update the PID selection
            try:
                msg = await asyncio.wait_for(ws.receive_json(), timeout=0.001)
                if isinstance(msg, dict) and "pids" in msg:
                    pids = [int(p) for p in msg["pids"]]
            except (asyncio.TimeoutError, Exception):
                pass

            frame = []
            for pid in pids:
                try:
                    raw = client.read_pid(pid)
                    frame.append(decode_pid(pid, raw))
                except UDSError:
                    continue
            await ws.send_json({"frame": frame})
            await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        await ws.send_json({"error": str(e)})


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
