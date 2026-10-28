#!/usr/bin/env python3
"""Liloport-Server: startet den lokalen Editiermodus (http://127.0.0.1:8000).

Aufruf:  python server.py [Inhalte-Ordner] [--port 8000] [--kein-browser]
Ohne Angabe wird der zuletzt verwendete Ordner genommen (config.json im Einstellungsordner des
Benutzers), sonst ~/Liloport. Läuft Liloport schon, öffnet ein zweiter Start nur das Dashboard.
"""
import argparse
import json
import mimetypes
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

PROGRAMM = Path(__file__).resolve().parent
sys.path.insert(0, str(PROGRAMM))
# Als fertiges Programm (PyInstaller) liegt config.json neben der ausführbaren Datei
PROGRAMM_ORDNER = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else PROGRAMM
# Mitgelieferte Dateien (static/, templates/ …): beim fertigen Programm im Bundle von PyInstaller
PROGRAMM_DATEN = Path(getattr(sys, "_MEIPASS", PROGRAMM))

from liloport import beispiel, kompetenzen, links, sanitize  # noqa: E402
from liloport.kompetenzen import Kompetenzen  # noqa: E402
from liloport.assets import Assets  # noqa: E402
from liloport.backup import Backup  # noqa: E402
from liloport.export import Exporter  # noqa: E402
from liloport.history import History  # noqa: E402
from liloport.importer import Importer  # noqa: E402
from liloport.kommentare import Kommentare  # noqa: E402
from liloport.suche import Suche  # noqa: E402
from liloport.render import seite_html  # noqa: E402
from liloport.render import Renderer  # noqa: E402
from liloport.sitzung import Sitzung, einstellungs_ordner  # noqa: E402
from liloport.store import MENUE_OPTIONEN, Store, StoreFehler  # noqa: E402
from liloport.render import produkt_laden, version_anzeige  # noqa: E402

STANDARD_PORT = 8000


def config_datei() -> Path:
    """config.json liegt im Einstellungsordner des Benutzers (beschreibbar, auch bei installiertem Programm)."""
    return einstellungs_ordner() / "config.json"


