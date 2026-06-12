#!/usr/bin/env sh
set -e

# Populate the /data volume on first run from the bundled seed, then (re)build
# the ECU database if needed. This keeps DATA in the volume (extensible) while
# the image stays code-only.

mkdir -p /data/cbf

# 1) Seed CBF library if the volume's cbf dir is empty
if [ -z "$(ls -A /data/cbf 2>/dev/null)" ] && [ -d /app/seed/cbf ]; then
    echo "[macDiag] seeding /data/cbf from bundled starter set..."
    cp /app/seed/cbf/* /data/cbf/ 2>/dev/null || true
fi

# 2) Seed unlock_db.json if absent
if [ ! -f /data/unlock_db.json ] && [ -f /app/seed/unlock_db.json ]; then
    cp /app/seed/unlock_db.json /data/unlock_db.json
fi

# 3) ECU database. Prefer the bundled seed DB (full 169-ECU catalog) so the
#    catalog stays rich out of the box. Rebuilding from /data/cbf is an explicit
#    step the user runs AFTER adding their own CBF library (see README) - we do
#    NOT auto-rebuild here, since the seed cbf set is only a small subset.
if [ ! -f /data/ecu_db.sqlite ]; then
    if [ -f /app/seed/ecu_db.sqlite ]; then
        echo "[macDiag] seeding ecu_db.sqlite (bundled catalog)"
        cp /app/seed/ecu_db.sqlite /data/ecu_db.sqlite
    elif [ -n "$(ls -A /data/cbf 2>/dev/null)" ]; then
        echo "[macDiag] no seed DB; building from /data/cbf ..."
        python /app/tools/build_ecu_db.py --dir /data/cbf --out /data/ecu_db.sqlite || true
    fi
fi

echo "[macDiag] data ready: cbf=$(ls /data/cbf 2>/dev/null | wc -l) files, db=$( [ -f /data/ecu_db.sqlite ] && echo yes || echo no )"
exec "$@"
