"""Versionen pro Seite (_wiki/history/<pfad>/<zeitstempel>.json) und Papierkorb für gelöschte Seiten."""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from .store import INTERN, Store, StoreFehler, jetzt

MAX_VERSIONEN = 50
MAX_TAGE = 90
PAPIERKORB_TAGE = 30


def _stempel() -> str:
    """Dateitauglicher Zeitstempel, sortierbar: 2026-10-24T03-55-12."""
    return datetime.now().replace(microsecond=0).isoformat().replace(":", "-")


def _stempel_lesen(name: str) -> str:
    return name[:10] + "T" + name[11:19].replace("-", ":")


def _sortierschluessel(datei: Path):
    """Sortiert Versionsdateien chronologisch, auch bei mehreren pro Sekunde (-2, -3, …)."""
    stem = datei.stem
    basis, _, zusatz = stem[:19], stem[19:20], stem[20:]
    return (basis, int(zusatz) if zusatz.isdigit() else 1)


class History:
    """Legt Fassungen ab, listet sie, stellt sie wieder her und räumt alte auf."""

    def __init__(self, store: Store):
        self.store = store
        self.wurzel = store.root / INTERN / "history"
        self.papierkorb_ordner = self.wurzel / "_geloescht"

    # ---------- Versionen ----------

    def _ordner(self, pfad: str) -> Path:
        return self.wurzel / pfad

    def sichern(self, pfad: str, seite: dict):
        """Legt die übergebene Fassung als Version ab (vor einer Änderung aufrufen)."""
        ordner = self._ordner(pfad)
        ordner.mkdir(parents=True, exist_ok=True)
        inhalt = json.dumps(seite, ensure_ascii=False, sort_keys=True)
        letzte = self._dateien(pfad)
        if letzte and letzte[0].read_text(encoding="utf-8").strip() == inhalt.strip():
            return  # identisch mit der letzten Version, nichts zu tun
        name = _stempel()
        ziel = ordner / f"{name}.json"
        n = 1
        while ziel.exists():
            n += 1
            ziel = ordner / f"{name}-{n}.json"
        ziel.write_text(inhalt + "\n", encoding="utf-8")
        self._aufraeumen(pfad)

    def _dateien(self, pfad: str) -> list:
        ordner = self._ordner(pfad)
        if not ordner.exists():
            return []
        return sorted(ordner.glob("*.json"), key=_sortierschluessel, reverse=True)

    def _aufraeumen(self, pfad: str):
        grenze = (datetime.now() - timedelta(days=MAX_TAGE)).isoformat()
        for i, datei in enumerate(self._dateien(pfad)):
            if i >= MAX_VERSIONEN or _stempel_lesen(datei.stem) < grenze:
                datei.unlink()

    def versionen(self, pfad: str) -> list:
        """Liste der Versionen (neueste zuerst) mit Zeitstempel und Anzahl geänderter Blöcke zur aktuellen Fassung."""
        aktuell = self.store.seite_laden(pfad)
        ergebnis = []
        for datei in self._dateien(pfad):
            try:
                fassung = json.loads(datei.read_text(encoding="utf-8"))
            except ValueError:
                continue
            diff = vergleichen(fassung, aktuell)
            ergebnis.append({"id": datei.stem, "zeit": _stempel_lesen(datei.stem)[:19], "titel": fassung.get("titel", ""),
                             "bloecke": len(fassung.get("bloecke", [])),
                             "geaendert": len(diff["geaendert"]) + len(diff["neu"]) + len(diff["entfernt"]), "diff": diff})
        return ergebnis

    def laden(self, pfad: str, vid: str) -> dict:
        """Liest eine bestimmte Version."""
        if not re.fullmatch(r"[0-9T-]+(-\d+)?", vid):
            raise StoreFehler("Ungültige Versions-ID.")
        datei = self._ordner(pfad) / f"{vid}.json"
        if not datei.exists():
            raise StoreFehler("Version nicht gefunden.")
        return json.loads(datei.read_text(encoding="utf-8"))

    def wiederherstellen(self, pfad: str, vid: str) -> dict:
        """Macht eine Version zur aktuellen Fassung; die bisherige Fassung wandert vorher in die Historie."""
        fassung = self.laden(pfad, vid)
        aktuell = self.store.seite_laden(pfad)
        self.sichern(pfad, aktuell)
        fassung["slug"] = aktuell["slug"]
        fassung["geaendert"] = jetzt()
        self.store.seite_speichern(pfad, fassung)
        return fassung

    def verschieben(self, alt: str, neu: str):
        """Nach einer Ordnerumbenennung: Historie mitnehmen."""
        quelle = self._ordner(alt)
        if quelle.exists():
            ziel = self._ordner(neu)
            ziel.parent.mkdir(parents=True, exist_ok=True)
            quelle.rename(ziel)

    # ---------- Papierkorb ----------

    def in_papierkorb(self, pfad: str, verzeichnis_id: str, assets=None):
        """Legt die Seite vor dem Löschen in den Papierkorb (30 Tage), samt Anhängen, die mitgelöscht würden."""
        seite = self.store.seite_laden(pfad)
        self.papierkorb_ordner.mkdir(parents=True, exist_ok=True)
        kennung = f"{_stempel()}__{pfad.replace('/', '__')}"
        anhaenge = []
        if assets is not None:
            registry = assets.laden()
            ablage = self.papierkorb_ordner / f"{kennung}.anhaenge"
            for e in assets.loesch_vorschau(pfad)["geloescht"]:
                quelle = self.store.sicherer_pfad(e["datei"])
                if not quelle.exists():
                    continue
                ablage.mkdir(parents=True, exist_ok=True)
                ziel = ablage / f"{e['id']}{quelle.suffix}"
                ziel.write_bytes(quelle.read_bytes())
                anhaenge.append({"id": e["id"], "ablage": ziel.name, "eintrag": registry[e["id"]]})
        eintrag = {"pfad": pfad, "verzeichnis": verzeichnis_id, "geloescht": jetzt(), "seite": seite, "anhaenge": anhaenge}
        (self.papierkorb_ordner / f"{kennung}.json").write_text(json.dumps(eintrag, ensure_ascii=False, indent=2), encoding="utf-8")
        # Versionen der Seite mitnehmen, damit sie nach dem Wiederherstellen noch da sind
        versionen = self._ordner(pfad)
        if versionen.exists():
            versionen.rename(self.papierkorb_ordner / f"{kennung}.versionen")
        self._papierkorb_aufraeumen()

    def _papierkorb_aufraeumen(self):
        grenze = (datetime.now() - timedelta(days=PAPIERKORB_TAGE)).isoformat()
        for datei in self.papierkorb_ordner.glob("*.json"):
            if _stempel_lesen(datei.stem.split("__", 1)[0]) < grenze:
                datei.unlink()
                self._beilagen_loeschen(datei)

    def _beilagen_loeschen(self, datei: Path):
        """Entfernt Versionen- und Anhangordner eines Papierkorb-Eintrags."""
        for endung in (".versionen", ".anhaenge"):
            ordner = datei.with_suffix(endung)
            if ordner.exists():
                for v in ordner.glob("*"):
                    v.unlink()
                ordner.rmdir()

    def papierkorb(self) -> list:
        """Alle gelöschten Seiten, neueste zuerst."""
        if not self.papierkorb_ordner.exists():
            return []
        ergebnis = []
        for datei in sorted(self.papierkorb_ordner.glob("*.json"), reverse=True):
            try:
                e = json.loads(datei.read_text(encoding="utf-8"))
            except ValueError:
                continue
            ergebnis.append({"id": datei.stem, "pfad": e["pfad"], "titel": e["seite"].get("titel", ""),
                             "geloescht": e["geloescht"], "bloecke": len(e["seite"].get("bloecke", [])),
                             "anhaenge": len(e.get("anhaenge", []))})
        return ergebnis

    def aus_papierkorb(self, kennung: str, assets=None) -> str:
        """Stellt eine gelöschte Seite samt Anhängen wieder her; gibt den neuen Pfad zurück."""
        if not re.fullmatch(r"[0-9A-Za-z_.-]+", kennung):
            raise StoreFehler("Ungültige Kennung.")
        datei = self.papierkorb_ordner / f"{kennung}.json"
        if not datei.exists():
            raise StoreFehler("Eintrag nicht gefunden.")
        e = json.loads(datei.read_text(encoding="utf-8"))
        site = self.store.site_laden()
        vid = e.get("verzeichnis")
        if not any(v["id"] == vid for v in site["verzeichnisse"]):
            if not site["verzeichnisse"]:
                raise StoreFehler("Kein Verzeichnis vorhanden, in das die Seite zurückkehren könnte.")
            vid = site["verzeichnisse"][0]["id"]
        seite = e["seite"]
        pfad, neu = self.store.seite_anlegen(seite.get("titel") or "Seite", vid, seite.get("menue", "voll"), seite.get("bloecke", []))
        neu["css"] = seite.get("css", "")
        if seite.get("gliederung"):
            neu["gliederung"] = seite["gliederung"]
        neu["erstellt"] = seite.get("erstellt", neu["erstellt"])
        self.store.seite_speichern(pfad, neu)
        if assets is not None and e.get("anhaenge"):
            self._anhaenge_zurueck(e["anhaenge"], datei.with_suffix(".anhaenge"), pfad, assets)
        ablage = datei.with_suffix(".anhaenge")
        if ablage.exists():
            for a in ablage.glob("*"):
                a.unlink()
            ablage.rmdir()
        versionen = datei.with_suffix(".versionen")
        if versionen.exists():
            ziel = self._ordner(pfad)
            ziel.parent.mkdir(parents=True, exist_ok=True)
            if not ziel.exists():
                versionen.rename(ziel)
        datei.unlink()
        return pfad

    def _anhaenge_zurueck(self, anhaenge: list, ablage: Path, pfad: str, assets):
        """Legt die mitgenommenen Anhänge wieder unter assets/<slug>/ ab und trägt sie in die Registry ein."""
        registry = assets.laden()
        slug = pfad.rsplit("/", 1)[-1]
        zielordner = self.store.sicherer_pfad("assets/" + slug)
        for a in anhaenge:
            quelle = ablage / a["ablage"]
            if not quelle.exists() or a["id"] in registry:
                continue
            zielordner.mkdir(parents=True, exist_ok=True)
            name = Path(a["eintrag"]["datei"]).name
            ziel = zielordner / name
            n = 2
            while ziel.exists():
                ziel = zielordner / f"{ziel.stem.rsplit('-', 1)[0] if n > 2 else ziel.stem}-{n}{ziel.suffix}"
                n += 1
            ziel.write_bytes(quelle.read_bytes())
            eintrag = dict(a["eintrag"])
            eintrag["datei"] = ziel.relative_to(self.store.root).as_posix()
            eintrag["heimat"] = pfad
            eintrag["referenzen"] = []
            registry[a["id"]] = eintrag
        assets.speichern(registry)
        assets.referenzen_setzen(pfad, self.store.seite_laden(pfad))

    def endgueltig(self, kennung: str):
        """Löscht einen Papierkorb-Eintrag samt Versionen und Anhängen."""
        datei = self.papierkorb_ordner / f"{kennung}.json"
        if datei.exists():
            datei.unlink()
        self._beilagen_loeschen(datei)


def vergleichen(alt: dict, neu: dict) -> dict:
    """Block-für-Block-Vergleich zweier Fassungen anhand der Block-IDs."""
    def flach(seite):
        ergebnis = {}
        def rek(bl):
            for b in bl or []:
                ergebnis[b.get("id")] = json.dumps({k: v for k, v in b.items() if k != "spalten"}, sort_keys=True, ensure_ascii=False)
                if b.get("typ") == "spalten":
                    for sp in b.get("spalten", []):
                        rek(sp)
        rek(seite.get("bloecke"))
        return ergebnis
    a, n = flach(alt), flach(neu)
    return {"neu": [k for k in n if k not in a], "entfernt": [k for k in a if k not in n],
            "geaendert": [k for k in n if k in a and a[k] != n[k]],
            "titel": alt.get("titel") != neu.get("titel"), "css": (alt.get("css") or "") != (neu.get("css") or "")}
