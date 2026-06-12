"""
KWP2000 (ISO 14230) services carried over CAN / ISO15765.

Many Mercedes control units of the W221/X164 era (EZS, ESP, SRS, SAM, AIRMATIC)
answer KWP2000 rather than UDS. The framing (ISO-TP) is identical to UDS - only
the service IDs and a few sub-functions differ. This client mirrors UDSClient's
interface so the API can treat both transparently.

KWP2000 services used here:
    0x10  StartDiagnosticSession
    0x14  ClearDiagnosticInformation
    0x18  ReadDTCByStatus
    0x21  ReadDataByLocalIdentifier
    0x22  ReadDataByCommonIdentifier   (some MB units)
    0x27  SecurityAccess
    0x3B  WriteDataByLocalIdentifier   (coding / adaptation)
"""

from __future__ import annotations

import threading
import time

from .passthru import OBD_PHYS_RX_BASE, trace
from .uds import NRC, _decode_dtc_3byte, _status_text


class KWPError(Exception):
    pass


class KWPTimeout(KWPError):
    """No frame from the ECU — silent / not present."""


class KWPNegative(KWPError):
    """ECU answered with a 7F negative response — it IS present."""
    def __init__(self, nrc: int, msg: str):
        super().__init__(msg)
        self.nrc = nrc


class KWPClient:
    protocol = "kwp"

    def __init__(self, bus, channel_id: int, tx_id: int, rx_id: int):
        self.bus = bus
        self.channel_id = channel_id
        self.tx_id = tx_id
        self.rx_id = rx_id

    def _ensure_filter(self):
        """See UDSClient._ensure_filter — same single-active-filter contract."""
        if getattr(self.bus, "filter_owner", None) != (self.channel_id,
                                                       self.rx_id, self.tx_id):
            self.bus.set_filters(self.channel_id, self.rx_id, self.tx_id)

    def _request(self, payload: bytes, timeout=1.0) -> bytes:
        # Atomic request — see UDSClient._request for the rationale.
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
                if nrc == 0x78:  # responsePending (capped by `hard`)
                    deadline = min(time.time() + timeout, hard)
                    continue
                trace("kwp", tx=tx, req=payload.hex().upper(), rx=f"0x{msg.rx_id:X}",
                      nrc=f"0x{nrc:02X} {NRC.get(nrc, 'unknown')}", ms=ms)
                raise KWPNegative(nrc, f"NRC 0x{nrc:02X} {NRC.get(nrc, 'unknown')}")
            trace("kwp", tx=tx, req=payload.hex().upper(), rx=f"0x{msg.rx_id:X}",
                  resp=data.hex().upper(), ms=ms)
            return data
        trace("kwp", tx=tx, req=payload.hex().upper(), timeout=True,
              ms=int((time.time() - t0) * 1000))
        raise KWPTimeout("timeout: no response from ECU")

    def raw_request(self, payload: bytes) -> bytes:
        return self._request(payload)

    def ping(self, timeout: float = 0.6) -> bool:
        """Fast presence probe: TesterPresent (0x3E). Any answer (positive or
        NRC) means the ECU is present."""
        try:
            self._request(bytes([0x3E, 0x00]), timeout=timeout)
            return True
        except KWPNegative:
            return True
        except KWPError:
            return False

    # -- session -----------------------------------------------------------
    def session(self, session_type=0x85) -> bytes:
        """0x81 default, 0x85 programming/extended (MB development session)."""
        return self._request(bytes([0x10, session_type]))

    # -- DTC ---------------------------------------------------------------
    def read_dtcs(self) -> dict:
        """0x18 readDTCByStatus. Returns {responded, readable, dtcs, via, detail}
        so the UI can tell 'answered, no faults' from 'no response'."""
        try:
            resp = self._request(bytes([0x18, 0xFF, 0xFF, 0x00]))
            return {"responded": True, "readable": True,
                    "dtcs": _parse_kwp_dtcs(resp), "via": "KWP 0x18", "detail": "ok"}
        except KWPNegative as e:
            return {"responded": True, "readable": False,
                    "dtcs": [], "via": None, "detail": str(e)}
        except KWPTimeout as e:
            return {"responded": False, "readable": False,
                    "dtcs": [], "via": None, "detail": str(e)}

    def clear_dtcs(self) -> bool:
        # 0x14 clearDiagnosticInformation, group 0xFF00 = all
        self._request(bytes([0x14, 0xFF, 0x00]))
        return True

    # -- data --------------------------------------------------------------
    def read_did(self, did: int) -> bytes:
        """Try common identifier (0x22) then local identifier (0x21)."""
        try:
            resp = self._request(bytes([0x22, (did >> 8) & 0xFF, did & 0xFF]))
            return resp[3:]
        except KWPError:
            resp = self._request(bytes([0x21, did & 0xFF]))
            return resp[2:]

    def read_pid(self, pid: int) -> bytes:
        # KWP units don't expose OBD mode 01; read as local identifier.
        resp = self._request(bytes([0x21, pid & 0xFF]))
        return resp[2:]

    # -- security access ---------------------------------------------------
    def request_seed(self, level=0x01) -> bytes:
        resp = self._request(bytes([0x27, level]))
        return resp[2:]  # strip 0x67 + level

    def send_key(self, key: bytes, level=0x02) -> bool:
        self._request(bytes([0x27, level]) + key)
        return True

    # -- coding ------------------------------------------------------------
    def write_did(self, did: int, value: bytes) -> bool:
        # 0x3B writeDataByLocalIdentifier
        self._request(bytes([0x3B, did & 0xFF]) + value)
        return True


def _parse_kwp_dtcs(resp: bytes) -> list[dict]:
    """0x58 numDTC  [DTChigh DTClow status] ..."""
    out = []
    body = resp[2:]  # skip 0x58 numberOfDTC
    for i in range(0, len(body) - 2, 3):
        code = _decode_dtc_3byte(body[i:i + 2] + b"\x00")
        out.append({"code": code, "status": _status_text(body[i + 2]),
                    "raw": body[i:i + 3].hex().upper()})
    return out
