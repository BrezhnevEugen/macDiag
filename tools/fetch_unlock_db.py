#!/usr/bin/env python3
"""
Download the UnlockECU seed-key definition database (MIT, ~1.4MB).

This file contains reverse-engineered, reimplemented security definitions with
NO proprietary blobs. It maps each ECU to its seed-key provider + constants and
is consumed by backend/mb/unlock.py.

    python tools/fetch_unlock_db.py
"""

import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/jglim/UnlockECU/main/UnlockECU/db.json"
OUT = Path(__file__).resolve().parent.parent / "backend" / "mb" / "unlock_db.json"


def main():
    print(f"downloading {URL}")
    urllib.request.urlretrieve(URL, OUT)
    print(f"saved -> {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
