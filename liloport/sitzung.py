"""Einstellungen pro Gerät und Warnung, wenn zwei Geräte gleichzeitig im selben Inhalte-Ordner arbeiten.

Liegt der Inhalte-Ordner in einem Cloud-Ordner (OneDrive, iCloud, SWITCHdrive …), kann Liloport auf zwei
Geräten gleichzeitig laufen. Jede laufende Instanz schreibt darum regelmässig _wiki/sitzung.json mit
einer Geräte-Kennung. Findet eine Instanz dort ein anderes Gerät mit frischem Zeitstempel, warnt die
Oberfläche. Die Geräte-Kennung ist zufällig und liegt im Einstellungsordner des Geräts, nicht im
Inhalte-Ordner.
"""
import json
import os
import secrets
import socket
import sys
import threading
import time
from pathlib import Path

from .store import INTERN

FRISCH = 300      # Sekunden: so lange gilt ein anderes Gerät als «aktiv»
TAKT = 60         # Sekunden zwischen zwei Lebenszeichen


def einstellungs_ordner() -> Path:
    """Pro Benutzer und Gerät: %APPDATA%\\Liloport, ~/Library/Application Support/Liloport, ~/.config/liloport.

    Bewusst nicht im Programmordner: Ein installiertes Programm darf dort meist nicht schreiben.
    """
    if os.environ.get("LILOPORT_EINSTELLUNGEN"):
        ordner = Path(os.environ["LILOPORT_EINSTELLUNGEN"])
    elif sys.platform.startswith("win"):
        ordner = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "Liloport"
    elif sys.platform == "darwin":
        ordner = Path.home() / "Library" / "Application Support" / "Liloport"
    else:
        ordner = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "liloport"
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def geraete_id() -> str:
    datei = einstellungs_ordner() / "geraet.txt"
    try:
        gid = datei.read_text(encoding="utf-8").strip()
        if len(gid) == 16:
            return gid
    except OSError:
        pass
    gid = secrets.token_hex(8)
    datei.write_text(gid, encoding="utf-8")
    return gid


class Sitzung:
    """Lebenszeichen in _wiki/sitzung.json schreiben und fremde Geräte erkennen."""

    def __init__(self, root: Path):
        self.datei = Path(root) / INTERN / "sitzung.json"
        self.gid = geraete_id()
        self.name = (socket.gethostname() or "anderes Gerät")[:60]
        self.fremd = None
        self._stopp = threading.Event()

    def _lesen(self):
        try:
            return json.loads(self.datei.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def pruefen(self):
        """Gibt {name, zeit} eines anderen aktiven Geräts zurück oder None."""
        d = self._lesen()
        if isinstance(d, dict) and d.get("geraet") != self.gid and time.time() - float(d.get("zeit", 0)) < FRISCH:
            self.fremd = {"name": str(d.get("name") or "anderes Gerät"), "zeit": float(d.get("zeit", 0))}
        elif isinstance(d, dict) and d.get("geraet") == self.gid:
            pass  # unser eigenes Lebenszeichen: Warnung bleibt bis zum Ablauf bestehen
        if self.fremd and time.time() - self.fremd["zeit"] > FRISCH:
            self.fremd = None
        return self.fremd

    def schreiben(self):
        self.pruefen()
        try:
            self.datei.parent.mkdir(parents=True, exist_ok=True)
            self.datei.write_text(json.dumps({"geraet": self.gid, "name": self.name, "zeit": time.time()}), encoding="utf-8")
        except OSError:
            pass

    def starten(self):
        self.schreiben()

        def schleife():
            while not self._stopp.wait(TAKT):
                self.schreiben()
        threading.Thread(target=schleife, daemon=True).start()

    def beenden(self):
        self._stopp.set()
        d = self._lesen()
        if isinstance(d, dict) and d.get("geraet") == self.gid:
            try:
                self.datei.unlink()
            except OSError:
                pass

    def status(self) -> dict:
        f = self.pruefen()
        return {"fremd": {"name": f["name"], "vorSekunden": int(time.time() - f["zeit"])} if f else None}
