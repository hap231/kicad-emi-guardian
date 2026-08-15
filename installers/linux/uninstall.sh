#!/usr/bin/env bash
set -euo pipefail

KICAD_VERSION="10.0"
FORCE=0
while (($#)); do
  case "$1" in
    --kicad-version) KICAD_VERSION="${2:?missing version}"; shift 2 ;;
    --force) FORCE=1; shift ;;
    -h|--help) echo "Usage: $0 [--kicad-version 10.0] [--force]"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done
if command -v pgrep >/dev/null 2>&1 && { pgrep -x kicad >/dev/null 2>&1 || pgrep -x pcbnew >/dev/null 2>&1; } && ((FORCE == 0)); then
  echo "Close KiCad and PCB Editor before uninstalling. Use --force only after saving all boards." >&2
  exit 1
fi

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
PLUGINS_ROOT="$DATA_HOME/KiCad/$KICAD_VERSION/plugins"
DESTINATION="$PLUGINS_ROOT/emi-guardian"
LEGACY_BACKUP_ROOT="$PLUGINS_ROOT/_emi-guardian-backups"
CACHE="$CACHE_HOME/KiCad/$KICAD_VERSION/python-environments/com.openai.kicad.emi-guardian"
rm -rf "$DESTINATION" "$CACHE" "$LEGACY_BACKUP_ROOT"
find "$PLUGINS_ROOT" -maxdepth 1 -type d -name 'emi-guardian.installing-*' -exec rm -rf {} + 2>/dev/null || true

echo "EMI Guardian was uninstalled. Persistent settings and exported reports were not removed."
