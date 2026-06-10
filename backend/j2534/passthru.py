"""
J2534 PassThru abstraction layer for Tactrix Openport 2.0.

Two backends are provided:
  * J2534PassThru  - real hardware via the vendor J2534 DLL/.so (ctypes)
  * SimPassThru    - software simulator so the whole web app runs without a cable

Both expose the same minimal interface used by the UDS/KWP layers:
    open() / close()
    connect(protocol, baudrate, flags) -> channel_id
    disconnect(channel_id)
    set_filters(channel_id, rx_id, tx_id)      # ISO15765 flow-control filter
    write(channel_id, tx_id, data: bytes)
    read(channel_id, timeout_ms) -> (rx_id, bytes) | None

The Openport 2.0 is a SAE J2534-1 PassThru device. It is NOT an ELM327 and does
not speak AT commands over a virtual COM port, so the browser cannot talk to it
directly via the Web Serial API. A native host process (this backend) must load
the J2534 driver. See README for the rationale.
"""

from __future__ import annotations

import ctypes
import os
import platform
import time
from dataclasses import dataclass

# ---- J2534 protocol / flag constants (subset we need) ----------------------
CAN = 5
ISO15765 = 6
ISO14230 = 4  # KWP2000

CAN_29BIT_ID = 0x00000100
ISO15765_FRAME_PAD = 0x00000040

# Standard 11-bit OBD addressing (functional broadcast)
OBD_FUNCTIONAL_TX = 0x7DF
OBD_PHYS_TX_BASE = 0x7E0   # ECU 0 request
OBD_PHYS_RX_BASE = 0x7E8   # ECU 0 response


@dataclass
class PassThruMessage:
    rx_id: int
    data: bytes


class PassThruError(Exception):
    pass


# ---------------------------------------------------------------------------
# Real hardware backend
# ---------------------------------------------------------------------------
def _default_driver_path() -> str | None:
    """Best-effort guess of the Openport 2.0 J2534 driver path per OS."""
    system = platform.system()
    if system == "Windows":
        # Installed by the Tactrix "OpenPort 2.0 J2534" / EcuFlash package.
        for p in (
            r"C:\Program Files (x86)\OpenECU\OpenPort 2.0\drivers\openport 2.0\op20pt32.dll",
            r"C:\Windows\SysWOW64\op20pt32.dll",
        ):
            if os.path.exists(p):
                return p
        return "op20pt32.dll"
    if system == "Linux":
        # Built from github.com/dschultzca/j2534 or NikolaKozina/j2534
        for p in ("/usr/local/lib/libj2534.so", "/usr/lib/libj2534.so"):
            if os.path.exists(p):
                return p
        return "libj2534.so"
    if system == "Darwin":
        # No official macOS J2534. Use Linux build in a VM, or the simulator.
        return None
    return None


class _Msg(ctypes.Structure):
    _fields_ = [
        ("ProtocolID", ctypes.c_uint32),
        ("RxStatus", ctypes.c_uint32),
        ("TxFlags", ctypes.c_uint32),
        ("Timestamp", ctypes.c_uint32),
        ("DataSize", ctypes.c_uint32),
        ("ExtraDataIndex", ctypes.c_uint32),
        ("Data", ctypes.c_ubyte * 4128),
    ]