def inhalte_ordner(argument) -> Path:
    """Ermittelt den Inhalte-Ordner: Argument > config.json > ~/Liloport; merkt ihn in config.json."""
    config = config_datei()
    alt = PROGRAMM_ORDNER / "config.json"  # frühere Versionen: neben server.py
    if not config.exists() and alt.exists():
        try:
            config.write_text(alt.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            pass
    if argument:
        ordner = Path(argument).expanduser().resolve()
    elif config.exists():
        try:
            ordner = Path(json.loads(config.read_text(encoding="utf-8"))["inhalte"]).expanduser()
        except (ValueError, KeyError):
            ordner = Path.home() / "Liloport"
    else:
        ordner = Path.home() / "Liloport"
    try:
        config.write_text(json.dumps({"inhalte": str(ordner)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
    return ordner


def laufendes_liloport(port: int):
    """Antwortet auf 127.0.0.1:port bereits ein Liloport? Gibt dann dessen Inhalte-Ordner zurück."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=1.5) as r:
            daten = json.loads(r.read().decode("utf-8"))
        return daten.get("ordner") if daten.get("liloport") else None
    except Exception:  # noqa: BLE001 – kein Server oder etwas anderes auf dem Port
        return None


def ordner_oeffnen(pfad: Path):
    """Öffnet einen Ordner im Dateimanager des Betriebssystems."""
    import subprocess
    if sys.platform.startswith("win"):
        os.startfile(str(pfad))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(pfad)])
    else:
        subprocess.Popen(["xdg-open", str(pfad)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class LiloportServer(ThreadingHTTPServer):
    """HTTP-Server nur für 127.0.0.1. Unter Windows ohne SO_REUSEADDR: Dort erlaubte die Option, einen Port
    zu belegen, den schon ein anderes Programm benutzt."""
    allow_reuse_address = not sys.platform.startswith("win")
    daemon_threads = True


def server_oeffnen(start: int):
    """Öffnet den ersten Port ab `start`, der sich wirklich belegen lässt (Bind statt Verbindungsversuch:
    schneller unter Windows und richtig auch bei Ports, die das System reserviert hat)."""
    for port in range(start, start + 50):
        try:
            return LiloportServer(("127.0.0.1", port), Handler)
        except OSError:
            continue
    raise StartFehler(f"Kein freier Port zwischen {start} und {start + 49} gefunden. Läuft ein anderes Programm auf diesen Ports?")


BREITEN = ("voll", "halb", "klein")
AUSRICHTUNGEN = ("links", "mitte", "rechts")
_BREITE_FREI = re.compile(r"^\d{1,4}(px|%)$")


def _klapp(b: dict, neu: dict) -> dict:
    """Übernimmt die Einstellung «auf der Seite einklappbar» (offen/zu) samt Titel."""
    klapp = b.get("klapp")
    if klapp in ("offen", "zu"):
        neu["klapp"] = klapp
        neu["klappTitel"] = str(b.get("klappTitel") or "")[:120]
    return neu


def bloecke_pruefen(bloecke, ids=None, tiefe=0) -> list:
    """Validiert und filtert die Blöcke einer Seite (text, trenner, bild, video, pdf, spalten, html)."""
    if not isinstance(bloecke, list):
        raise StoreFehler("Blöcke müssen eine Liste sein.")
    ids = ids if ids is not None else set()
    ergebnis = []
    for n, b in enumerate(bloecke, 1):
        if not isinstance(b, dict):
            raise StoreFehler("Ungültiger Block.")
        typ = b.get("typ", "text")
        bid = str(b.get("id") or f"b{n}")[:40]
        while bid in ids:
            bid += "x"
        ids.add(bid)
        if typ == "text":
            ergebnis.append({"id": bid, "typ": "text", "html": sanitize.filtern(b.get("html", ""), "profi")})
        elif typ == "trenner":
            ergebnis.append({"id": bid, "typ": "trenner"})
        elif typ in ("bild", "video", "pdf", "datei"):
            asset = str(b.get("asset") or "")
            if asset and not re.fullmatch(r"[0-9a-f]{8}", asset):
                raise StoreFehler("Ungültige Anhang-ID.")
            neu = {"id": bid, "typ": typ, "asset": asset}
            if typ == "bild":
                breite = str(b.get("breite") or "voll")
                if breite not in BREITEN and not _BREITE_FREI.match(breite):
                    breite = "voll"
                neu["bildtext"] = str(b.get("bildtext") or "")[:300]
                neu["breite"] = breite
                neu["ausrichtung"] = b.get("ausrichtung") if b.get("ausrichtung") in AUSRICHTUNGEN else "links"
            if typ == "pdf":
                try:
                    neu["hoehe"] = max(200, min(2000, int(b.get("hoehe") or 600)))
                except (TypeError, ValueError):
                    neu["hoehe"] = 600
                try:
                    seite = int(b.get("seite") or 1)
                except (TypeError, ValueError):
                    seite = 1
                if seite > 1:
                    neu["seite"] = min(seite, 99999)   # PDF öffnet auf dieser Seite
            ergebnis.append(neu)
        elif typ == "spalten":
            if tiefe > 0:
                raise StoreFehler("Spalten können nicht verschachtelt werden.")
            spalten = b.get("spalten") or [[], []]
            if not isinstance(spalten, list) or not 2 <= len(spalten) <= 4:
                raise StoreFehler("Spalten-Block braucht 2 bis 4 Spalten.")
            ergebnis.append({"id": bid, "typ": "spalten",
                             "spalten": [bloecke_pruefen(sp, ids, tiefe + 1) for sp in spalten]})
        elif typ == "html":
            ergebnis.append({"id": bid, "typ": "html", "html": str(b.get("html") or "")})
        elif typ == "kr":
            ergebnis.append(kompetenzen.block_pruefen(b, bid))
        elif typ == "button":
            ziel = str(b.get("ziel") or "").strip()[:2000]
            if re.match(r"(?i)^\s*(javascript|data|vbscript):", ziel):
                ziel = ""
            ergebnis.append({"id": bid, "typ": "button", "text": str(b.get("text") or "")[:120], "ziel": ziel,
                             "stil": b.get("stil") if b.get("stil") in ("voll", "umrandet") else "voll",
                             "ausrichtung": b.get("ausrichtung") if b.get("ausrichtung") in AUSRICHTUNGEN else "links"})
        else:
            raise StoreFehler(f"Blocktyp «{typ}» ist nicht verfügbar.")
        ergebnis[-1] = _klapp(b, ergebnis[-1])
    return ergebnis


class Handler(BaseHTTPRequestHandler):
    """Beantwortet /api/… als JSON und liefert alle anderen Pfade aus dem Inhalte-Ordner."""

    store: Store = None
    renderer: Renderer = None
    assets: Assets = None
    history: History = None
    backup: Backup = None
    exporter: Exporter = None
    kommentare: Kommentare = None
    importer: Importer = None
    sitzung: Sitzung = None
    kompetenzen: Kompetenzen = None
    beenden = None          # Funktion, die Liloport beendet (Knopf «Beenden» in der Leiste)
    letzte_speicherung = {}  # pfad -> (Editor-Kennung, geaendert) der letzten Speicherung aus dem Editor
    leise = False           # installiertes Programm: nicht jede Anfrage protokollieren
    protocol_version = "HTTP/1.1"

    laufende_anfragen = {}  # Thread-ID -> (Start, Methode, Pfad); für den Wächter bei Hängern

    def handle_one_request(self):
        """Wie üblich, misst aber die Dauer: Langsame Anfragen landen im Protokoll (Fehlersuche bei Hängern)."""
        start = time.monotonic()
        tid = threading.get_ident()
        Handler.laufende_anfragen[tid] = (start, "", "")
        try:
            super().handle_one_request()
        finally:
            Handler.laufende_anfragen.pop(tid, None)
            dauer = time.monotonic() - start
            if dauer > 5 and getattr(self, "command", None):
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} langsame Anfrage: {self.command} {self.path} – {dauer:.1f} s")

    def parse_request(self):
        ok = super().parse_request()
        if ok:
            Handler.laufende_anfragen[threading.get_ident()] = (time.monotonic(), self.command, self.path)
        return ok

    # ---------- Hilfen ----------

    def log_message(self, fmt, *args):
        """Kürzeres Protokoll ohne Zeitstempel-Rauschen."""
        if self.leise or sys.stderr is None:
            return
        sys.stderr.write("  %s\n" % (fmt % args))

    def _json(self, daten, status=200):
        """Sendet eine JSON-Antwort."""
        body = json.dumps(daten, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        """Sicherheits-Header für jede Antwort."""
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "frame-ancestors 'self'")
        super().end_headers()

    def _zugriff_erlaubt(self) -> bool:
        """Schützt die lokale API vor fremden Webseiten.

        - Host-Prüfung gegen DNS-Rebinding: nur 127.0.0.1:<port> und localhost:<port>.
        - Bei schreibenden Anfragen: keine Anfrage von einer anderen Website (Origin / Sec-Fetch-Site).
        """
        port = self.server.server_address[1]
        erlaubt = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.close_connection = self.close_connection or self.command != "GET"
        if (self.headers.get("Host") or "").lower() not in erlaubt:
            self._fehler("Ungültiger Host.", 403)
            return False
        if self.command in ("POST", "PUT", "DELETE"):
            herkunft = self.headers.get("Origin")
            if herkunft and herkunft.lower() not in {"http://" + h for h in erlaubt}:
                self._fehler("Anfrage von fremder Website abgelehnt.", 403)
                return False
            if (self.headers.get("Sec-Fetch-Site") or "same-origin") not in ("same-origin", "none"):
                self._fehler("Anfrage von fremder Website abgelehnt.", 403)
                return False
        return True

    def _fehler(self, meldung, status=400):
        """Sendet eine Fehlermeldung als JSON."""
        self._json({"fehler": meldung}, status)

    def _body(self) -> dict:
        """Liest den JSON-Body der Anfrage."""
        laenge = int(self.headers.get("Content-Length") or 0)
        if laenge > 20_000_000:
            raise StoreFehler("Anfrage zu gross.")
        roh = self.rfile.read(laenge) if laenge else b"{}"
        try:
            daten = json.loads(roh.decode("utf-8") or "{}")
        except ValueError:
            raise StoreFehler("Ungültiges JSON.")
        if not isinstance(daten, dict):
            raise StoreFehler("Erwartet ein JSON-Objekt.")
        return daten

    def _route(self):
        """Zerlegt den Pfad in Segmente, z. B. /api/seiten/a/b -> ['api','seiten','a','b']; merkt die Query."""
        geparst = urlparse(self.path)
        self.query = {k: v[0] for k, v in parse_qs(geparst.query).items()}
        pfad = unquote(geparst.path)
        return [s for s in pfad.split("/") if s], pfad

    # ---------- HTTP-Methoden ----------

    def do_GET(self):
        if not self._zugriff_erlaubt():
            return
        teile, pfad = self._route()
        try:
            if teile[:1] == ["api"]:
                return self._api_get(teile[1:])
            if teile[:1] == ["_vorschau"] and len(teile) >= 3:
                return self._vorschau(teile[1:])
            return self._datei(pfad)
        except StoreFehler as e:
            self._fehler(str(e))

    def do_POST(self):
        if not self._zugriff_erlaubt():
            return
        teile, _ = self._route()
        try:
            if teile[:1] != ["api"]:
                return self._fehler("Nicht gefunden.", 404)
            if teile[1:2] == ["upload"] and len(teile) >= 4:
                return self._upload(teile[2:])
            if teile[1:] == ["import-kommentare"] and self.headers.get("X-Dateiname"):
                return self._import_datei()
            if teile[1:] == ["kompetenzrahmen", "import"]:
                laenge = int(self.headers.get("Content-Length") or 0)
                if laenge > 20_000_000:
                    raise StoreFehler("Datei zu gross.")
                kr = self.kompetenzen.importieren(self.rfile.read(laenge), unquote(self.headers.get("X-Dateiname") or ""))
                self.renderer.alles_schreiben()
                return self._json({"ok": True, "id": kr["id"], "rahmen": kr})
            if teile[1:] == ["import", "vorschau"]:
                return self._import_vorschau()
            self._api_post(teile[1:], self._body())
        except StoreFehler as e:
            self._fehler(str(e))

    def do_PUT(self):
        if not self._zugriff_erlaubt():
            return
        teile, _ = self._route()
        try:
            if teile[:1] != ["api"]:
                return self._fehler("Nicht gefunden.", 404)
            self._api_put(teile[1:], self._body())
        except StoreFehler as e:
            self._fehler(str(e))

    def do_DELETE(self):
        if not self._zugriff_erlaubt():
            return
        teile, _ = self._route()
        try:
            if teile[:1] != ["api"]:
                return self._fehler("Nicht gefunden.", 404)
            self._api_delete(teile[1:])
        except StoreFehler as e:
            self._fehler(str(e))

    # ---------- statische Dateien ----------

    def _datei(self, pfad: str):
        """Liefert eine Datei aus dem Inhalte-Ordner; / ist das Dashboard."""
        if pfad in ("", "/"):
            pfad = "/index.html"
        ziel = self.store.sicherer_pfad(pfad)
        if ziel.is_dir():
            ziel = ziel / "index.html"
        if not ziel.is_file():
            return self._fehler("Nicht gefunden.", 404)
        typ = mimetypes.guess_type(str(ziel))[0] or "application/octet-stream"
        if typ.startswith("text/") or typ in ("application/javascript", "application/json"):
            typ += "; charset=utf-8"
        groesse = ziel.stat().st_size
        # Teilbereiche (Range): Videos lassen sich so spulen, ohne die ganze Datei zu laden; Safari braucht das
        # sogar zum Abspielen. Nur ein Bereich pro Anfrage (mehr verlangen Browser für Medien nicht).
        anfang, ende = 0, groesse - 1
        bereich = re.fullmatch(r"bytes=(\d*)-(\d*)", (self.headers.get("Range") or "").strip())
        if bereich and (bereich.group(1) or bereich.group(2)):
            if bereich.group(1):
                anfang = int(bereich.group(1))
                if bereich.group(2):
                    ende = min(int(bereich.group(2)), groesse - 1)
            else:   # «bytes=-500»: die letzten 500 Bytes
                anfang = max(0, groesse - int(bereich.group(2)))
            if anfang >= groesse or anfang > ende:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{groesse}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {anfang}-{ende}/{groesse}")
        else:
            self.send_response(200)
        laenge = ende - anfang + 1 if groesse else 0
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(laenge))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        if ziel.suffix.lower() == ".svg":
            # Hochgeladene SVGs könnten Skript enthalten; direkt aufgerufen läuft es so nie.
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox")
        self.end_headers()
        try:
            with open(ziel, "rb") as f:  # stückweise, damit auch sehr grosse Videos gehen
                f.seek(anfang)
                rest = laenge
                while rest > 0:
                    stueck = f.read(min(1024 * 1024, rest))
                    if not stueck:
                        break
                    self.wfile.write(stueck)
                    rest -= len(stueck)
        except (ConnectionError, TimeoutError):
            # Browser hat abgebrochen (z. B. beim Spulen im Video oder Seitenwechsel): kein Fehler
            self.close_connection = True

    # ---------- API ----------

    def _api_get(self, teile):
        if teile == ["ping"]:
            return self._json({"liloport": True, "version": produkt_laden().get("version", ""), "ordner": str(self.store.root)})
        if teile == ["sitzung"]:
            return self._json(self.sitzung.status() if self.sitzung else {"fremd": None})
        if teile == ["site"]:
            daten = self.renderer.menue_schreiben()
            daten["ordner"] = str(self.store.root)
            daten["beispielGefragt"] = bool(self.store.site_laden().get("beispielGefragt"))
            return self._json(daten)
        if teile[:1] == ["seiten"] and len(teile) >= 3:
            pfad = "/".join(teile[1:])
            return self._json({"pfad": pfad, "seite": self.store.seite_laden(pfad)})
        if teile == ["assets"]:
            return self._json({"assets": self.assets.liste(), "verwaist": [e["id"] for e in self.assets.verwaist()]})
        if teile[:1] == ["loeschvorschau"] and len(teile) >= 3:
            return self._json(self.assets.loesch_vorschau("/".join(teile[1:])))
        if teile[:1] == ["verlauf"] and len(teile) >= 3:
            pfad = "/".join(teile[1:])
            if self.query.get("v"):
                return self._json({"seite": self.history.laden(pfad, self.query["v"])})
            return self._json({"versionen": self.history.versionen(pfad)})
        if teile == ["papierkorb"]:
            return self._json({"eintraege": self.history.papierkorb()})
        if teile == ["backup"]:
            return self._json(self.backup.status())
        if teile == ["export-einstellungen"]:
            e = dict(self.store.site_laden().get("export", {}))
            e.setdefault("autor", ""); e.setdefault("id", ""); e.setdefault("autorAnzeigen", bool(e.get("autor"))); e.setdefault("idAnzeigen", False)
            return self._json(e)
        if teile[:1] == ["kommentare"] and len(teile) >= 3:
            pfad = "/".join(teile[1:])
            return self._json({"kommentare": self.kommentare.laden(pfad)})
        if teile == ["exporte"]:
            return self._json({"exporte": self.kommentare.exporte()})
        if teile == ["kompetenzrahmen"]:
            return self._json({"rahmen": self.kompetenzen.liste()})
        if teile[:1] == ["kompetenzrahmen"] and len(teile) == 2:
            kr = self.kompetenzen.laden(teile[1])
            return self._json({"rahmen": kr, "index": kompetenzen.knoten_index(kr),
                               "status": {k: v["status"] for k, v in self.kompetenzen.status(teile[1]).items()}})
        self._fehler("Nicht gefunden.", 404)

    def _vorschau(self, teile):
        """Rendert eine alte Version einer Seite zur Ansicht (nicht gespeichert)."""
        pfad = "/".join(teile)
        fassung = self.history.laden(pfad, self.query.get("v", ""))
        text = seite_html(pfad, fassung, self.assets.laden())
        text = text.replace("<body ", "<body data-vorschau=\"1\" ", 1)
        # Relative Pfade so auflösen, als läge die Seite an ihrem echten Ort
        text = text.replace("<head>", f'<head><base href="/{pfad.rsplit("/", 1)[0]}/">', 1)
        daten = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(daten)))
        self.end_headers()
        self.wfile.write(daten)

    def _upload(self, teile):
        """Nimmt eine Datei als rohen Body entgegen (Header X-Dateiname) und legt sie ab."""
        pfad = "/".join(teile)
        laenge = int(self.headers.get("Content-Length") or 0)
        name = unquote(self.headers.get("X-Dateiname") or "datei")
        eintrag = self.assets.hochladen_strom(pfad, name, self.rfile, laenge)  # kein Grössenlimit
        self._json({"ok": True, "asset": eintrag})

    def _import_datei(self):
        """Importiert Kommentare aus einer hochgeladenen HTML- oder JSON-Datei."""
        laenge = int(self.headers.get("Content-Length") or 0)
        if laenge > 20_000_000:
            raise StoreFehler("Datei zu gross.")
        name = unquote(self.headers.get("X-Dateiname") or "")
        ergebnis = self.kommentare.importieren_aus_datei(name, self.rfile.read(laenge))
        self.renderer.alles_schreiben()
        self._json({"ok": True, **ergebnis})

    def _import_vorschau(self):
        """Nimmt eine Export-ZIP entgegen und beschreibt, was importiert würde."""
        laenge = int(self.headers.get("Content-Length") or 0)
        name = unquote(self.headers.get("X-Dateiname") or "export.zip")
        self._json({"ok": True, **self.importer.vorschau_strom(self.rfile, laenge, name)})

    def _api_post(self, teile, daten):
        if teile == ["beenden"]:
            if not self.beenden:
                raise StoreFehler("Liloport lässt sich hier nicht beenden.")
            self._json({"ok": True})
            threading.Thread(target=self.beenden, daemon=True).start()
            return None
        if teile == ["niveau"]:
            self.store.niveau_setzen(daten.get("niveau"))
            self.renderer.alles_schreiben()
            return self._json({"ok": True, "niveau": daten.get("niveau")})
        if teile == ["verzeichnisse"]:
            v = self.store.verzeichnis_anlegen(daten.get("name"), daten.get("eltern") or None,
                                               daten.get("inMenue", True))
            self.renderer.alles_schreiben()
            return self._json({"ok": True, "verzeichnis": v})
        if teile == ["seiten"]:
            menue = daten.get("menue", "voll")
            if menue not in MENUE_OPTIONEN:
                raise StoreFehler("Unbekannte Menü-Option.")
            bloecke = bloecke_pruefen(daten.get("bloecke") or [])
            pfad, seite = self.store.seite_anlegen(daten.get("titel"), daten.get("verzeichnis"),
                                                   menue, bloecke)
            self.assets.referenzen_setzen(pfad, seite)
            self.renderer.alles_schreiben()
            return self._json({"ok": True, "pfad": pfad, "seite": seite})
        if teile == ["kompetenzrahmen"]:
            kr = self.kompetenzen.anlegen(daten)
            self.renderer.alles_schreiben()
            return self._json({"ok": True, "id": kr["id"], "rahmen": kr})
        if teile[:1] == ["kr-status"] and len(teile) >= 3:
            # Status eines Knotens direkt auf der Seite umschalten (ohne Editor)
            pfad = "/".join(teile[1:])
            seite = self.store.seite_laden(pfad)
            treffer = None
            for b in kompetenzen.kr_bloecke(seite.get("bloecke")):
                if b.get("id") == daten.get("block"):
                    treffer = b
            if treffer is None or daten.get("status") not in kompetenzen.STATUS or daten.get("knoten") not in (treffer.get("knoten") or {}):
                raise StoreFehler("Block oder Knoten nicht gefunden.")
            self.history.sichern(pfad, seite)
            treffer["knoten"][daten["knoten"]] = daten["status"]
            seite = self.store.seite_aktualisieren(pfad, bloecke=seite["bloecke"])
            self.renderer.seite_schreiben(pfad, seite)
            self.renderer.kompetenzen_schreiben()
            return self._json({"ok": True, "status": {k: v["status"] for k, v in self.kompetenzen.status(treffer["rahmen"]).items()}})
        if teile == ["profil"]:
            site = self.store.site_laden()
            export = site.setdefault("export", {})
            export["autor"] = str(daten.get("autor") or "").strip()[:120]
            export["id"] = str(daten.get("id") or "").strip()[:60]
            self.store.site_speichern(site)
            return self._json({"ok": True, "profil": {"autor": export["autor"], "id": export["id"]}})
        if teile == ["beispiel"]:
            site = self.store.site_laden()
            site["beispielGefragt"] = True
            self.store.site_speichern(site)
            if not daten.get("anlegen"):
                return self._json({"ok": True})
            start = beispiel.anlegen(self.store, self.assets, self.kompetenzen)
            self.renderer.alles_schreiben()
            return self._json({"ok": True, "pfad": start})
        if teile == ["rendern"]:
            self.renderer.alles_schreiben()
            return self._json({"ok": True})
        if teile[:1] == ["seiten"] and len(teile) >= 4 and teile[-1] == "verschieben":
            pfad = "/".join(teile[1:-1])
            neu = self.store.seite_verschieben(pfad, str(daten.get("verzeichnis") or ""))
            links.pfade_umbenennen(self.store, pfad, neu)
            self.assets.pfade_umbenennen(pfad, neu)
            self.history.verschieben(pfad, neu)
            self.kommentare.pfade_umbenennen(pfad, neu)
            self.renderer.alles_schreiben()
            return self._json({"ok": True, "pfad": neu})
        if teile[:1] == ["verlauf"] and len(teile) >= 3:
            pfad = "/".join(teile[1:])
            seite = self.history.wiederherstellen(pfad, str(daten.get("v") or ""))
            self.assets.referenzen_setzen(pfad, seite)
            self.renderer.alles_schreiben()
            return self._json({"ok": True, "seite": seite})
        if teile[:1] == ["papierkorb"] and len(teile) == 2:
            pfad = self.history.aus_papierkorb(teile[1], self.assets)
            self.assets.referenzen_setzen(pfad, self.store.seite_laden(pfad))
            self.renderer.alles_schreiben()
            return self._json({"ok": True, "pfad": pfad})
        if teile == ["oeffnen"]:
            ziel = self.store.sicherer_pfad(str(daten.get("pfad") or ""))
            if not ziel.exists():
                raise StoreFehler("Ordner nicht gefunden.")
            ordner_oeffnen(ziel if ziel.is_dir() else ziel.parent)
            return self._json({"ok": True, "pfad": str(ziel)})
        if teile == ["backup"]:
            # Im Hintergrund: bei vielen Gigabyte dauert das erste Backup Minuten; das Dashboard zeigt den Fortschritt
            if daten.get("warten"):
                return self._json({"ok": True, **self.backup.erstellen()})
            self.backup.erstellen_hintergrund()
            return self._json({"ok": True, "laeuft": True})
        if teile == ["backup", "wiederherstellen"]:
            name, ziel = str(daten.get("name") or ""), str(daten.get("ziel") or "")
            if daten.get("warten"):
                return self._json({"ok": True, "ziel": self.backup.wiederherstellen(name, ziel)})
            return self._json({"ok": True, "laeuft": True, "ziel": self.backup.wiederherstellen_hintergrund(name, ziel)})
        if teile == ["backup", "ort"]:
            if self.backup.arbeit:
                raise StoreFehler("Bitte warten, bis das laufende Backup fertig ist.")
            return self._json({"ok": True, **self.backup.ort_setzen(str(daten.get("ordner") or ""))})
        if teile[:1] == ["export"] and len(teile) >= 3:
            return self._export("/".join(teile[1:]), daten)
        if teile == ["export-mehrere"]:
            return self._export(None, daten)
        if teile == ["import"]:
            pfad = self.importer.importieren(str(daten.get("token") or ""), str(daten.get("verzeichnis") or ""), daten.get("titel"))
            self.renderer.alles_schreiben()
            return self._json({"ok": True, "pfad": pfad})
        if teile == ["import-kommentare"]:
            ergebnis = self.kommentare.importieren_von_url(str(daten.get("url") or ""))
            self.renderer.alles_schreiben()
            return self._json({"ok": True, **ergebnis})
        self._fehler("Nicht gefunden.", 404)

    def _export(self, pfad, daten):
        """Baut die Export-ZIP und sendet sie als Download; merkt Autor-Einstellungen in site.json."""
        site = self.store.site_laden()
        export = site.setdefault("export", {})
        if "autor" in daten:
            export["autor"] = str(daten["autor"]).strip()[:120]
        if "id" in daten:
            export["id"] = str(daten["id"]).strip()[:60]
        export["autorAnzeigen"] = bool(daten.get("autorAnzeigen"))
        export["idAnzeigen"] = bool(daten.get("idAnzeigen"))
        export["datumAnzeigen"] = bool(daten.get("datumAnzeigen"))
        self.store.site_speichern(site)
        # Die ZIP entsteht in einer temporären Datei und wird stückweise gesendet: Ein ganzes Portfolio
        # mit Videos kann viele Gigabyte gross sein und passt nicht in den Arbeitsspeicher.
        with tempfile.TemporaryFile(prefix="liloport-export-") as datei:
            if pfad is None:
                name, _, zufall = self.exporter.exportieren_mehrere(str(daten.get("verzeichnis") or ""), daten, ziel=datei)
            else:
                name, _, zufall = self.exporter.exportieren(pfad, daten, ziel=datei)
            groesse = datei.seek(0, os.SEEK_END)
            datei.seek(0)
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
            self.send_header("X-Zufallsname", zufall)
            self.send_header("X-Moderation", self.exporter.moderation)
            self.send_header("Content-Length", str(groesse))
            self.end_headers()
            shutil.copyfileobj(datei, self.wfile, 1024 * 1024)

    def _api_put(self, teile, daten):
        if teile[:1] == ["kompetenzrahmen"] and len(teile) == 2:
            kr = self.kompetenzen.speichern(teile[1], daten)
            self.renderer.alles_schreiben()
            return self._json({"ok": True, "rahmen": kr, "status": {k: v["status"] for k, v in self.kompetenzen.status(teile[1]).items()}})
        if teile[:1] == ["verzeichnisse"] and len(teile) == 2:
            self.store.letzte_umbenennung = None
            v = self.store.verzeichnis_aendern(teile[1], daten.get("name"), daten.get("inMenue"))
            if self.store.letzte_umbenennung:
                links.pfade_umbenennen(self.store, *self.store.letzte_umbenennung)
                self.assets.pfade_umbenennen(*self.store.letzte_umbenennung)
                self.history.verschieben(*self.store.letzte_umbenennung)
                self.kommentare.pfade_umbenennen(*self.store.letzte_umbenennung)
            self.renderer.alles_schreiben()
            return self._json({"ok": True, "verzeichnis": v})
        if teile[:1] == ["seiten"] and len(teile) >= 3:
            pfad = "/".join(teile[1:])
            bloecke = bloecke_pruefen(daten["bloecke"]) if "bloecke" in daten else None
            css = str(daten["css"])[:100000] if "css" in daten else None
            vorher = self.store.seite_laden(pfad)
            # Konflikt: Die Seite wurde seit dem Öffnen im Editor anderswo geändert (zweites Gerät, Cloud-Sync).
            # Kein Konflikt, wenn die letzte Speicherung von genau diesem Editor stammt (z. B. sich überholende
            # Anfragen desselben Fensters).
            editor = str(daten.get("editor") or "")[:64]
            eigene = bool(editor) and self.letzte_speicherung.get(pfad) == (editor, vorher.get("geaendert"))
            if daten.get("basis") and daten["basis"] != vorher.get("geaendert") and not daten.get("erzwingen") and not eigene:
                return self._json({"fehler": "Diese Seite wurde inzwischen anderswo geändert.", "konflikt": True,
                                   "geaendert": vorher.get("geaendert")}, 409)
            self.history.sichern(pfad, vorher)
            seite = self.store.seite_aktualisieren(pfad, daten.get("titel"), daten.get("menue"), bloecke, css,
                                                   bool(daten["kommentare"]) if "kommentare" in daten else None,
                                                   daten.get("datum"), daten.get("tags"),
                                                   bool(daten["verweise"]) if "verweise" in daten else None)
            if editor:
                self.letzte_speicherung[pfad] = (editor, seite.get("geaendert"))
            self.assets.referenzen_setzen(pfad, seite)
            self.renderer.seite_schreiben(pfad, seite)
            # Rückverweise: Zielseiten neu schreiben, deren «Verlinkt von» sich geändert hat
            alt_ziele, neu_ziele = links.ziele(vorher), links.ziele(seite)
            betroffen = (alt_ziele | neu_ziele) if vorher.get("titel") != seite.get("titel") else (alt_ziele ^ neu_ziele)
            for ziel in betroffen - {pfad}:
                try:
                    self.renderer.seite_schreiben(ziel)
                except StoreFehler:
                    pass
            self.renderer.menue_schreiben()
            self.renderer.redirects_schreiben()
            if self.renderer.suche:
                self.renderer.suche.schreiben()
            # Kompetenz-Block geändert (Stand, Auswahl) oder Titel einer Seite mit Kompetenzbezug: Abbildung neu
            if any(kompetenzen.kr_bloecke(vorher.get("bloecke"))) or any(kompetenzen.kr_bloecke(seite.get("bloecke"))):
                self.renderer.kompetenzen_schreiben()
            return self._json({"ok": True, "pfad": pfad, "seite": seite})
        self._fehler("Nicht gefunden.", 404)

    def _api_delete(self, teile):
        if teile[:1] == ["kompetenzrahmen"] and len(teile) == 2:
            self.kompetenzen.loeschen(teile[1])
            self.renderer.alles_schreiben()
            return self._json({"ok": True})
        if teile[:1] == ["verzeichnisse"] and len(teile) == 2:
            self.store.verzeichnis_loeschen(teile[1])
            self.renderer.alles_schreiben()
            return self._json({"ok": True})
        if teile[:1] == ["seiten"] and len(teile) >= 3:
            pfad = "/".join(teile[1:])
            ordner = pfad.rsplit("/", 1)[0]
            vid = next((v["id"] for v in self.store.site_laden()["verzeichnisse"] if v["ordner"] == ordner), None)
            self.history.in_papierkorb(pfad, vid, self.assets)
            vorschau = self.assets.seite_loeschen(pfad)
            self.renderer.alles_schreiben()
            return self._json({"ok": True, "vorschau": vorschau})
        if teile[:1] == ["assets"] and len(teile) == 2:
            self.assets.loeschen(teile[1])
            self.renderer.alles_schreiben()
            return self._json({"ok": True})
        if teile[:1] == ["verzeichnisse"] and len(teile) >= 5 and teile[2] == "redirect":
            self.store.redirect_entfernen(teile[1], "/".join(teile[3:]))
            self.renderer.alles_schreiben()
            return self._json({"ok": True})
        if teile[:1] == ["papierkorb"] and len(teile) == 2:
            self.history.endgueltig(teile[1])
            return self._json({"ok": True})
        if teile[:1] == ["kommentare"] and len(teile) >= 3:
            pfad = "/".join(teile[1:])
            self.kommentare.loeschen(pfad, self.query.get("id"))
            self.renderer.seite_schreiben(pfad)
            return self._json({"ok": True})
        self._fehler("Nicht gefunden.", 404)


def einrichten(ordner):
    """Legt den Inhalte-Ordner an und verbindet alle Bausteine mit dem Handler."""
    store = Store(ordner)
    store.anlegen()
    assets = Assets(store)
    kommentare = Kommentare(store)
    komp = Kompetenzen(store)
    renderer = Renderer(store, assets, kommentare, Suche(store, assets, hintergrund=True), komp)
    t0 = time.monotonic()
    renderer.alles_schreiben()
    dauer = time.monotonic() - t0
    if dauer > 2:
        print(f"Seiten vorbereitet in {dauer:.1f} s")
    Handler.store = store
    Handler.renderer = renderer
    Handler.assets = assets
    Handler.history = History(store)
    Handler.backup = Backup(store)
    Handler.exporter = Exporter(store, assets, kommentare)
    Handler.kommentare = kommentare
    Handler.importer = Importer(store, assets, kommentare)
    Handler.kompetenzen = komp
    Handler.exporter.kompetenzen = komp
    return store


def lauf_datei() -> Path:
    """Port und Prozess des laufenden Liloport – damit ein zweiter Start es auch auf einem anderen Port findet."""
    return einstellungs_ordner() / "laufend.json"


def laufende_adresse():
    """Adresse eines schon laufenden Liloport laut laufend.json, sonst None. (Bewusst kein Probieren
    fester Ports: Unter Windows dauert ein Verbindungsversuch auf einen leeren Port rund zwei Sekunden.)"""
    try:
        port = int(json.loads(lauf_datei().read_text(encoding="utf-8"))["port"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return f"http://127.0.0.1:{port}/" if laufendes_liloport(port) else None


def protokoll_umleiten():
    """Installiertes Programm ohne Konsole: Ausgaben in liloport.log im Einstellungsordner (max. ca. 1 MB)."""
    try:
        datei = einstellungs_ordner() / "liloport.log"
        if datei.exists() and datei.stat().st_size > 1_000_000:
            datei.replace(datei.with_suffix(".log.1"))
        f = open(datei, "a", encoding="utf-8", buffering=1)
    except OSError:
        return None
    sys.stdout = sys.stderr = f
    return datei


def umgebung_fuer_programme():
    """PyInstaller setzt unter Linux LD_LIBRARY_PATH auf die eigenen Bibliotheken; Browser und Dateimanager,
    die Liloport startet, sollen aber die des Systems verwenden."""
    if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
        alt = os.environ.get("LD_LIBRARY_PATH_ORIG")
        if alt is not None:
            os.environ["LD_LIBRARY_PATH"] = alt
        else:
            os.environ.pop("LD_LIBRARY_PATH", None)


_KENNUNG = None


def windows_kennung_setzen():
    """Benannter Mutex «LiloportLaeuft»: Daran erkennt das Installationsprogramm (AppMutex), dass Liloport
    läuft, und bittet vor dem Aktualisieren oder Deinstallieren, es zu beenden."""
    global _KENNUNG
    if sys.platform.startswith("win"):
        try:
            import ctypes
            _KENNUNG = ctypes.windll.kernel32.CreateMutexW(None, False, "LiloportLaeuft")
        except (AttributeError, OSError):
            pass


def browser_oeffnen(adresse: str) -> bool:
    """Öffnet das Dashboard im Standardbrowser. Gibt False zurück, wenn das nicht ging – dann zeigt das
    Startfenster die Adresse zum Kopieren an.

    Ist der Standardbrowser kaputt oder deinstalliert, aber noch als Standard eingetragen, scheitert der
    normale Weg. Unter Windows versucht Liloport dann Microsoft Edge, das auf jedem Windows 10/11 vorhanden ist."""
    try:
        if webbrowser.open(adresse):
            return True
        print("Der Standardbrowser liess sich nicht öffnen.")
    except Exception as e:  # noqa: BLE001 – ohne Browser läuft Liloport trotzdem
        print(f"Der Standardbrowser liess sich nicht öffnen: {e}")
    if sys.platform.startswith("win"):
        try:
            os.startfile("msedge.exe", "open", adresse)  # type: ignore[attr-defined,call-arg]
            print("Dashboard stattdessen in Microsoft Edge geöffnet.")
            return True
        except (OSError, TypeError) as e:
            print(f"Auch Microsoft Edge liess sich nicht öffnen: {e}")
    print(f"Bitte diese Adresse von Hand in einem Browser öffnen: {adresse}")
    return False


def _hinweis_fenster(titel: str, text: str):
    """Kurze Meldung ohne Hauptfenster (installiertes Programm ohne Konsole)."""
    try:
        import tkinter as tk
        from tkinter import messagebox
        wurzel = tk.Tk()
        wurzel.withdraw()
        messagebox.showinfo(titel, text, parent=wurzel)
        wurzel.destroy()
    except Exception:  # noqa: BLE001 – ohne Anzeige bleibt die Zeile im Protokoll
        pass


class StartFehler(Exception):
    """Verständliche Fehlermeldung für den Start (erscheint im Fenster bzw. in der Konsole)."""


class Dienst:
    """Liloport als laufender Dienst: einrichten, Server starten, sauber beenden."""

    def __init__(self, ordner_argument, port: int):
        self.ordner_argument, self.wunschport = ordner_argument, port
        self.server, self.adresse, self.ordner = None, None, None
        self.beendet = threading.Event()
        self._lauf_eigen = False
        self._dient = False   # serve_forever läuft (sonst würde shutdown() ewig warten)

    def starten(self):
        """Richtet den Inhalte-Ordner ein und öffnet den Port. Gibt (adresse, ordner) zurück."""
        t0 = time.monotonic()
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} Liloport {produkt_laden().get('version', '')} startet")
        self.ordner = inhalte_ordner(self.ordner_argument)
        try:
            einrichten(self.ordner)
        except OSError as e:
            raise StartFehler(
                f"Liloport kann den Inhalte-Ordner nicht öffnen oder anlegen:\n{self.ordner}\n\n"
                "Ist der Ordner verschoben oder umbenannt, ein USB-Stick oder Netzlaufwerk nicht verbunden, "
                "oder fehlt die Berechtigung?\n\n"
                f"Technische Angabe: {e.strerror or e}\n"
                f"Der gewählte Ordner steht in {config_datei()}.") from e
        Handler.sitzung = Sitzung(Handler.store.root)
        Handler.sitzung.starten()
        Handler.beenden = self.beenden
        # Tägliches Backup im Hintergrund: Bei grossen Videos und PDFs dauert das Zippen Minuten,
        # das Dashboard soll trotzdem sofort aufgehen.
        threading.Thread(target=self._backup, args=(self.beendet,), name="backup-start", daemon=True).start()
        self.server = server_oeffnen(self.wunschport)
        port = self.server.server_address[1]
        self.adresse = f"http://127.0.0.1:{port}/"
        if not self.ordner_argument:
            try:
                lauf_datei().write_text(json.dumps({"port": port, "pid": os.getpid(), "ordner": str(self.ordner)}),
                                        encoding="utf-8")
                self._lauf_eigen = True
            except OSError:
                pass
        print(f"Liloport läuft: {self.adresse} (Start {time.monotonic() - t0:.1f} s)")
        print(f"Inhalte-Ordner: {self.ordner}")
        try:   # fürs Protokoll: ein volles Laufwerk erklärt viele seltsame Fehler
            platz = shutil.disk_usage(self.ordner)
            print(f"Freier Speicher auf diesem Laufwerk: {platz.free / 1024 ** 3:.1f} von {platz.total / 1024 ** 3:.0f} GB")
            if platz.free < 2 * 1024 ** 3:
                print("WARNUNG: Das Laufwerk ist fast voll.")
        except OSError:
            pass
        return self.adresse, self.ordner

    BACKUP_VERZOEGERUNG = 20   # Sekunden nach dem Start: erst Dashboard und Seiten, dann das Backup

    @classmethod
    def _backup(cls, beendet):
        if beendet.wait(cls.BACKUP_VERZOEGERUNG):
            return
        try:
            if Handler.backup.taeglich_hintergrund():
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} Tägliches Backup gestartet")
        except Exception as e:  # noqa: BLE001 – ein misslungenes Backup darf den Start nicht verhindern
            print(f"Tägliches Backup nicht möglich: {e}")

    def im_hintergrund(self):
        self._dient = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        threading.Thread(target=self._waechter, name="waechter", daemon=True).start()

    def _waechter(self):
        """Hängt eine Anfrage länger als eine Minute, schreibt Liloport einmal alle Thread-Stapel ins Protokoll.
        Damit lässt sich ein Hänger später genau nachvollziehen (liloport.log im Einstellungsordner)."""
        import faulthandler
        gemeldet = set()
        while not self.beendet.wait(15):
            jetzt_ = time.monotonic()
            for tid, (start, methode, pfad) in list(Handler.laufende_anfragen.items()):
                if methode and jetzt_ - start > 60 and (tid, start) not in gemeldet:
                    gemeldet.add((tid, start))
                    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} Anfrage hängt seit {jetzt_ - start:.0f} s: {methode} {pfad}")
                    try:
                        faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
                    except Exception:  # noqa: BLE001 – ohne Dateihandle (z. B. kein Protokoll) nur die Meldung
                        pass

    def beenden(self):
        """Darf aus jedem Thread aufgerufen werden, auch mehrfach."""
        self.beendet.set()

    def aufraeumen(self):
        if self.server:
            if self._dient:
                try:
                    self.server.shutdown()
                except Exception:  # noqa: BLE001
                    pass
            self.server.server_close()
        if Handler.sitzung:
            Handler.sitzung.beenden()
        if self._lauf_eigen:
            try:
                if json.loads(lauf_datei().read_text(encoding="utf-8")).get("pid") == os.getpid():
                    lauf_datei().unlink()
            except (OSError, ValueError):
                pass
        print("Liloport beendet.")


def main(argv=None):
    """Startet Liloport. Mit Fenster (installiertes Programm, Desktop-Symbol) oder in der Konsole."""
    parser = argparse.ArgumentParser(description="Liloport lokal starten.")
    parser.add_argument("ordner", nargs="?", help="Inhalte-Ordner (Standard: config.json oder ~/Liloport)")
    parser.add_argument("--port", type=int, default=STANDARD_PORT)
    parser.add_argument("--kein-browser", action="store_true")
    parser.add_argument("--fenster", action="store_true", help="mit Startfenster (Standard beim installierten Programm)")
    parser.add_argument("--ohne-fenster", action="store_true", help="nur Konsole, auch beim installierten Programm")
    # parse_known_args: macOS kann einem Programm beim Start eigene Argumente mitgeben
    args, _ = parser.parse_known_args(argv)

    gefroren = getattr(sys, "frozen", False)
    if gefroren:
        umgebung_fuer_programme()
        if sys.stdout is None or sys.stderr is None or not args.ohne_fenster:
            protokoll_umleiten()
            Handler.leise = True
    mit_fenster = (args.fenster or gefroren) and not args.ohne_fenster

    if not args.ordner and args.port == STANDARD_PORT:
        laeuft = laufende_adresse()
        if laeuft:
            print(f"Liloport läuft bereits – öffne nur das Dashboard: {laeuft}")
            if not args.kein_browser and not browser_oeffnen(laeuft) and mit_fenster:
                _hinweis_fenster("Liloport läuft bereits",
                                 f"Liloport läuft bereits, aber der Browser liess sich nicht öffnen.\n\n"
                                 f"Bitte einen Browser starten und diese Adresse eingeben:\n{laeuft}")
            return 0

    if gefroren:
        windows_kennung_setzen()
    dienst = Dienst(args.ordner, args.port)
    oeffnen = (lambda a: True) if args.kein_browser else browser_oeffnen

    if mit_fenster:
        from liloport import fenster
        if fenster.verfuegbar():
            def starten():
                adresse, ordner = dienst.starten()
                dienst.im_hintergrund()
                return adresse, ordner
            try:
                f = fenster.Startfenster("Liloport", version_anzeige(produkt_laden().get("version")),
                                         PROGRAMM_DATEN / "static" / "app-icon.png",
                                         starten, oeffnen, ordner_oeffnen, dienst.beendet)
            except Exception as e:  # noqa: BLE001 – z. B. keine Anzeige: dann ohne Fenster weiter
                print(f"Startfenster nicht möglich ({e}) – Liloport läuft ohne Fenster.")
            else:
                try:
                    ergebnis = f.ausfuehren()
                finally:
                    dienst.aufraeumen()
                return 1 if ergebnis == "fehler" else 0

    # Ohne Fenster: Server im Vordergrund; beenden mit Ctrl+C oder mit «Beenden» im Dashboard
    try:
        dienst.starten()
    except Exception as e:  # noqa: BLE001
        print(f"Liloport konnte nicht starten: {e}")
        return 1
    print("Beenden mit Ctrl+C oder im Dashboard über «Beenden».")
    if not args.kein_browser:
        threading.Timer(0.5, lambda: oeffnen(dienst.adresse)).start()
    dienst.im_hintergrund()
    try:
        while not dienst.beendet.wait(0.5):
            pass
    except KeyboardInterrupt:
        print()
    finally:
        dienst.aufraeumen()
    return 0


if __name__ == "__main__":
    # Das installierte Programm startet für das Lesen von PDFs eigene Prozesse (siehe liloport/pdftext.py);
    # freeze_support lässt diese Prozesse ihre Arbeit tun, statt ein zweites Liloport zu öffnen.
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())
