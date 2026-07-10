"""Append-only audit journal for ECU-changing operations.

This log records the operation, target and outcome of every guarded write path.
It complements ``coding_backups.jsonl``: backups contain recoverable old/new
coding bytes, while this journal also covers DTC clear and blocked/failed writes.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

PATH = Path(os.environ.get("MACDIAG_AUDIT_FILE")
            or Path(__file__).resolve().parent.parent.parent
            / "data" / "action_audit.jsonl")


def record(**entry) -> dict:
    """Append one action event without ever breaking the diagnostic operation."""
    entry = {"id": str(uuid.uuid4()), "ts": round(time.time(), 3), **entry}
    try:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        with PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        entry["saved"] = True
    except (OSError, TypeError, ValueError) as e:
        entry["saved"] = False
        entry["save_error"] = str(e)
    return entry


def recent(limit: int = 100) -> list[dict]:
    """Return newest events first, bounded for API/UI use."""
    limit = max(0, min(int(limit), 500))
    if limit == 0 or not PATH.exists():
        return []
    try:
        lines = PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in reversed(lines[-limit:]):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out
