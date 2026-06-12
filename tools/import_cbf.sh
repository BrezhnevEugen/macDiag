#!/usr/bin/env bash
# Deprecated: use tools/import_data.sh (imports CBF + CFF + SMR into the volume).
exec "$(dirname "$0")/import_data.sh" "$@"
