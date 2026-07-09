"""Captured simulator traffic loaded from the active vehicle profile.

The trace is data, not executable logic: each profile owns its installed/silent
ECUs and exact request/response pairs. That lets a new bench capture be added
without modifying the J2534 transport implementation.
"""

from __future__ import annotations

from ..mb.modules import simulator_profile


def config() -> dict:
    """Return the active simulator section (a safe copy from the profile loader)."""
    return simulator_profile()


def lookup(tx_id: int, request_hex: str) -> tuple[bool, str | None]:
    """Return ``(matched, response_or_none)`` for a captured ECU request.

    ``matched=False`` means the generic simulator may synthesize a response;
    ``matched=True, None`` models a captured timeout or an ECU not fitted to the
    selected vehicle profile.
    """
    capture = config().get("capture", {})
    ecu = capture.get(str(tx_id))
    if not isinstance(ecu, dict):
        return False, None
    if ecu.get("silent"):
        return True, None
    response = (ecu.get("resp") or {}).get(request_hex.upper(), ...)
    if response is ...:
        return False, None
    return True, response
