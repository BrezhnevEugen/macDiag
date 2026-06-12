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

import collections
import ctypes
import os
import platform
import threading
import time
from dataclasses import dataclass

# ---- diagnostic trace log (ring buffer) ------------------------------------
# Every request/response and every J2534 error is appended here so the UI can
# show the live traffic and the user can copy a log for debugging.
TRACE = collections.deque(maxlen=1000)


def trace(kind: str, **kw) -> None:
    kw["kind"] = kind
    kw["ts"] = time.time()
    TRACE.append(kw)

# ---- J2534 protocol / flag constants (subset we need) ----------------------
CAN = 5
ISO15765 = 6
ISO14230 = 4  # KWP2000

CAN_29BIT_ID = 0x00000100
ISO15765_FRAME_PAD = 0x00000040

# RxStatus bits (frames to skip when reading ISO15765 responses)
RX_TX_MSG_TYPE = 0x00000001       # loopback of our own transmit
RX_START_OF_MESSAGE = 0x00000002  # ISO15765 first-frame indication (id only)

# PassThruIoctl IDs
IOCTL_SET_CONFIG = 0x02
IOCTL_READ_VBATT = 0x03
IOCTL_CLEAR_RX_BUFFER = 0x08
IOCTL_CLEAR_MSG_FILTERS = 0x0A
FLOW_CONTROL_FILTER = 3

# The driver header (dschultzca/j2534) types every field as `unsigned long`, so
# the width is the platform's native long: 4 bytes on Windows (LLP64), 8 bytes on
# 64-bit macOS/Linux (LP64). ctypes.c_ulong matches that automatically. Override
# with MACDIAG_J2534_INT=32|64 only if a particular build differs.
_INT = os.environ.get("MACDIAG_J2534_INT")
_UL = (ctypes.c_uint32 if _INT == "32"
       else ctypes.c_uint64 if _INT == "64"
       else ctypes.c_ulong)
# PassThru* functions return int32_t (fixed 4 bytes on every platform).
_STATUS = ctypes.c_int32

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
    """Best-effort path to the Openport 2.0 J2534 driver. Override with
    env MACDIAG_DRIVER."""
    env = os.environ.get("MACDIAG_DRIVER")
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    local = os.path.join(here, "..", "..", "driver")    # project ./driver/
    system = platform.system()
    if system == "Windows":
        cands = [r"C:\Program Files (x86)\OpenECU\OpenPort 2.0\drivers\openport 2.0\op20pt32.dll",
                 r"C:\Windows\SysWOW64\op20pt32.dll",
                 os.path.join(local, "op20pt32.dll")]
        fallback = "op20pt32.dll"
    elif system == "Darwin":
        # open-source libusb J2534 built for macOS (.dylib). See README.
        cands = ["/usr/local/lib/libj2534.dylib", "/opt/homebrew/lib/libj2534.dylib",
                 os.path.join(local, "libj2534.dylib"), os.path.join(local, "libj2534.so")]
        fallback = None
    elif system == "Linux":
        cands = ["/usr/local/lib/libj2534.so", "/usr/lib/libj2534.so",
                 os.path.join(local, "libj2534.so")]
        fallback = "libj2534.so"
    else:
        cands, fallback = [], None
    for p in cands:
        if os.path.exists(p):
            return p
    return fallback


class _Msg(ctypes.Structure):
    _fields_ = [
        ("ProtocolID", _UL), ("RxStatus", _UL), ("TxFlags", _UL),
        ("Timestamp", _UL), ("DataSize", _UL), ("ExtraDataIndex", _UL),
        ("Data", ctypes.c_ubyte * 4128),
    ]


def _mk_msg(protocol: int, payload: bytes = b"", tx_flags: int = 0) -> _Msg:
    m = _Msg(ProtocolID=protocol, TxFlags=tx_flags, DataSize=len(payload))
    for i, b in enumerate(payload):
        m.Data[i] = b
    return m


