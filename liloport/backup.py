"""Backups des Inhalte-Ordners: täglich automatisch und auf Knopfdruck – auch bei vielen Gigabyte.

Aufbau des Backup-Ordners (Standard: _wiki/backups im Inhalte-Ordner; wählbar, z. B. eine externe Festplatte):

    2026-10-27_141818.zip     Momentaufnahme: alle kleinen Dateien (Seiten, Einstellungen, …) und
                              liloport-backup.json mit der Liste der grossen Dateien dieses Stands
    dateien/ab/ab12….dat      grosse Dateien (Bilder, Videos, PDFs ab 32 KB), benannt nach ihrer
                              SHA-256-Prüfsumme: Jeder Inhalt liegt nur einmal da, egal in wie vielen Backups
    dateien.json              Merkliste Pfad → Grösse, Änderungszeit, Prüfsumme: Unveränderte Dateien werden
                              beim nächsten Backup weder gelesen noch kopiert
    .liloport-backups.json    Marke: zu welchem Inhalte-Ordner (Kennung) dieser Backup-Ordner gehört
    .sperre                   solange ein Backup läuft (auch über Prozesse und Geräte hinweg)

Das erste Backup kopiert alles einmal; jedes weitere nur, was neu ist oder sich geändert hat. Zehn Backups
eines Portfolios mit 50 GB Videos belegen darum rund 50 GB (plus Änderungen) statt 500 GB. Vor jedem Backup
prüft Liloport den freien Speicherplatz und lässt immer eine Reserve frei, damit das Laufwerk nie vollläuft.

Ein gewählter Backup-Ordner bekommt immer einen eigenen Unterordner pro Inhalte-Ordner; Liloport räumt nur
dort auf und nur Dateien mit seinen eigenen Namensmustern.

Backups aus Testversionen vor 0.9 sind ein vollständiges ZIP ohne liloport-backup.json; sie lassen sich weiterhin
wiederherstellen und werden mit der Zeit wie alle anderen aufgeräumt.
"""
import hashlib
import json
import os
import re
import secrets
import shutil
import sys
import threading
import time
import zipfile
from datetime import date, datetime
from pathlib import Path

from .store import INTERN, Store, StoreFehler

BEREITS_KOMPRIMIERT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".webm", ".pdf", ".zip", ".woff2"}

MAX_BACKUPS = 10
WARNUNG_TAGE = 7
GROSS = 32 * 1024                   # ab dieser Grösse kommt eine Datei in den gemeinsamen Dateispeicher
RESERVE_MIN = 1024 ** 3             # so viel bleibt auf dem Laufwerk mindestens frei (1 GB) …
RESERVE_ANTEIL = 0.02               # … bzw. 2 % des Laufwerks, wenn das mehr ist
MANIFEST = "liloport-backup.json"
MARKE = ".liloport-backups.json"
SPERRDATEI = ".sperre"
SPERRE_ALTER = 600                  # Sekunden ohne Lebenszeichen: Sperre eines abgestürzten Liloport gilt als alt
TEIL_ALTER = 6 * 3600               # .teil-Reste erst nach so langer Zeit löschen
UNSCHARF_NS = 3_000_000_000         # Änderungszeit so nah am Backup-Start: nicht als «unverändert» merken
NAME_RE = re.compile(r"\d{4}-\d{2}-\d{2}_\d{6}\.zip")
DAT_RE = re.compile(r"[0-9a-f]{64}\.dat")
FACH_RE = re.compile(r"[0-9a-f]{2}")
SUMME_RE = re.compile(r"[0-9a-f]{64}")
STUECK = 1024 * 1024
AUSGESCHLOSSEN = {(INTERN, "backups"), (INTERN, "import")}   # nie ins Backup
ID_DATEI = "portfolio-id.json"
# Gerätebezogen bzw. Kennung: nie sichern (sonst zeigte eine wiederhergestellte Kopie auf denselben
# Backup-Ordner und gälte als dasselbe Portfolio)
NICHT_SICHERN = {f"{INTERN}/backup-ort.json", f"{INTERN}/backup-status.json", f"{INTERN}/{ID_DATEI}"}
SYSTEMDATEIEN = {"Thumbs.db", ".DS_Store", "desktop.ini"}


def groesse_lesbar(n: float) -> str:
    """1234567 -> '1,2 MB' (Schweizer Schreibweise mit Komma)."""
    for einheit in ("Bytes", "KB", "MB", "GB", "TB"):
        if n < 1024 or einheit == "TB":
            text = f"{n:.0f}" if einheit in ("Bytes", "KB") else f"{n:.1f}".replace(".", ",")
            return f"{text} {einheit}"
        n /= 1024
    return ""


def reserve(gesamt: int) -> int:
    return max(RESERVE_MIN, int(gesamt * RESERVE_ANTEIL))


