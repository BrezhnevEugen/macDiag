#!/usr/bin/env bash
# Consolidate ALL macDiag-relevant payload out of a big Vediamo library into the
# Docker data volume, so you can then delete the original to free space.
#
#   tools/import_data.sh ~/Downloads/Vediamo            # -> ./data/{cbf,cff,smr}
#   tools/import_data.sh ~/Downloads/Vediamo ./data
#
# Layout produced under <dest> (default ./data):
#   cbf/   - *.cbf  (diagnostics + variant coding)            ~1 GB
#   cff/   - *.cff  (flash images, for the future flash mode)  ~7 GB  (preserves ECU subfolders)
#   smr/   - *.smr-d/*.smr-f (flash containers)                ~0.4 GB
#   ecu_db.sqlite - catalog rebuilt from cbf/
#
# After verifying the app works, free space with:  rm -rf <vediamo root>
set -e

SRC="${1:?usage: import_data.sh <vediamo root> [dest=./data]}"
DEST="${2:-./data}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$DEST/cbf" "$DEST/cff" "$DEST/smr"

have_rsync() { command -v rsync >/dev/null 2>&1; }

echo "[import] CBF (*.cbf) -> $DEST/cbf (flat) ..."
find "$SRC" -type f -iname '*.cbf' -print0 | while IFS= read -r -d '' f; do
    cp -n "$f" "$DEST/cbf/$(basename "$f")" 2>/dev/null || true
done

echo "[import] CFF (*.cff) -> $DEST/cff (keeping ECU subfolders) ..."
if have_rsync; then
    rsync -a --include='*/' --include='*.cff' --include='*.CFF' --exclude='*' \
          "$SRC"/ "$DEST/cff"/
else
    find "$SRC" -type f -iname '*.cff' -print0 | while IFS= read -r -d '' f; do
        rel="${f#$SRC/}"
        mkdir -p "$DEST/cff/$(dirname "$rel")"
        cp -n "$f" "$DEST/cff/$rel" 2>/dev/null || true
    done
fi

echo "[import] SMR (*.smr-d/*.smr-f) -> $DEST/smr (flat) ..."
find "$SRC" -type f \( -iname '*.smr-d' -o -iname '*.smr-f' \) -print0 | while IFS= read -r -d '' f; do
    cp -n "$f" "$DEST/smr/$(basename "$f")" 2>/dev/null || true
done

echo "[import] rebuilding catalog from cbf/ ..."
python3 "$ROOT/tools/build_ecu_db.py" --dir "$DEST/cbf" --out "$DEST/ecu_db.sqlite"

echo "[import] done:"
echo "    cbf: $(find "$DEST/cbf" -iname '*.cbf' | wc -l | tr -d ' ')  |  cff: $(find "$DEST/cff" -iname '*.cff' | wc -l | tr -d ' ')  |  smr: $(find "$DEST/smr" -type f | wc -l | tr -d ' ')"
echo "Verify the app, THEN free space:  rm -rf \"$SRC\""
