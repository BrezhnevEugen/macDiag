"""
UDS (ISO 14229) + basic OBD-II services on top of a PassThru backend.

The PassThru backend already handles ISO15765 (ISO-TP) segmentation when real
hardware is used, so this layer works with whole service payloads.
"""

from __future__ import annotations

import threading
import time

from .passthru import OBD_PHYS_RX_BASE, trace

NRC = {
    0x10: "generalReject",
    0x11: "serviceNotSupported",
    0x12: "subFunctionNotSupported",
    0x22: "conditionsNotCorrect",
    0x31: "requestOutOfRange",
    0x33: "securityAccessDenied",
    0x35: "invalidKey",
    0x78: "responsePending",
    0x7F: "serviceNotSupportedInActiveSession",
}


class UDSError(Exception):
    pass


class UDSTimeout(UDSError):
    """No frame at all from the ECU — it is silent / not present."""


class UDSNegative(UDSError):
    """ECU answered with a negative response (7F NRC) — it IS present."""
    def __init__(self, nrc: int, msg: str):
        super().__init__(msg)
        self.nrc = nrc


class UDSClient:
    protocol = "uds"

    def __init__(self, bus, channel_id: int, tx_id: int, rx_id: int):
        self.bus = bus
        self.channel_id = channel_id
        self.tx_id = tx_id
        self.rx_id = rx_id

    def _ensure_filter(self):
        """(Re)register our flow-control filter only if another client owned
        the channel since our last request — keeps filter churn minimal on the
        Tactrix build, where filters accumulate."""
        if getattr(self.bus, "filter_owner", None) != (self.channel_id,
                                                       self.rx_id, self.tx_id):
            self.bus.set_filters(self.channel_id, self.rx_id, self.tx_id)

    def _request(self, payload: bytes, timeout=1.0) -> bytes:
        # One diagnostic request (filter + write + read loop) is atomic: REST
        # endpoints run in the threadpool and the live WebSocket polls the same
        # channel, so without the lock responses cross-talk.
        with getattr(self.bus, "io_lock", threading.RLock()):
            self._ensure_filter()
            return self._request_io(payload, timeout)

    def _request_io(self, payload: bytes, timeout=1.0) -> bytes:
        t0 = time.time()
        hard = t0 + 3.0   # absolute cap so responsePending can't stall for 5s+
        tx = f"0x{self.tx_id:X}"
        self.bus.write(self.channel_id, self.tx_id, payload)
        deadline = time.time() + timeout
        while time.time() < deadline and time.time() < hard:
            msg = self.bus.read(self.channel_id, timeout_ms=200)
            if msg is None:
                continue
            if msg.rx_id != self.rx_id and self.rx_id != OBD_PHYS_RX_BASE:
                continue
            data = msg.data
            if not data:
                continue
            ms = int((time.time() - t0) * 1000)
            if data[0] == 0x7F:
                nrc = data[2] if len(data) > 2 else 0
                if nrc == 0x78:  # responsePending - keep waiting (capped by `hard`)
                    deadline = min(time.time() + timeout, hard)
                    continue
                trace("uds", tx=tx, req=payload.hex().upper(), rx=f"0x{msg.rx_id:X}",
                      nrc=f"0x{nrc:02X} {NRC.get(nrc, 'unknown')}", ms=ms)
                raise UDSNegative(nrc, f"NRC 0x{nrc:02X} {NRC.get(nrc, 'unknown')}")
            trace("uds", tx=tx, req=payload.hex().upper(), rx=f"0x{msg.rx_id:X}",
                  resp=data.hex().upper(), ms=ms)
            return data
        trace("uds", tx=tx, req=payload.hex().upper(), timeout=True,
              ms=int((time.time() - t0) * 1000))
        raise UDSTimeout("timeout: no response from ECU")

    def raw_request(self, payload: bytes) -> bytes:
        """Send an arbitrary diagnostic request, return the positive response."""
        return self._request(payload)

    def ping(self, timeout: float = 0.6) -> bool:
        """Fast presence probe: TesterPresent. True if the ECU answers anything
        (positive OR negative) — a negative response still proves it's there."""
        try:
            self._request(bytes([0x3E, 0x00]), timeout=timeout)
            return True
        except UDSNegative:
            return True
        except UDSError:
            return False

    # -- sessions ----------------------------------------------------------
    def session(self, session_type=0x03) -> bytes:
        """0x01 default, 0x03 extended diagnostic."""
        return self._request(bytes([0x10, session_type]))

    # -- DTC ---------------------------------------------------------------
    def read_dtcs(self) -> dict:
        """Read DTCs the Mercedes way: open the extended diagnostic session
        (0x10 0x92) first, then try the services MB ECUs actually use. Returns
        {responded, readable, dtcs, via, detail}:
          * responded — the ECU sent any frame (positive or NRC) → it is present;
          * readable  — a DTC service gave a positive response (dtcs are valid);
          * an empty `dtcs` with readable=True means "answered, no faults".
        Tries MB 0x17 -> UDS 0x19/02 -> KWP 0x18 -> OBD 0x03."""
        try:
            self._request(bytes([0x10, 0x92]))   # MB extended session (best-effort)
        except UDSError:
            pass
        attempts = [
            ("MB 0x17", bytes([0x17, 0x00, 0x00]), _parse_mb17_dtcs),
            ("UDS 0x19", bytes([0x19, 0x02, 0xFF]), _parse_uds_dtcs),
            ("KWP 0x18", bytes([0x18, 0xFF, 0xFF, 0x00]), _parse_kwp18_dtcs),
            ("OBD 0x03", bytes([0x03]), _parse_obd_dtcs),
        ]
        responded, detail = False, "timeout: no response from ECU"
        for via, req, parse in attempts:
            try:
                resp = self._request(req)
                return {"responded": True, "readable": True,
                        "dtcs": parse(resp), "via": via, "detail": "ok"}
            except UDSNegative as e:
                responded, detail = True, str(e)
            except UDSTimeout as e:
                detail = str(e)
        return {"responded": responded, "readable": False,
                "dtcs": [], "via": None, "detail": detail}

    def clear_dtcs(self) -> bool:
        try:
            self._request(bytes([0x14, 0xFF, 0xFF, 0xFF]))
        except UDSError:
            self._request(bytes([0x04]))
        return True

    # -- data --------------------------------------------------------------
    def read_did(self, did: int) -> bytes:
        resp = self._request(bytes([0x22, (did >> 8) & 0xFF, did & 0xFF]))
        return resp[3:]  # strip 0x62 + DID echo

    def read_pid(self, pid: int) -> bytes:
        resp = self._request(bytes([0x01, pid]))
        return resp[2:]  # strip 0x41 + PID echo

    # -- security access (0x27) -------------------------------------------
    def request_seed(self, level=0x01) -> bytes:
        """Odd sub-level requests a seed. Returns the seed bytes."""
        resp = self._request(bytes([0x27, level]))
        return resp[2:]  # strip 0x67 + level echo

    def send_key(self, key: bytes, level=0x02) -> bool:
        """Even sub-level sends the computed key."""
        self._request(bytes([0x27, level]) + key)
        return True

    # -- coding / adaptation ----------------------------------------------
    def write_did(self, did: int, value: bytes) -> bool:
        self._request(bytes([0x2E, (did >> 8) & 0xFF, did & 0xFF]) + value)
        return True


