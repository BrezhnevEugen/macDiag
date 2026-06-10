"""
UDS (ISO 14229) + basic OBD-II services on top of a PassThru backend.

The PassThru backend already handles ISO15765 (ISO-TP) segmentation when real
hardware is used, so this layer works with whole service payloads.
"""

from __future__ import annotations

import time

from .passthru import OBD_FUNCTIONAL_TX, OBD_PHYS_RX_BASE

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


class UDSClient:
    def __init__(self, bus, channel_id: int, tx_id: int, rx_id: int):
        self.bus = bus
        self.channel_id = channel_id
        self.tx_id = tx_id
        self.rx_id = rx_id
        self.bus.set_filters(channel_id, rx_id, tx_id)

    def _request(self, payload: bytes, timeout=1.5) -> bytes:
        self.bus.write(self.channel_id, self.tx_id, payload)
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = self.bus.read(self.channel_id, timeout_ms=200)
            if msg is None:
                continue
            if msg.rx_id != self.rx_id and self.rx_id != OBD_PHYS_RX_BASE:
                continue
            data = msg.data
            if not data:
                continue
            if data[0] == 0x7F:
                nrc = data[2] if len(data) > 2 else 0
                if nrc == 0x78:  # responsePending - keep waiting
                    deadline = time.time() + timeout
                    continue
                raise UDSError(f"NRC 0x{nrc:02X} {NRC.get(nrc, 'unknown')}")
            return data
        raise UDSError("timeout: no response from ECU")

    # -- sessions ----------------------------------------------------------
    def session(self, session_type=0x03) -> bytes:
        """0x01 default, 0x03 extended diagnostic."""
        return self._request(bytes([0x10, session_type]))

    # -- DTC ---------------------------------------------------------------
    def read_dtcs(self) -> list[dict]:
        """UDS 0x19 sub 0x02 reportDTCByStatusMask, with OBD-03 fallback."""
        try:
            resp = self._request(bytes([0x19, 0x02, 0xFF]))
            return _parse_uds_dtcs(resp)
        except UDSError:
            resp = self._request(bytes([0x03]))
            return _parse_obd_dtcs(resp)

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


def _parse_uds_dtcs(resp: bytes) -> list[dict]:
    out = []
    body = resp[3:]  # skip 0x59 0x02 statusAvailabilityMask
    for i in range(0, len(body) - 3, 4):
        code = _decode_dtc_3byte(body[i:i + 3])
        out.append({"code": code, "status": _status_text(body[i + 3]),
                    "raw": body[i:i + 4].hex().upper()})
    return out


def _parse_obd_dtcs(resp: bytes) -> list[dict]:
    out = []
    count = resp[1] if len(resp) > 1 else 0
    body = resp[2:]
    for i in range(0, min(count * 2, len(body) - 1), 2):
        out.append({"code": _decode_dtc_3byte(body[i:i + 2] + b"\x00"),
                    "status": "stored", "raw": body[i:i + 2].hex().upper()})
    return out
