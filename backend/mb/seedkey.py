"""
Security Access (service 0x27) seed -> key algorithms.

The real key algorithm for a given Mercedes control unit is ECU-specific and
proprietary - it is NOT published by the manufacturer. You must supply the
correct algorithm for your target module (often derived per-ECU, sometimes
identical across a family). This module provides a pluggable registry so the
backend stays generic.

Register an algorithm:

    @register("ezs")
    def ezs_key(seed: bytes, level: int) -> bytes:
        ...

Lookup order in the API: module id -> "default". The bundled "sim" algorithm
matches the simulator ECU so the unlock flow can be tested end to end; it is
NOT valid on a real car.
"""

from __future__ import annotations

from typing import Callable

_ALGOS: dict[str, Callable[[bytes, int], bytes]] = {}


def register(name: str):
    def deco(fn: Callable[[bytes, int], bytes]):
        _ALGOS[name] = fn
        return fn
    return deco


def get_algo(module_id: str | None) -> Callable[[bytes, int], bytes] | None:
    if module_id and module_id in _ALGOS:
        return _ALGOS[module_id]
    return _ALGOS.get("default")


# --- simulator algorithm (matches SimPassThru, invalid on real hardware) -----
@register("sim")
@register("default")
def _sim_key(seed: bytes, level: int) -> bytes:
    """
    Toy reversible transform used by the simulator: key = (seed XOR 0x5A) + 1,
    big-endian, same length as seed. Real MB units use a far more complex,
    secret routine - replace per module.
    """
    val = int.from_bytes(seed, "big")
    mask = int.from_bytes(b"\x5a" * len(seed), "big")
    key = ((val ^ mask) + level) & ((1 << (8 * len(seed))) - 1)
    return key.to_bytes(len(seed), "big")
