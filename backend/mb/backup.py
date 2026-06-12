"""
Pre-write backup journal for coding/adaptation writes.

Before /api/coding/write and /api/coding/apply touch an ECU, the CURRENT value
of the target identifier is read and appended here as a JSON line — so a bad
coding string can always be rolled back by hand. Append-only on purpose: the
journal is the safety net, it must never lose history.

Location: MACDIAG_BACKUP_FILE, or ./data/coding_backups.jsonl (the same /data
volume in Docker).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

PATH = Path(os.environ.get("MACDIAG_BACKUP_FILE")
            or Path(__file__).resolve().parent.parent.parent
            / "data" / "coding_backups.jsonl")


def record(**entry) -> dict:
    """Append one backup entry; report (not raise) journal IO problems."""
    entry = {"ts": round(time.time(), 3), **entry}
    try:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        with PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        entry["saved"] = True
    except OSError as e:
        entry["saved"] = False
        entry["save_error"] = str(e)
    return entry


def recent(limit: int = 50) -> list[dict]:
    """Last `limit` journal entries, newest first."""
    if not PATH.exists():
        return []
    lines = PATH.read_text(encoding="utf-8").splitlines()
    out = []
    for ln in reversed(lines[-limit:]):
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out