class J2534PassThru:
    """Thin ctypes wrapper around the vendor J2534 driver."""

    def __init__(self, driver_path: str | None = None):
        self.driver_path = driver_path or _default_driver_path()
        if not self.driver_path:
            raise PassThruError(
                "No J2534 driver path. macOS has no native Openport J2534 driver "
                "- run the backend on Windows/Linux, or use SIM mode."
            )
        self._lib = None
        self._device_id = ctypes.c_uint32(0)

    def _check(self, rc: int, fn: str):
        if rc != 0:
            raise PassThruError(f"{fn} failed, J2534 status={rc}")

    def open(self):
        self._lib = ctypes.cdll.LoadLibrary(self.driver_path)
        rc = self._lib.PassThruOpen(None, ctypes.byref(self._device_id))
        self._check(rc, "PassThruOpen")

    def close(self):
        if self._lib:
            self._lib.PassThruClose(self._device_id)
            self._lib = None

    def connect(self, protocol=ISO15765, baudrate=500000, flags=0) -> int:
        chan = ctypes.c_uint32(0)
        rc = self._lib.PassThruConnect(
            self._device_id, protocol, flags, baudrate, ctypes.byref(chan)
        )
        self._check(rc, "PassThruConnect")
        return chan.value

    def disconnect(self, channel_id: int):
        self._lib.PassThruDisconnect(ctypes.c_uint32(channel_id))

    def set_filters(self, channel_id: int, rx_id: int, tx_id: int):
        # FLOW_CONTROL_FILTER for ISO15765, pattern matches the ECU response id.
        mask = _Msg(ProtocolID=ISO15765, DataSize=4)
        patt = _Msg(ProtocolID=ISO15765, DataSize=4)
        flow = _Msg(ProtocolID=ISO15765, DataSize=4)
        for i, b in enumerate((0xFF, 0xFF, 0xFF, 0xFF)):
            mask.Data[i] = b
        for i, b in enumerate(rx_id.to_bytes(4, "big")):
            patt.Data[i] = b
        for i, b in enumerate(tx_id.to_bytes(4, "big")):
            flow.Data[i] = b
        fid = ctypes.c_uint32(0)
        FLOW_CONTROL_FILTER = 3
        rc = self._lib.PassThruStartMsgFilter(
            ctypes.c_uint32(channel_id), FLOW_CONTROL_FILTER,
            ctypes.byref(mask), ctypes.byref(patt), ctypes.byref(flow),
            ctypes.byref(fid),
        )
        self._check(rc, "PassThruStartMsgFilter")
        return fid.value

    def write(self, channel_id: int, tx_id: int, data: bytes, timeout_ms=100):
        msg = _Msg(ProtocolID=ISO15765, TxFlags=ISO15765_FRAME_PAD)
        payload = tx_id.to_bytes(4, "big") + data
        msg.DataSize = len(payload)
        for i, b in enumerate(payload):
            msg.Data[i] = b
        count = ctypes.c_uint32(1)
        rc = self._lib.PassThruWriteMsgs(
            ctypes.c_uint32(channel_id), ctypes.byref(msg),
            ctypes.byref(count), timeout_ms,
        )
        self._check(rc, "PassThruWriteMsgs")

    def read(self, channel_id: int, timeout_ms=200) -> PassThruMessage | None:
        msg = _Msg()
        count = ctypes.c_uint32(1)
        rc = self._lib.PassThruReadMsgs(
            ctypes.c_uint32(channel_id), ctypes.byref(msg),
            ctypes.byref(count), timeout_ms,
        )
        if rc != 0 or count.value == 0 or msg.DataSize < 4:
            return None
        raw = bytes(msg.Data[: msg.DataSize])
        return PassThruMessage(rx_id=int.from_bytes(raw[:4], "big"), data=raw[4:])


