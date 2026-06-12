#!/usr/bin/env bash
# Prepare the Docker seed dataset (bundled into the image as a starter set).
# Run once before `docker compose up --build` if docker/seed/ is empty
# (the seed is gitignored because it is derived from proprietary MB CBF data).
#
#   tools/prepare_seed.sh /path/to/VediamoData
#
# Produces:
#   docker/seed/ecu_db.sqlite   - full catalog built from ALL CBFs in the dir
#   docker/seed/cbf/*.cbf       - curated module CBFs for out-of-box coding
set -e

SRC="${1:?usage: prepare_seed.sh <vediamo CBF dir>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SEED="$ROOT/docker/seed"
mkdir -p "$SEED/cbf"

echo "[seed] building catalog DB from $SRC ..."
python3 "$ROOT/tools/build_ecu_db.py" --dir "$SRC" --out "$SEED/ecu_db.sqlite"

echo "[seed] copying curated module CBFs ..."
CORE="EZS164 KI164 SAMV164 SAMH164 KLA164 TCM164 ZGW164 MRM164 RBS164 \
FSCM164HY ME97 ME272 CRD3 ESP9MFA EIS447 IC_204 EPS218 FSCM221"
for n in $CORE; do
  for ext in cbf CBF; do
    f=$(find "$SRC" -iname "$n.$ext" -print -quit 2>/dev/null || true)
    [ -n "$f" ] && cp "$f" "$SEED/cbf/" && break
  done
done
echo "[seed] done: $(ls "$SEED/cbf" | wc -l) CBFs, DB $(du -h "$SEED/ecu_db.sqlite" | cut -f1)"
