#!/bin/sh
# Installiert Liloport für den aktuellen Benutzer – ohne Administratorrechte.
# Aufruf im entpackten Ordner:  ./installieren.sh
# Danach: «Liloport» im Programm-Menü und (falls vorhanden) als Symbol auf dem Schreibtisch.
# Deine Inhalte (Ordner ~/Liloport) werden nicht angefasst.
set -eu

HIER="$(cd "$(dirname "$0")" && pwd)"
DATEN="${XDG_DATA_HOME:-$HOME/.local/share}"
ZIEL="$DATEN/liloport-programm"
APPS="$DATEN/applications"
ICONS="$DATEN/icons/hicolor"
BIN="$HOME/.local/bin"

if [ ! -x "$HIER/app/liloport" ]; then
  echo "Fehler: $HIER/app/liloport fehlt. Bitte im entpackten Ordner ausführen." >&2
  exit 1
fi

if pgrep -x liloport >/dev/null 2>&1; then
  echo "Liloport läuft gerade. Bitte zuerst beenden (Fenster «Liloport» → Beenden) und dann erneut ausführen." >&2
  exit 1
fi

echo "Installiere Liloport nach $ZIEL …"
rm -rf "$ZIEL"
mkdir -p "$ZIEL" "$APPS" "$BIN" "$ICONS/256x256/apps" "$ICONS/512x512/apps" "$ICONS/48x48/apps"
cp -R "$HIER/app/." "$ZIEL/"
cp "$HIER/icons/liloport-256.png" "$ICONS/256x256/apps/liloport.png"
cp "$HIER/icons/liloport-512.png" "$ICONS/512x512/apps/liloport.png"
cp "$HIER/icons/liloport-48.png" "$ICONS/48x48/apps/liloport.png"
cp "$HIER/deinstallieren.sh" "$ZIEL/deinstallieren.sh"
chmod +x "$ZIEL/liloport" "$ZIEL/deinstallieren.sh"
ln -sf "$ZIEL/liloport" "$BIN/liloport"

STARTER="$APPS/liloport.desktop"
cat > "$STARTER" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Liloport
GenericName=Portfolio-Wiki
Comment=Portfolio-Wiki für lebenslanges Lernen
Exec="$ZIEL/liloport"
Icon=liloport
Terminal=false
Categories=Education;Office;
Keywords=Portfolio;Wiki;Lernen;
StartupNotify=true
StartupWMClass=Liloport
EOF
chmod +x "$STARTER"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$ICONS" >/dev/null 2>&1 || true

# Symbol auf dem Schreibtisch (Desktop), sofern es diesen Ordner gibt
SCHREIBTISCH="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
[ -n "$SCHREIBTISCH" ] || SCHREIBTISCH="$HOME/Desktop"
if [ -d "$SCHREIBTISCH" ] && [ "$SCHREIBTISCH" != "$HOME" ]; then
  cp "$STARTER" "$SCHREIBTISCH/liloport.desktop"
  chmod +x "$SCHREIBTISCH/liloport.desktop"
  # GNOME: als vertrauenswürdig markieren, damit ein Doppelklick startet
  command -v gio >/dev/null 2>&1 && gio set "$SCHREIBTISCH/liloport.desktop" metadata::trusted true >/dev/null 2>&1 || true
  echo "Desktop-Symbol: $SCHREIBTISCH/liloport.desktop"
fi

echo "Fertig. Liloport im Programm-Menü oder über das Desktop-Symbol starten."
echo "(Unter GNOME beim ersten Doppelklick auf das Desktop-Symbol ggf. «Start erlauben» wählen.)"
echo "Deinstallieren: $ZIEL/deinstallieren.sh"