# ---------------------------------------------------------------------------
# Simulator backend (no hardware needed)
# ---------------------------------------------------------------------------
class SimPassThru:
    """
    In-memory simulator. Answers UDS/OBD requests with believable W221/X164
    data so the full web UI can be exercised without a car or cable.
    """

    def __init__(self, *_args, **_kwargs):
        self._open = False
        self._t0 = time.time()
        self._pending: list[PassThruMessage] = []
        self._cleared = False

    # -- lifecycle ---------------------------------------------------------
    def open(self):
        self._open = True

    def close(self):
        self._open = False

    def connect(self, protocol=ISO15765, baudrate=500000, flags=0) -> int:
        return 1

    def disconnect(self, channel_id: int):
        pass

    def set_filters(self, channel_id: int, rx_id: int, tx_id: int):
        self._rx_id = rx_id
        return 1

    # -- I/O ---------------------------------------------------------------
    def write(self, channel_id: int, tx_id: int, data: bytes, timeout_ms=100):
        rx_id = (tx_id + 8) if tx_id != OBD_FUNCTIONAL_TX else OBD_PHYS_RX_BASE
        resp = self._respond(data)
        if resp is not None:
            self._pending.append(PassThruMessage(rx_id=rx_id, data=resp))

    def read(self, channel_id: int, timeout_ms=200) -> PassThruMessage | None:
        if self._pending:
            return self._pending.pop(0)
        return None

    # -- fake ECU logic ----------------------------------------------------
    def _respond(self, req: bytes) -> bytes | None:
        if not req:
            return None
        sid = req[0]

        # OBD mode 01 - current data (live PIDs)
        if sid == 0x01 and len(req) >= 2:
            pid = req[1]
            val = self._live_pid(pid)
            if val is not None:
                return bytes([0x41, pid]) + val

        # UDS 0x22 - ReadDataByIdentifier
        if sid == 0x22 and len(req) >= 3:
            did = (req[1] << 8) | req[2]
            data = self._read_did(did)
            if data is not None:
                return bytes([0x62, req[1], req[2]]) + data

        # UDS 0x19 / OBD 0x03 - read DTCs
        if sid == 0x19 or sid == 0x03:
            return self._read_dtcs(sid)

        # UDS 0x14 / OBD 0x04 - clear DTCs
        if sid == 0x14 or sid == 0x04:
            self._cleared = True
            return bytes([sid + 0x40])

        # UDS 0x10 - DiagnosticSessionControl (enter session)
        if sid == 0x10 and len(req) >= 2:
            return bytes([0x50, req[1], 0x00, 0x32, 0x01, 0xF4])

        # UDS 0x2E - WriteDataByIdentifier (adaptation/coding)
        if sid == 0x2E and len(req) >= 3:
            return bytes([0x6E, req[1], req[2]])

        # Negative response (service not supported)
        return bytes([0x7F, sid, 0x11])

    def _live_pid(self, pid: int) -> bytes | None:
        import math
        t = time.time() - self._t0
        table = {
            0x05: bytes([88 + int(8 * math.sin(t / 7)) + 40]),         # coolant temp +40 offset
            0x0C: ((1500 + int(700 * (math.sin(t / 3) + 1))) * 4).to_bytes(2, "big"),  # RPM
            0x0D: bytes([max(0, int(60 + 50 * math.sin(t / 11)))]),     # speed km/h
            0x0F: bytes([30 + int(5 * math.sin(t / 13)) + 40]),         # intake air temp
            0x11: bytes([int(20 + 15 * (math.sin(t / 5) + 1))]),        # throttle %
            0x2F: bytes([int(70 + 25 * math.sin(t / 29))]),            # fuel level %
            0x42: (13800 + int(400 * math.sin(t / 4))).to_bytes(2, "big"),  # control module voltage mV
        }
        return table.get(pid)

    def _read_did(self, did: int) -> bytes | None:
        dids = {
            0xF190: b"WDD2211711A123456",      # VIN
            0xF195: b"02/14",                    # SW version
            0xF18C: b"EZS-W221-REVE",            # serial
            0xF187: b"A2215403345",              # MB part number
        }
        return dids.get(did)

    def _read_dtcs(self, sid: int) -> bytes:
        if self._cleared:
            # no stored faults after a clear
            return bytes([0x59, 0x02, 0xFF]) if sid == 0x19 else bytes([0x43, 0x00])
        # Two believable W221 faults, SAE J2012 encoded:
        #   B1535 -> 0x95 0x35 (seat/body module)
        #   C1525 -> 0x55 0x25 (ESP)
        if sid == 0x19:
            #  0x59 0x02 statusAvail  DTC(3) status  DTC(3) status
            return bytes([0x59, 0x02, 0xFF,
                          0x95, 0x35, 0x00, 0x08,
                          0x55, 0x25, 0x00, 0x08])
        # OBD mode 03: count + DTC pairs (2 bytes each)
        return bytes([0x43, 0x02, 0x95, 0x35, 0x55, 0x25])


def make_passthru(mode: str, driver_path: str | None = None):
    """Factory: mode='sim' or mode='hw'."""
    if mode == "hw":
        return J2534PassThru(driver_path)
    return SimPassThru()