def _niedrige_prioritaet():
    """Windows: Backup-Thread mit Hintergrund-Priorität (auch für Festplattenzugriffe), damit Liloport und
    der Rest des Computers flüssig bleiben, während viele Gigabyte kopiert werden."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetThreadPriority(k.GetCurrentThread(), 0x00010000)   # THREAD_MODE_BACKGROUND_BEGIN
        except (AttributeError, OSError):
            pass


def _ersetzen(quelle: Path, ziel: Path):
    """os.replace mit Wiederholung: Unter Windows halten Virenscanner und Indexdienste frisch geschriebene
    Dateien oft kurz offen (PermissionError), ebenso ein anderer Thread, der die Zieldatei gerade liest."""
    for versuch in range(12):
        try:
            os.replace(quelle, ziel)
            return
        except PermissionError:
            if versuch == 11:
                raise
            time.sleep(0.1 * (versuch + 1))


def _json_schreiben(datei: Path, daten):
    tmp = datei.with_name(f"{datei.name}.{secrets.token_hex(4)}.tmp")
    try:
        tmp.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
        _ersetzen(tmp, datei)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _gleich(a: Path, b: Path) -> bool:
    """Derselbe Ordner? Auch auf Dateisystemen ohne Gross-/Kleinschreibung (macOS) und über Verknüpfungen."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(str(a)) == os.path.normcase(str(b))


def _liegt_in(kind: Path, eltern: Path) -> bool:
    """Liegt kind in eltern (oder ist es eltern)?"""
    for p in [kind, *kind.parents]:
        if _gleich(p, eltern):
            return True
    return False


class _Quellfehler(Exception):
    """Eine Datei im Inhalte-Ordner liess sich nicht lesen (gesperrt, gerade gelöscht): überspringen."""


class _Sperre:
    """Sperrdatei im Backup-Ordner: Zwei Liloport (zwei Geräte am selben Cloud-Ordner, zwei Fenster) sichern
    nie gleichzeitig in denselben Ordner. Ein laufendes Backup frischt sie regelmässig auf; ist sie länger als
    SPERRE_ALTER unverändert, stammt sie von einem abgestürzten Liloport und wird übernommen."""

    def __init__(self, ordner: Path):
        self.datei = ordner / SPERRDATEI
        self._zuletzt = 0.0

    def holen(self):
        for _ in range(3):
            try:
                fd = os.open(self.datei, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    alter = time.time() - self.datei.stat().st_mtime
                except FileNotFoundError:
                    continue
                if alter > SPERRE_ALTER:
                    try:
                        self.datei.unlink()
                    except OSError:
                        pass
                    continue
                raise StoreFehler("Ein anderes Liloport (z. B. auf einem zweiten Gerät) arbeitet gerade in diesem "
                                  "Backup-Ordner. Bitte in ein paar Minuten nochmals versuchen.")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps({"pid": os.getpid(), "seit": datetime.now().isoformat(timespec="seconds")}))
            self._zuletzt = time.monotonic()
            return
        raise StoreFehler("Die Sperrdatei im Backup-Ordner lässt sich nicht anlegen.")

    def auffrischen(self):
        if time.monotonic() - self._zuletzt > 30:
            self._zuletzt = time.monotonic()
            try:
                os.utime(self.datei)
            except OSError:
                pass

    def freigeben(self):
        try:
            self.datei.unlink(missing_ok=True)
        except OSError:
            pass