def _decode_dtc_3byte(b: bytes) -> str:
    """ISO 15031-6 / 14229 3-byte DTC -> letter+digits (first 2 bytes)."""
    first = b[0]
    letter = "PCBU"[(first >> 6) & 0x03]
    d1 = (first >> 4) & 0x03
    d2 = first & 0x0F
    d3 = (b[1] >> 4) & 0x0F
    d4 = b[1] & 0x0F
    return f"{letter}{d1}{d2:X}{d3:X}{d4:X}"


def _status_text(status: int) -> str:
    bits = []
    if status & 0x01: bits.append("testFailed")
    if status & 0x08: bits.append("confirmed")
    if status & 0x20: bits.append("pending")
    return ", ".join(bits) or "stored"


def _parse_mb17_dtcs(resp: bytes) -> list[dict]:
    """MB service 0x17 readDTC -> 0x57 [count?] [code_hi code_lo status] ...
    Best-effort layout (refine from a real capture); raw is always kept."""
    if not resp or resp[0] != 0x57:
        return []
    body = resp[1:]
    if len(body) % 3 == 1:        # leading count byte
        body = body[1:]
    out = []
    for i in range(0, len(body) - 2, 3):
        b = body[i:i + 3]
        out.append({"code": _decode_dtc_3byte(b[0:2] + b"\x00"),
                    "status": _status_text(b[2]), "raw": b.hex().upper()})
    return out


def _parse_uds_dtcs(resp: bytes) -> list[dict]:
    out = []
    body = resp[3:]  # skip 0x59 0x02 statusAvailabilityMask
    for i in range(0, len(body) - 3, 4):
        code = _decode_dtc_3byte(body[i:i + 3])
        out.append({"code": code, "status": _status_text(body[i + 3]),
                    "raw": body[i:i + 4].hex().upper()})
    return out


def _parse_kwp18_dtcs(resp: bytes) -> list[dict]:
    """KWP 0x18 readDTCByStatus response: 0x58 count [DThi DTlo status]*."""
    if not resp or resp[0] != 0x58:
        raise UDSError("not a 0x58 response")
    out = []
    body = resp[2:]                      # skip 0x58 + numberOfDTC
    for i in range(0, len(body) - 2, 3):
        out.append({"code": _decode_dtc_3byte(body[i:i + 2] + b"\x00"),
                    "status": _status_text(body[i + 2]),
                    "raw": body[i:i + 3].hex().upper()})
    return out


def _parse_obd_dtcs(resp: bytes) -> list[dict]:
    out = []
    count = resp[1] if len(resp) > 1 else 0
    body = resp[2:]
    for i in range(0, min(count * 2, len(body) - 1), 2):
        out.append({"code": _decode_dtc_3byte(body[i:i + 2] + b"\x00"),
                    "status": "stored", "raw": body[i:i + 2].hex().upper()})
    return out
