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

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PAYLOAD="$SCRIPT_DIR/payload/emi-guardian"
PLUGIN_ID="com.openai.kicad.emi-guardian"
if [[ ! -f "$PAYLOAD/plugin.json" ]]; then
  echo "Installer payload is incomplete: $PAYLOAD/plugin.json" >&2
  exit 1
fi
if command -v pgrep >/dev/null 2>&1 && { pgrep -x KiCad >/dev/null 2>&1 || pgrep -x pcbnew >/dev/null 2>&1; } && ((FORCE == 0)); then
  echo "Close KiCad and PCB Editor before installing. Use --force only after saving all boards." >&2
  exit 1
fi

PLUGINS_ROOT="$HOME/Documents/KiCad/$KICAD_VERSION/plugins"
DESTINATION="$PLUGINS_ROOT/emi-guardian"
LEGACY_BACKUP_ROOT="$PLUGINS_ROOT/_emi-guardian-backups"
CACHE="$HOME/Library/Caches/KiCad/$KICAD_VERSION/python-environments/$PLUGIN_ID"
TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/emi-guardian-install.XXXXXX")"
NEW_PAYLOAD="$TEMP_ROOT/new"

cleanup() { rm -rf "$TEMP_ROOT"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

mkdir -p "$PLUGINS_ROOT"
# Remove directories left by pre-v0.0.2 installers before any replacement.
# KiCad may scan every direct child of the plugin root on its next launch.
rm -rf "$LEGACY_BACKUP_ROOT"
find "$PLUGINS_ROOT" -maxdepth 1 -type d -name 'emi-guardian.installing-*' -exec rm -rf {} + 2>/dev/null || true
cp -R "$PAYLOAD" "$NEW_PAYLOAD"
rm -rf "$DESTINATION"
if ! cp -R "$NEW_PAYLOAD" "$DESTINATION"; then
  rm -rf "$DESTINATION"
  echo "Installation failed. No backup was created; correct the cause and run the installer again." >&2
  exit 1
fi
rm -rf "$CACHE"

echo "EMI Guardian was installed or updated successfully without creating a backup copy."
echo "Plugin: $DESTINATION"
echo "Start KiCad, enable Preferences > Plugins > Enable KiCad API, open a PCB, then use Tools > External Plugins > Open EMI Guardian."
read -r -p "Press Return to close..." _ || true
