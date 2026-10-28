#!/bin/sh
# Entfernt das Programm Liloport. Deine Inhalte (~/Liloport) und Einstellungen (~/.config/liloport) bleiben.
set -eu

DATEN="${XDG_DATA_HOME:-$HOME/.local/share}"
ZIEL="$DATEN/liloport-programm"

if pgrep -x liloport >/dev/null 2>&1; then
  echo "Liloport läuft gerade. Bitte zuerst beenden." >&2
  exit 1
fi

rm -f "$DATEN/applications/liloport.desktop" "$HOME/.local/bin/liloport"
for g in 48x48 256x256 512x512; do rm -f "$DATEN/icons/hicolor/$g/apps/liloport.png"; done
SCHREIBTISCH="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
[ -n "$SCHREIBTISCH" ] || SCHREIBTISCH="$HOME/Desktop"
rm -f "$SCHREIBTISCH/liloport.desktop"
rm -rf "$ZIEL"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATEN/applications" >/dev/null 2>&1 || true
echo "Liloport wurde entfernt. Deine Inhalte im Ordner ~/Liloport sind unverändert."