class J2534PassThru:
    """ctypes wrapper around an SAE J2534-1 driver (Openport 2.0)."""

    def __init__(self, driver_path: str | None = None):
        self.driver_path = driver_path or _default_driver_path()
        if not self.driver_path:
            raise PassThruError(
                "No J2534 driver found. On macOS build the libusb driver "
                "(libj2534.dylib) and set MACDIAG_DRIVER, or run in SIM mode. "
                "See README → 'Подключение Openport 2.0'.")
        self._lib = None
        self._device_id = _UL(0)
        # Serializes all hardware IO: the J2534 driver is not thread-safe and
        # only one flow-control filter is active at a time, so a request
        # (filter + write + read loop) must not interleave with another.
        self.io_lock = threading.RLock()
        self.filter_owner: tuple | None = None   # (channel_id, rx_id, tx_id)

    # -- ctypes prototypes -------------------------------------------------
    def _bind(self):
        L = self._lib
        P = ctypes.POINTER
        sig = {
            "PassThruOpen": ([ctypes.c_void_p, P(_UL)], _STATUS),
            "PassThruClose": ([_UL], _STATUS),
            "PassThruConnect": ([_UL, _UL, _UL, _UL, P(_UL)], _STATUS),
            "PassThruDisconnect": ([_UL], _STATUS),
            "PassThruReadMsgs": ([_UL, P(_Msg), P(_UL), _UL], _STATUS),
            "PassThruWriteMsgs": ([_UL, P(_Msg), P(_UL), _UL], _STATUS),
            "PassThruStartMsgFilter":
                ([_UL, _UL, P(_Msg), P(_Msg), P(_Msg), P(_UL)], _STATUS),
            "PassThruStopMsgFilter": ([_UL, _UL], _STATUS),
            "PassThruIoctl": ([_UL, _UL, ctypes.c_void_p, ctypes.c_void_p], _STATUS),
            "PassThruGetLastError": ([ctypes.c_char_p], _STATUS),
            "PassThruReadVersion":
                ([_UL, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p], _STATUS),
        }
        for name, (args, res) in sig.items():
            try:
                fn = getattr(L, name)
                fn.argtypes = args
                fn.restype = res
            except AttributeError:
                pass

    def _last_error(self) -> str:
        try:
            buf = ctypes.create_string_buffer(128)
            self._lib.PassThruGetLastError(buf)
            return buf.value.decode("latin-1", "replace").strip()
        except Exception:  # noqa: BLE001
            return ""

    def _check(self, rc: int, fn: str):
        if rc != 0:
            msg = self._last_error()
            trace("error", fn=fn, status=rc, msg=msg)
            raise PassThruError(f"{fn} failed (status {rc}): {msg}")

    # -- lifecycle ---------------------------------------------------------
    def open(self):
        try:
            self._lib = ctypes.cdll.LoadLibrary(self.driver_path)
        except OSError as e:
            raise PassThruError(f"cannot load J2534 driver '{self.driver_path}': {e}")
        self._bind()
        rc = self._lib.PassThruOpen(None, ctypes.byref(self._device_id))
        self._check(rc, "PassThruOpen")

    def close(self):
        if self._lib:
            try:
                self._lib.PassThruClose(self._device_id)
            finally:
                self._lib = None

    def connect(self, protocol=ISO15765, baudrate=500000, flags=0) -> int:
        chan = _UL(0)
        rc = self._lib.PassThruConnect(self._device_id, protocol, flags,
                                       baudrate, ctypes.byref(chan))
        self._check(rc, "PassThruConnect")
        self.filter_owner = None   # fresh channel: no filter registered yet
        self._filter_id = None
        return chan.value

    def disconnect(self, channel_id: int):
        if self._lib:
            self._lib.PassThruDisconnect(_UL(channel_id))

    # -- filters / IO ------------------------------------------------------
    def set_filters(self, channel_id: int, rx_id: int, tx_id: int):
        # We talk to one ECU at a time, so only one flow-control filter should be
        # active. Filters otherwise accumulate and PassThruStartMsgFilter returns
        # ERR_EXCEEDED_LIMIT (status 12). Stop the previous filter explicitly
        # (the Tactrix build ignores the CLEAR_MSG_FILTERS ioctl), then also try
        # the ioctl as a fallback.
        prev = getattr(self, "_filter_id", None)
        if prev is not None:
            try:
                self._lib.PassThruStopMsgFilter(_UL(channel_id), _UL(prev))
            except Exception:  # noqa: BLE001
                pass
            self._filter_id = None
        try:
            self._lib.PassThruIoctl(_UL(channel_id), IOCTL_CLEAR_MSG_FILTERS,
                                    None, None)
        except Exception:  # noqa: BLE001
            pass
        mask = _mk_msg(ISO15765, b"\xFF\xFF\xFF\xFF")
        patt = _mk_msg(ISO15765, rx_id.to_bytes(4, "big"))
        flow = _mk_msg(ISO15765, tx_id.to_bytes(4, "big"))
        fid = _UL(0)
        rc = self._lib.PassThruStartMsgFilter(
            _UL(channel_id), FLOW_CONTROL_FILTER,
            ctypes.byref(mask), ctypes.byref(patt), ctypes.byref(flow),
            ctypes.byref(fid))
        self._check(rc, "PassThruStartMsgFilter")
        self._filter_id = fid.value
        self.filter_owner = (channel_id, rx_id, tx_id)
        return fid.value

    def write(self, channel_id: int, tx_id: int, data: bytes, timeout_ms=100):
        msg = _mk_msg(ISO15765, tx_id.to_bytes(4, "big") + data, ISO15765_FRAME_PAD)
        count = _UL(1)
        rc = self._lib.PassThruWriteMsgs(_UL(channel_id), ctypes.byref(msg),
                                         ctypes.byref(count), _UL(timeout_ms))
        self._check(rc, "PassThruWriteMsgs")

    def read(self, channel_id: int, timeout_ms=200) -> PassThruMessage | None:
        """Read one real response, skipping loopback / first-frame indications."""
        deadline = time.time() + timeout_ms / 1000.0
        while True:
            msg = _Msg()
            count = _UL(1)
            rc = self._lib.PassThruReadMsgs(_UL(channel_id), ctypes.byref(msg),
                                            ctypes.byref(count), _UL(20))
            if rc == 0 and count.value:
                ds = int(msg.DataSize)
                rx = int(msg.RxStatus)
                if ds > 4 and not (rx & (RX_TX_MSG_TYPE | RX_START_OF_MESSAGE)):
                    raw = bytes(msg.Data[:ds])
                    return PassThruMessage(int.from_bytes(raw[:4], "big"), raw[4:])
            if time.time() >= deadline:
                return None

    # -- diagnostics -------------------------------------------------------
    def read_vbatt(self, channel_id: int | None = None) -> float:
        """Battery voltage in volts (connection sanity test)."""
        mv = _UL(0)
        target = _UL(channel_id) if channel_id is not None else self._device_id
        rc = self._lib.PassThruIoctl(target, IOCTL_READ_VBATT, None, ctypes.byref(mv))
        self._check(rc, "PassThruIoctl(READ_VBATT)")
        return round(mv.value / 1000.0, 2)

    def read_version(self) -> dict:
        """API / DLL / firmware versions read FROM the adapter - proves the
        Mac<->cable link works even with no car connected."""
        api = ctypes.create_string_buffer(80)
        dll = ctypes.create_string_buffer(80)
        fw = ctypes.create_string_buffer(80)
        rc = self._lib.PassThruReadVersion(self._device_id, api, dll, fw)
        self._check(rc, "PassThruReadVersion")
        dec = lambda b: b.value.decode("latin-1", "replace").strip()
        return {"api": dec(api), "dll": dec(dll), "firmware": dec(fw)}


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
        self._seed: bytes | None = None
        self._unlocked = False
        self._coding: dict[int, bytes] = {}   # identifier -> stored coding blob
        self.io_lock = threading.RLock()      # same contract as J2534PassThru
        self.filter_owner: tuple | None = None

    # -- lifecycle ---------------------------------------------------------
    def open(self):
        self._open = True

    def close(self):
        self._open = False

    def connect(self, protocol=ISO15765, baudrate=500000, flags=0) -> int:
        return 1

    def disconnect(self, channel_id: int):
        pass

    def read_vbatt(self, channel_id=None) -> float:
        import math
        return round(12.4 + 0.1 * math.sin(time.time() / 5), 2)

    def read_version(self) -> dict:
        return {"api": "04.04", "dll": "SIM-3.0.0", "firmware": "OP2-SIM"}

    def set_filters(self, channel_id: int, rx_id: int, tx_id: int):
        self._rx_id = rx_id
        self.filter_owner = (channel_id, rx_id, tx_id)
        return 1

    # -- I/O ---------------------------------------------------------------
    def write(self, channel_id: int, tx_id: int, data: bytes, timeout_ms=100):
        # respond on the id the client is filtering for (real modules use
        # arbitrary response ids, not the OBD tx+8 convention)
        rx_id = getattr(self, "_rx_id", None)
        if rx_id is None:
            rx_id = (tx_id + 8) if tx_id != OBD_FUNCTIONAL_TX else OBD_PHYS_RX_BASE
        # captured real-car behaviour first (this vehicle's actual responses)
        from .car_profile import lookup
        matched, val = lookup(tx_id, data.hex())
        if matched:
            if val is not None:
                self._pending.append(PassThruMessage(rx_id=rx_id, data=bytes.fromhex(val)))
            return                      # captured timeout/silent -> no response
        resp = self._respond(data)      # generic synthetic fallback
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

        # UDS/KWP 0x3E - TesterPresent (presence probe / ping)
        if sid == 0x3E:
            return bytes([0x7E, 0x00])

        # OBD mode 09 PID 02 - VIN
        if sid == 0x09 and len(req) >= 2 and req[1] == 0x02:
            return bytes([0x49, 0x02, 0x01]) + b"4JGBF71E07A000001"

        # MB readEcuIdentification 0x1A (0x90 = VIN)
        if sid == 0x1A and len(req) >= 2:
            if req[1] == 0x90:
                return bytes([0x5A, 0x90]) + b"WDC1641541A123456"
            return bytes([0x5A, req[1]]) + bytes(8)
        # MB readDataByLocalId 0x21 (e.g. 21E0 version)
        if sid == 0x21 and len(req) >= 2:
            return bytes([0x61, req[1]]) + bytes(16)
        # MB routineControl 0x31 (CAN config 310800/310700, etc.)
        if sid == 0x31 and len(req) >= 3:
            return bytes([0x71, req[1], req[2]]) + bytes(16)
        # MB variant coding read 0x30 (300101 = 38-byte global code)
        if sid == 0x30 and len(req) >= 2:
            return bytes([0x70, req[1]]) + bytes(38)

        # OBD mode 01 - current data (live PIDs)
        if sid == 0x01 and len(req) >= 2:
            pid = req[1]
            val = self._live_pid(pid)
            if val is not None:
                return bytes([0x41, pid]) + val

        # UDS 0x22 - ReadDataByIdentifier
        if sid == 0x22 and len(req) >= 3:
            did = (req[1] << 8) | req[2]
            if did in self._coding:                  # previously written coding
                return bytes([0x62, req[1], req[2]]) + self._coding[did]
            data = self._read_did(did)
            if data is not None:
                return bytes([0x62, req[1], req[2]]) + data
            # unknown identifier: zeroed coding blob (UI pads/trims to dump size)
            return bytes([0x62, req[1], req[2]]) + bytes(32)

        # UDS 0x19 / OBD 0x03 - read DTCs
        if sid == 0x19 or sid == 0x03:
            return self._read_dtcs(sid)

        # MB 0x17 readDTC - synth a couple of faults so the DTC flow is testable
        if sid == 0x17:
            if getattr(self, "_cleared", False):
                return bytes([0x57, 0x00])
            return bytes([0x57, 0x02, 0x95, 0x35, 0x28, 0x55, 0x25, 0x28])

        # UDS 0x14 / OBD 0x04 - clear DTCs
        if sid == 0x14 or sid == 0x04:
            self._cleared = True
            return bytes([sid + 0x40])

        # UDS 0x10 / KWP 0x10 - session control (enter session)
        if sid == 0x10 and len(req) >= 2:
            return bytes([0x50, req[1], 0x00, 0x32, 0x01, 0xF4])

        # 0x27 - SecurityAccess (UDS and KWP share this service id)
        if sid == 0x27 and len(req) >= 2:
            level = req[1]
            if level % 2 == 1:  # request seed (odd sub-function = 2L-1)
                self._seed = bytes([0x12, 0x34, 0x56, 0x78])
                return bytes([0x67, level]) + self._seed
            # send key (even sub-function = 2L): validate against 'sim' algo at
            # the matching logical level L = sub-function / 2
            if self._seed is not None:
                from ..mb.seedkey import get_algo
                expected = get_algo("sim")(self._seed, level // 2)
                if req[2:] == expected:
                    self._unlocked = True
                    return bytes([0x67, level])
            return bytes([0x7F, 0x27, 0x35])  # invalidKey

        # UDS 0x2E / KWP 0x3B - WriteDataByIdentifier (coding/adaptation)
        if sid in (0x2E, 0x3B):
            if not self._unlocked:
                return bytes([0x7F, sid, 0x33])  # securityAccessDenied
            if sid == 0x2E and len(req) >= 3:
                self._coding[(req[1] << 8) | req[2]] = req[3:]   # store by DID
                return bytes([0x6E, req[1], req[2]])
            if sid == 0x3B and len(req) >= 2:
                self._coding[req[1]] = req[2:]                   # store by local id
                return bytes([0x7B, req[1]])

        # KWP 0x18 - ReadDTCByStatus
        if sid == 0x18:
            if self._cleared:
                return bytes([0x58, 0x00])
            return bytes([0x58, 0x02, 0x95, 0x35, 0x08, 0x55, 0x25, 0x08])

        # KWP 0x21 - ReadDataByLocalIdentifier
        if sid == 0x21 and len(req) >= 2:
            lid = req[1]
            if lid in self._coding:                  # previously written coding
                return bytes([0x61, lid]) + self._coding[lid]
            local = {0x05: bytes([0x5A]), 0x0C: bytes([0x08, 0xCA])}
            if lid in local:
                return bytes([0x61, lid]) + local[lid]
            # unknown id: return a zeroed coding blob (length the UI will pad/trim)
            return bytes([0x61, lid]) + bytes(32)

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