class Backup:
    """Erstellt, listet und entpackt Backups; kann beides im Hintergrund (mit Fortschritt)."""

    def __init__(self, store: Store):
        self.store = store
        self.standard = store.root / INTERN / "backups"
        self.ort_datei = store.root / INTERN / "backup-ort.json"
        self.status_datei = store.root / INTERN / "backup-status.json"
        self._sperre = threading.Lock()          # eine Arbeit (Backup, Wiederherstellen, Ort ändern) zur Zeit
        self._status_sperre = threading.Lock()   # backup-status.json lesen/schreiben
        self._manifeste = {}                     # (pfad, grösse, mtime) -> Manifest, für schnelle Übersicht
        self.arbeit = None        # laufende Arbeit: {"art", "fertig", "gesamt", "seit"}
        self._thread = None

    # ---------- Kennung und Ort ----------

    def kennung(self) -> str:
        """Zufällige Kennung dieses Inhalte-Ordners (wird nicht mitgesichert: eine Kopie bekommt eine neue)."""
        datei = self.store.root / INTERN / ID_DATEI
        try:
            k = json.loads(datei.read_text(encoding="utf-8")).get("id")
            if isinstance(k, str) and re.fullmatch(r"[0-9a-f]{32}", k):
                return k
        except (OSError, ValueError, AttributeError):
            pass
        k = secrets.token_hex(16)
        datei.parent.mkdir(parents=True, exist_ok=True)
        _json_schreiben(datei, {"id": k})
        return k

    @property
    def ordner(self) -> Path:
        try:
            eigener = json.loads(self.ort_datei.read_text(encoding="utf-8")).get("ordner")
        except (OSError, ValueError, AttributeError):
            eigener = None
        return Path(eigener) if eigener else self.standard

    def ist_standard(self, ordner: Path = None) -> bool:
        return (ordner or self.ordner) == self.standard

    def _marke_lesen(self, ordner: Path):
        try:
            return json.loads((ordner / MARKE).read_text(encoding="utf-8")).get("id")
        except (OSError, ValueError, AttributeError):
            return None

    def _marke_pruefen(self, ordner: Path):
        """Gehört der Backup-Ordner zu diesem Inhalte-Ordner? Fehlt die Marke, wird sie nur angelegt, wo das
        sicher ist (Standardordner oder leerer Ordner) – sonst lieber kein Backup als fremde Dateien anfassen."""
        eigene = self.kennung()
        marke = self._marke_lesen(ordner)
        if marke == eigene:
            return
        if marke:
            raise StoreFehler(f"Der Backup-Ordner {ordner} gehört zu einem anderen Liloport-Inhalte-Ordner. "
                              "Bitte im Dashboard (Verwaltung › Backup) einen anderen Ordner wählen.")
        leer = not ordner.exists() or not any(p.name != SPERRDATEI for p in ordner.iterdir())
        if self.ist_standard(ordner) or leer:
            ordner.mkdir(parents=True, exist_ok=True)
            _json_schreiben(ordner / MARKE, {"id": eigene, "inhalte": str(self.store.root)})
            return
        raise StoreFehler(f"Der Ordner {ordner} ist nicht als Liloport-Backup-Ordner erkennbar. "
                          "Bitte im Dashboard (Verwaltung › Backup) den Backup-Ordner neu wählen.")

    def ort_setzen(self, ordner: str) -> dict:
        """Neuer Backup-Ordner ('' = wieder im Inhalte-Ordner). Bisherige Backups bleiben, wo sie sind.

        Gewählt wird ein Ort (z. B. E:\\); die Backups landen darin im eigenen Unterordner
        «Liloport-Backups/<Name des Inhalte-Ordners>-<Kennung>». So teilen sich zwei Portfolios nie einen Ordner,
        und Liloport räumt nur auf, was ihm gehört."""
        if not self._sperre.acquire(blocking=False):
            raise StoreFehler("Bitte warten, bis das laufende Backup fertig ist.")
        try:
            return self._ort_setzen(ordner)
        finally:
            self._sperre.release()

    def _ort_setzen(self, ordner: str) -> dict:
        ordner = (ordner or "").strip()
        if not ordner:
            self.ort_datei.unlink(missing_ok=True)
            return self.status()
        ziel = Path(ordner).expanduser()
        if not ziel.is_absolute():
            raise StoreFehler("Bitte den vollständigen Pfad angeben, z. B. E:\\Liloport-Backups oder /Volumes/Stick/Liloport-Backups.")
        ziel = ziel.resolve()
        root = self.store.root.resolve()
        if _liegt_in(ziel, root):
            raise StoreFehler("Der Backup-Ordner darf nicht im Inhalte-Ordner liegen. "
                              "(Ohne Angabe liegen die Backups dort unter _wiki/backups.)")
        eigene = self.kennung()
        if self._marke_lesen(ziel) != eigene:
            name = re.sub(r"[^\w.-]+", "-", root.name).strip("-.") or "Liloport"
            if ziel.name.lower() != "liloport-backups":
                ziel = ziel / "Liloport-Backups"
            ziel = ziel / f"{name}-{eigene[:8]}"
        try:
            ziel.mkdir(parents=True, exist_ok=True)
            probe = ziel / f".liloport-probe-{secrets.token_hex(4)}"
            probe.write_bytes(b"ok")
            probe.unlink()
        except OSError as e:
            raise StoreFehler(f"In diesen Ordner kann Liloport nicht schreiben: {e.strerror or e}")
        self._marke_pruefen(ziel)
        try:
            _json_schreiben(self.ort_datei, {"ordner": str(ziel)})
        except OSError as e:
            raise StoreFehler(f"Einstellung liess sich nicht speichern: {e.strerror or e}")
        return self.status()

    # ---------- Übersicht ----------

    def _manifest(self, zip_pfad: Path, frisch: bool = False):
        """liloport-backup.json eines Backups; None bei Backups alter Art (vollständiges ZIP)."""
        st = zip_pfad.stat()
        schluessel = (str(zip_pfad), st.st_size, st.st_mtime_ns)
        if not frisch and schluessel in self._manifeste:
            return self._manifeste[schluessel]
        with zipfile.ZipFile(zip_pfad) as z:
            try:
                m = json.loads(z.read(MANIFEST).decode("utf-8"))
            except KeyError:
                m = None
        if m is not None and not isinstance(m, dict):
            raise ValueError("Manifest unlesbar")
        if len(self._manifeste) > 200:
            self._manifeste.clear()
        self._manifeste[schluessel] = m
        return m

    def liste(self, ordner: Path = None) -> list:
        """Alle Backups, neueste zuerst. groesse = Umfang des gesicherten Inhalts."""
        ordner = ordner or self.ordner
        dateien = sorted((d for d in ordner.glob("*.zip") if NAME_RE.fullmatch(d.name)), reverse=True)
        eintraege = []
        for datei in dateien:
            try:
                zipgroesse = datei.stat().st_size
                m = self._manifest(datei)
            except (OSError, zipfile.BadZipFile, ValueError):
                eintraege.append({"name": datei.name, "zeit": _zeit_aus_name(datei.stem), "groesse": 0, "defekt": True})
                continue
            eintraege.append({"name": datei.name, "zeit": _zeit_aus_name(datei.stem),
                              "groesse": (m or {}).get("gesamt", zipgroesse), "art": "neu" if m else "vollständig"})
        return eintraege

    def _status_lesen(self) -> dict:
        with self._status_sperre:
            try:
                d = json.loads(self.status_datei.read_text(encoding="utf-8"))
                return d if isinstance(d, dict) else {}
            except (OSError, ValueError):
                return {}

    def _status_schreiben(self, **werte):
        with self._status_sperre:
            try:
                daten = json.loads(self.status_datei.read_text(encoding="utf-8"))
                if not isinstance(daten, dict):
                    daten = {}
            except (OSError, ValueError):
                daten = {}
            daten.update(werte)
            try:
                _json_schreiben(self.status_datei, daten)
            except OSError as e:
                print(f"Backup-Status liess sich nicht speichern: {e}")

    def status(self) -> dict:
        """Letztes Backup, Warnungen, Speicherplatz, laufende Arbeit."""
        ordner = self.ordner
        standard = self.ist_standard(ordner)
        erreichbar = ordner.exists() or standard
        try:
            liste = self.liste(ordner) if erreichbar else []
        except OSError:
            liste, erreichbar = [], False
        gueltig = [b for b in liste if not b.get("defekt")]
        letztes = gueltig[0]["zeit"] if gueltig else None
        tage = (datetime.now() - datetime.fromisoformat(letztes)).days if letztes else None
        gespeichert = self._status_lesen()
        meldung = gespeichert.get("meldung") or None
        if not erreichbar:
            meldung = (f"Der Backup-Ordner ist nicht erreichbar: {ordner}. Ist die externe Festplatte bzw. "
                       "der USB-Stick angeschlossen?")
        speicher = _platz(ordner if erreichbar else self.store.root)
        inhalte_platz = _platz(self.store.root)
        knapp = bool(inhalte_platz and inhalte_platz["frei"] < reserve(inhalte_platz["gesamt"]) * 2)
        arbeit = self.arbeit
        return {"letztes": letztes, "tage": tage,
                "warnung": letztes is None or tage >= WARNUNG_TAGE or bool(meldung) or knapp,
                "anzahl": len(gueltig), "backups": liste, "ordner": str(ordner), "standard": standard,
                "erreichbar": erreichbar, "meldung": meldung, "speicher": speicher, "inhalte_speicher": inhalte_platz,
                "speicher_knapp": knapp, "belegt": gespeichert.get("belegt"), "inhalte": gespeichert.get("inhalte"),
                "laeuft": dict(arbeit) if arbeit else None, "zuletzt": gespeichert.get("zuletzt")}

    # ---------- Backup erstellen ----------

    def _dateien_sammeln(self, ordner: Path):
        """(rel, pfad, grösse, mtime_ns) aller zu sichernden Dateien; robust gegen Dateien, die verschwinden."""
        root = self.store.root
        try:
            backup_st = os.stat(ordner)
        except OSError:
            backup_st = None
        ergebnis = []
        for verz, unterordner, dateien in os.walk(root):
            verz_pfad = Path(verz)
            rel_verz = verz_pfad.relative_to(root)
            behalten = []
            for u in sorted(unterordner):
                if (rel_verz / u).parts[:2] in AUSGESCHLOSSEN:
                    continue
                if u in ("$RECYCLE.BIN", "System Volume Information", ".Trash-1000"):
                    continue
                if backup_st is not None:
                    try:   # Backup-Ordner nie in sich selbst sichern (auch bei anderer Gross-/Kleinschreibung)
                        if os.path.samestat(os.stat(verz_pfad / u), backup_st):
                            continue
                    except OSError:
                        continue
                behalten.append(u)
            unterordner[:] = behalten
            for name in sorted(dateien):
                rel = (rel_verz / name).as_posix()
                if name in SYSTEMDATEIEN or rel in NICHT_SICHERN:
                    continue
                if rel.startswith(INTERN + "/") and name.endswith((".teil", ".tmp")):
                    continue   # Zwischenstände von Liloport selbst
                pfad = verz_pfad / name
                try:
                    st = pfad.stat()
                except OSError:
                    continue
                ergebnis.append((rel, pfad, st.st_size, st.st_mtime_ns))
        return ergebnis

    @staticmethod
    def _speicher_pfad(ordner: Path, h: str) -> Path:
        return ordner / "dateien" / h[:2] / f"{h}.dat"

    def _aufnehmen(self, ordner: Path, pfad: Path, arbeit: dict, sperre: _Sperre) -> str:
        """Kopiert eine grosse Datei in den Dateispeicher (falls ihr Inhalt dort noch fehlt); gibt SHA-256 zurück.
        Gelesen wird nur einmal: Prüfsumme und Kopie entstehen im selben Durchgang. Fehler beim Lesen der Quelle
        ergeben _Quellfehler (Datei wird übersprungen), Fehler am Ziel brechen das Backup ab."""
        speicher = ordner / "dateien"
        speicher.mkdir(parents=True, exist_ok=True)
        tmp = speicher / f"{secrets.token_hex(8)}.teil"
        h = hashlib.sha256()
        groesse = 0
        try:
            try:
                quelle = open(pfad, "rb")
            except OSError as e:
                raise _Quellfehler(e.strerror or str(e)) from e
            with quelle, open(tmp, "wb") as ziel:
                while True:
                    try:
                        stueck = quelle.read(STUECK)
                    except OSError as e:
                        raise _Quellfehler(e.strerror or str(e)) from e
                    if not stueck:
                        break
                    h.update(stueck)
                    ziel.write(stueck)
                    groesse += len(stueck)
                    arbeit["fertig"] += len(stueck)
                    sperre.auffrischen()
                ziel.flush()
                os.fsync(ziel.fileno())   # erst auf der Platte, dann umbenennen (USB-Stick abgezogen …)
            summe = h.hexdigest()
            endgueltig = self._speicher_pfad(ordner, summe)
            try:
                schon_da = endgueltig.stat().st_size == groesse
            except FileNotFoundError:
                schon_da = False
            if schon_da:
                tmp.unlink()
            else:   # fehlt oder beschädigt (falsche Grösse): durch die frische Kopie ersetzen
                endgueltig.parent.mkdir(exist_ok=True)
                _ersetzen(tmp, endgueltig)
            return summe
        except BaseException:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def erstellen(self, arbeit: dict = None) -> dict:
        """Erstellt ein Backup (blockiert bis fertig). Wirft StoreFehler bei zu wenig Platz oder fehlendem Ordner."""
        if not self._sperre.acquire(blocking=False):
            raise StoreFehler("Es läuft bereits ein Backup oder eine Wiederherstellung.")
        arbeit = arbeit if arbeit is not None else {"art": "backup", "fertig": 0, "gesamt": 0, "seit": time.time()}
        self.arbeit = arbeit
        jetzt = lambda: datetime.now().isoformat(timespec="seconds")  # noqa: E731
        try:
            ergebnis = self._erstellen(self.ordner, arbeit)
            self._status_schreiben(meldung=None, zuletzt={"art": "backup", "ok": True, "name": ergebnis["name"],
                                                          "zeit": jetzt(), "uebersprungen": len(ergebnis["uebersprungen"])})
            return ergebnis
        except StoreFehler as e:
            self._status_schreiben(meldung=str(e), zuletzt={"art": "backup", "ok": False, "fehler": str(e), "zeit": jetzt()})
            raise
        except OSError as e:
            text = f"Backup nicht möglich: {e.strerror or e}"
            self._status_schreiben(meldung=text, zuletzt={"art": "backup", "ok": False, "fehler": text, "zeit": jetzt()})
            raise StoreFehler(text) from e
        finally:
            if self.arbeit is arbeit:
                self.arbeit = None
            self._sperre.release()

    def _erstellen(self, ordner: Path, arbeit: dict) -> dict:
        if not self.ist_standard(ordner) and not ordner.exists():
            raise StoreFehler(f"Der Backup-Ordner ist nicht erreichbar: {ordner}. Ist die externe Festplatte "
                              "bzw. der USB-Stick angeschlossen?")
        ordner.mkdir(parents=True, exist_ok=True)
        self._marke_pruefen(ordner)
        sperre = _Sperre(ordner)
        sperre.holen()
        try:
            return self._sichern(ordner, arbeit, sperre)
        finally:
            sperre.freigeben()

    def _sichern(self, ordner: Path, arbeit: dict, sperre: _Sperre) -> dict:
        start_ns = time.time_ns()
        index_datei = ordner / "dateien.json"
        try:
            index = json.loads(index_datei.read_text(encoding="utf-8")).get("dateien", {})
            if not isinstance(index, dict):
                index = {}
        except (OSError, ValueError, AttributeError):
            index = {}

        dateien = self._dateien_sammeln(ordner)
        bekannt = {}
        noetig = 0
        for rel, pfad, groesse, mtime in dateien:
            e = index.get(rel)
            if groesse >= GROSS and isinstance(e, dict) and e.get("m") is not None \
                    and e.get("g") == groesse and e.get("m") == mtime and SUMME_RE.fullmatch(str(e.get("h", ""))):
                try:
                    if self._speicher_pfad(ordner, e["h"]).stat().st_size == groesse:
                        bekannt[rel] = e["h"]
                        continue
                except OSError:
                    pass
            noetig += groesse
        gesamt = sum(d[2] for d in dateien)
        arbeit["gesamt"] = noetig

        # Platz prüfen: lieber kein Backup als ein volles Laufwerk (dann versagen auch andere Programme)
        platz = shutil.disk_usage(ordner)
        rest = reserve(platz.total)
        if platz.free - noetig < rest:
            raise StoreFehler(
                f"Zu wenig Speicherplatz für das Backup: nötig sind etwa {groesse_lesbar(noetig)}, frei sind "
                f"{groesse_lesbar(platz.free)}, und Liloport lässt immer mindestens {groesse_lesbar(rest)} frei. "
                "Abhilfe: Platz schaffen oder im Dashboard (Verwaltung › Backup) einen Backup-Ordner auf einer "
                "externen Festplatte wählen.")

        name = datetime.now().strftime("%Y-%m-%d_%H%M%S") + ".zip"
        while (ordner / name).exists():   # zwei Backups in derselben Sekunde
            time.sleep(1)
            name = datetime.now().strftime("%Y-%m-%d_%H%M%S") + ".zip"
        ziel = ordner / name
        # Erst unter eigenem Zwischennamen schreiben: Bricht Liloport mittendrin ab, bleibt kein halbes Backup
        # liegen, das wie ein gültiges aussieht (und das tägliche Backup für heute verhindern würde).
        tmp = ordner / f"{name}.{secrets.token_hex(4)}.teil"
        grosse, neuer_index, uebersprungen = {}, {}, []
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
                for rel, pfad, groesse, mtime in dateien:
                    sperre.auffrischen()
                    try:
                        if groesse >= GROSS:
                            h = bekannt.get(rel) or self._aufnehmen(ordner, pfad, arbeit, sperre)
                            grosse[rel] = {"h": h, "g": groesse}
                            # Gerade erst geändert? Dann beim nächsten Mal nochmals lesen: Grobe Zeitstempel
                            # (FAT, manche Netzlaufwerke) zeigen eine zweite Änderung in derselben Sekunde nicht.
                            frisch = mtime > start_ns - UNSCHARF_NS
                            neuer_index[rel] = {"g": groesse, "m": None if frisch else mtime, "h": h}
                        else:
                            # Kleine Datei ganz lesen, dann schreiben: Ein Lesefehler mittendrin hinterlässt so
                            # keinen abgeschnittenen Eintrag im ZIP.
                            try:
                                info = zipfile.ZipInfo.from_file(pfad, rel, strict_timestamps=False)
                                daten = pfad.read_bytes()
                            except OSError as e:
                                raise _Quellfehler(e.strerror or str(e)) from e
                            info.compress_type = (zipfile.ZIP_STORED if pfad.suffix.lower() in BEREITS_KOMPRIMIERT
                                                  else zipfile.ZIP_DEFLATED)
                            z.writestr(info, daten)
                            arbeit["fertig"] += len(daten)
                    except _Quellfehler as e:
                        # gerade gelöscht oder von einem anderen Programm gesperrt: weiter mit dem Rest
                        uebersprungen.append(f"{rel} ({e})")
                z.writestr(MANIFEST, json.dumps({"version": 2, "portfolio": self.kennung(),
                                                 "erstellt": datetime.now().isoformat(timespec="seconds"),
                                                 "gesamt": gesamt, "dateien": len(dateien), "grosse": grosse,
                                                 "uebersprungen": uebersprungen}, ensure_ascii=False))
            with open(tmp, "rb+") as f:
                os.fsync(f.fileno())
            _ersetzen(tmp, ziel)
        except OSError as e:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            if getattr(e, "errno", None) == 28:
                raise StoreFehler("Das Laufwerk des Backup-Ordners ist voll. Backup abgebrochen.") from e
            raise
        except BaseException:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        _json_schreiben(index_datei, {"dateien": neuer_index})
        belegt = self._aufraeumen(ordner, name)
        self._status_schreiben(belegt=belegt, inhalte=gesamt)
        if uebersprungen:
            print(f"Backup: {len(uebersprungen)} Datei(en) übersprungen, z. B. {uebersprungen[0]}")
        return {"name": name, "zeit": _zeit_aus_name(ziel.stem), "groesse": gesamt, "uebersprungen": uebersprungen}

    def taeglich(self) -> dict:
        """Erstellt ein Backup, falls heute noch keines gemacht wurde."""
        if self._heute_schon():
            return {"erstellt": False}
        return {"erstellt": True, **self.erstellen()}

    def _heute_schon(self) -> bool:
        heute = date.today().isoformat()
        try:
            return any(b["zeit"].startswith(heute) and not b.get("defekt") for b in self.liste())
        except OSError:
            return False

    def _aufraeumen(self, ordner: Path, neu: str):
        """Nur die neuesten MAX_BACKUPS behalten (das eben erstellte immer); Dateien im Speicher löschen, die
        kein Backup mehr braucht. Gibt den belegten Platz zurück (None, wenn nichts geprüft werden konnte)."""
        grenze = time.time() - TEIL_ALTER
        reste = list(ordner.glob("*.teil"))
        if (ordner / "dateien").is_dir():
            reste += list((ordner / "dateien").glob("*.teil"))
        for rest in reste:   # Reste abgebrochener Backups – nur alte, ein anderes Gerät könnte gerade schreiben
            try:
                if rest.stat().st_mtime < grenze:
                    rest.unlink()
            except OSError:
                pass
        try:
            liste = self.liste(ordner)
        except OSError:
            return None
        namen = [b["name"] for b in liste]
        if neu not in namen:
            return None   # Übersicht unvollständig: lieber nichts löschen
        behalten = [b for b in liste[:MAX_BACKUPS]]
        if neu not in [b["name"] for b in behalten]:   # Uhr falsch gestellt: das neue nie gleich wieder löschen
            behalten = behalten[:MAX_BACKUPS - 1] + [b for b in liste if b["name"] == neu]
        behalten_namen = {b["name"] for b in behalten}
        for alt in liste:
            if alt["name"] not in behalten_namen:
                try:
                    (ordner / alt["name"]).unlink()
                except OSError:
                    pass
        gebraucht, sicher = set(), True
        for b in behalten:
            try:
                m = self._manifest(ordner / b["name"], frisch=True)
            except (OSError, zipfile.BadZipFile, ValueError):
                sicher = False   # unlesbares Backup: lieber nichts aus dem Speicher löschen
                continue
            if m is None:
                if b["name"] == neu:
                    sicher = False
                continue
            grosse = m.get("grosse")
            if not isinstance(grosse, dict):
                sicher = False
                continue
            for e in grosse.values():
                if isinstance(e, dict):
                    gebraucht.add(str(e.get("h")))
        belegt = 0
        for b in behalten:
            try:
                belegt += (ordner / b["name"]).stat().st_size
            except OSError:
                pass
        speicher = ordner / "dateien"
        if speicher.is_dir():
            for fach in speicher.iterdir():
                if not (fach.is_dir() and FACH_RE.fullmatch(fach.name)):
                    continue
                for datei in fach.iterdir():
                    if not DAT_RE.fullmatch(datei.name):
                        continue   # nur eigene Dateien anfassen
                    try:
                        if sicher and datei.name[:-4] not in gebraucht:
                            datei.unlink()
                        else:
                            belegt += datei.stat().st_size
                    except OSError:
                        pass
        return belegt

    # ---------- Wiederherstellen ----------

    def _wiederherstellen_pruefen(self, name: str, zielordner: str, ordner: Path):
        if not NAME_RE.fullmatch(name or ""):
            raise StoreFehler("Ungültiger Backup-Name.")
        quelle = ordner / name
        if not quelle.exists():
            raise StoreFehler("Backup nicht gefunden.")
        if not (zielordner or "").strip():
            raise StoreFehler("Bitte einen Zielordner angeben.")
        ziel = Path(zielordner.strip()).expanduser()
        if not ziel.is_absolute():
            raise StoreFehler("Bitte den vollständigen Pfad des Zielordners angeben, z. B. C:\\Users\\name\\Liloport-Stand.")
        ziel = ziel.resolve()
        root = self.store.root.resolve()
        if _liegt_in(ziel, root) or _liegt_in(root, ziel):
            raise StoreFehler("Der Zielordner darf nicht im laufenden Inhalte-Ordner liegen.")
        if ordner.exists() and _liegt_in(ziel, ordner.resolve()):
            raise StoreFehler("Der Zielordner darf nicht im Backup-Ordner liegen.")
        if ziel.exists() and any(ziel.iterdir()):
            raise StoreFehler("Der Zielordner ist nicht leer.")
        try:
            m = self._manifest(quelle, frisch=True)
        except (OSError, zipfile.BadZipFile, ValueError):
            raise StoreFehler("Dieses Backup ist beschädigt und lässt sich nicht öffnen.")
        noetig = (m or {}).get("gesamt") or quelle.stat().st_size * 2
        pruefen = ziel
        while not pruefen.exists() and pruefen.parent != pruefen:
            pruefen = pruefen.parent
        platz = shutil.disk_usage(pruefen)
        if platz.free - noetig < reserve(platz.total):
            raise StoreFehler(f"Zu wenig Speicherplatz am Zielort: nötig sind etwa {groesse_lesbar(noetig)}, "
                              f"frei sind {groesse_lesbar(platz.free)}.")
        return quelle, ziel, m, noetig

    def wiederherstellen(self, name: str, zielordner: str, arbeit: dict = None) -> str:
        """Entpackt ein Backup in einen neuen oder leeren Ordner, nie in den laufenden Inhalte-Ordner."""
        ordner = self.ordner
        quelle, ziel, m, noetig = self._wiederherstellen_pruefen(name, zielordner, ordner)
        if not self._sperre.acquire(blocking=False):
            raise StoreFehler("Es läuft bereits ein Backup oder eine Wiederherstellung.")
        arbeit = arbeit if arbeit is not None else {"art": "wiederherstellen", "fertig": 0, "gesamt": noetig, "seit": time.time()}
        self.arbeit = arbeit
        try:
            fehlend = self._entpacken(ordner, quelle, ziel, m, arbeit)
            self._status_schreiben(zuletzt={"art": "wiederherstellen", "ok": True, "ziel": str(ziel),
                                            "fehlend": fehlend, "zeit": datetime.now().isoformat(timespec="seconds")})
            return str(ziel)
        except (StoreFehler, OSError, zipfile.BadZipFile) as e:
            grund = str(e) if isinstance(e, StoreFehler) else f"{getattr(e, 'strerror', None) or e}"
            text = (f"Wiederherstellen nicht möglich: {grund} Der Zielordner enthält nun einen unvollständigen "
                    "Stand – bitte löschen oder einen anderen Ordner wählen.")
            self._status_schreiben(zuletzt={"art": "wiederherstellen", "ok": False, "fehler": text,
                                            "zeit": datetime.now().isoformat(timespec="seconds")})
            raise StoreFehler(text) from e
        finally:
            if self.arbeit is arbeit:
                self.arbeit = None
            self._sperre.release()

    @staticmethod
    def _zielpfad(ziel: Path, rel: str):
        """Sicherer Pfad im Zielordner oder None (ausserhalb, oder auf diesem System ungültiger Name)."""
        if not rel or rel.startswith(("/", "\\")):
            return None
        teile = rel.split("/")
        if any(t in ("", ".", "..") for t in teile[:-1]) or teile[-1] in ("", ".", ".."):
            return None
        if sys.platform.startswith("win") and any(re.search(r'[:*?"<>|\\]', t) for t in teile):
            return None   # z. B. «Projekt 1:2.pdf» vom Mac: würde unter Windows in einem Nebendatenstrom landen
        p = (ziel / Path(*teile)).resolve()
        if ziel not in p.parents:
            return None
        return p

    def _entpacken(self, ordner: Path, quelle: Path, ziel: Path, m, arbeit: dict) -> list:
        ziel.mkdir(parents=True, exist_ok=True)
        fehlend = []
        with zipfile.ZipFile(quelle) as z:
            for info in z.infolist():
                if info.filename == MANIFEST or info.filename in NICHT_SICHERN or info.is_dir():
                    continue
                p = self._zielpfad(ziel, info.filename)
                if p is None:
                    fehlend.append(info.filename)
                    continue
                p.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as q, open(p, "wb") as f:
                    shutil.copyfileobj(q, f, STUECK)
                arbeit["fertig"] += info.file_size
        for rel, e in sorted(((m or {}).get("grosse") or {}).items()):
            h = str((e or {}).get("h", "")) if isinstance(e, dict) else ""
            p = self._zielpfad(ziel, rel)
            quelle_datei = self._speicher_pfad(ordner, h) if SUMME_RE.fullmatch(h) else None
            if p is None or quelle_datei is None or not quelle_datei.exists():
                fehlend.append(rel)
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            pruef = hashlib.sha256()
            with open(quelle_datei, "rb") as q, open(p, "wb") as f:
                while True:
                    stueck = q.read(STUECK)
                    if not stueck:
                        break
                    pruef.update(stueck)
                    f.write(stueck)
                    arbeit["fertig"] += len(stueck)
            if pruef.hexdigest() != h:   # im Dateispeicher beschädigt: nicht stillschweigend falsch zurückgeben
                p.unlink()
                fehlend.append(f"{rel} (beschädigt)")
        if fehlend:
            print(f"Wiederherstellen: {len(fehlend)} Datei(en) fehlen oder sind beschädigt, z. B. {fehlend[0]}")
        return fehlend

    # ---------- im Hintergrund ----------

    def _im_hintergrund(self, arbeit: dict, aufgabe):
        if (self._thread and self._thread.is_alive()) or self._sperre.locked():
            raise StoreFehler("Es läuft bereits ein Backup oder eine Wiederherstellung.")
        self.arbeit = arbeit

        def lauf():
            _niedrige_prioritaet()
            t0 = time.monotonic()
            try:
                aufgabe()
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {arbeit['art']} fertig ({time.monotonic() - t0:.0f} s)")
            except Exception as e:  # noqa: BLE001 – erscheint im Dashboard (status «zuletzt») und im Protokoll
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {arbeit['art']}: {e}")
            finally:
                if self.arbeit is arbeit:
                    self.arbeit = None

        self._thread = threading.Thread(target=lauf, name=arbeit["art"], daemon=True)
        self._thread.start()

    def erstellen_hintergrund(self):
        arbeit = {"art": "backup", "fertig": 0, "gesamt": 0, "seit": time.time()}
        self._im_hintergrund(arbeit, lambda: self.erstellen(arbeit))

    def taeglich_hintergrund(self):
        """Für den Start: nur wenn heute noch keines da ist (die Prüfung selbst ist schnell)."""
        if self._heute_schon():
            return False
        self.erstellen_hintergrund()
        return True

    def wiederherstellen_hintergrund(self, name: str, zielordner: str) -> str:
        _q, ziel, _m, noetig = self._wiederherstellen_pruefen(name, zielordner, self.ordner)   # Fehler sofort melden
        arbeit = {"art": "wiederherstellen", "fertig": 0, "gesamt": noetig, "seit": time.time()}
        self._im_hintergrund(arbeit, lambda: self.wiederherstellen(name, zielordner, arbeit))
        return str(ziel)

    def warten(self, sekunden: float = 60) -> bool:
        """Für Tests: wartet, bis die Arbeit im Hintergrund fertig ist."""
        if self._thread:
            self._thread.join(sekunden)
            return not self._thread.is_alive()
        return True


def _platz(ordner: Path):
    try:
        p = shutil.disk_usage(ordner)
        return {"frei": p.free, "gesamt": p.total}
    except OSError:
        return None


def _zeit_aus_name(stem: str) -> str:
    """2026-10-24_035512 -> 2026-10-24T03:55:12"""
    d, t = stem.split("_")
    return f"{d}T{t[:2]}:{t[2:4]}:{t[4:6]}"
