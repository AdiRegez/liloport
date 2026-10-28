"""Anhänge: Upload, Registry (_wiki/assets.json), Referenzzählung und Löschlogik."""
import io
import json
import re
import secrets
from pathlib import Path

from . import slugs
from .store import INTERN, Store, StoreFehler

REGISTRY = "assets.json"
BLOCK = 1024 * 1024  # Upload wird in 1-MB-Stücken auf die Platte geschrieben, kein Grössenlimit
HINWEIS_GROESSE = 50 * 1024 * 1024

# Erkennung des Dateityps anhand des Inhalts, nicht der Endung.
_MAGIC = [
    (b"\xff\xd8\xff", "bild", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "bild", "png"),
    (b"GIF87a", "bild", "gif"),
    (b"GIF89a", "bild", "gif"),
    (b"%PDF", "pdf", "pdf"),
    (b"\x1a\x45\xdf\xa3", "video", "webm"),
    (b"PK\x03\x04", "datei", "zip"),
]


def typ_erkennen(daten: bytes):
    """Gibt (typ, endung) zurück oder wirft StoreFehler bei unbekanntem Format."""
    kopf = daten[:64]
    for magic, typ, endung in _MAGIC:
        if kopf.startswith(magic):
            return typ, endung
    if kopf[:4] == b"RIFF" and kopf[8:12] == b"WEBP":
        return "bild", "webp"
    if kopf[4:8] == b"ftyp":
        return "video", "mp4"
    text = kopf.lstrip().lower()
    if text.startswith(b"<svg") or (text.startswith(b"<?xml") and b"<svg" in daten[:2048].lower()):
        return "bild", "svg"
    raise StoreFehler("Dateityp nicht erlaubt. Erlaubt: jpg, png, gif, webp, svg, mp4, webm, pdf, zip.")


class Assets:
    """Verwaltet die Dateien unter assets/ und die Registry."""

    def __init__(self, store: Store):
        self.store = store
        self.datei = store.root / INTERN / REGISTRY

    # ---------- Registry ----------

    def laden(self) -> dict:
        """Liest assets.json (leer, falls nicht vorhanden)."""
        if not self.datei.exists():
            return {}
        with open(self.datei, encoding="utf-8") as f:
            return json.load(f)

    def speichern(self, registry: dict):
        """Schreibt assets.json."""
        self.datei.parent.mkdir(exist_ok=True)
        with open(self.datei, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)
            f.write("\n")

    def liste(self) -> list:
        """Alle Anhänge als Liste mit ID, neueste zuerst."""
        registry = self.laden()
        eintraege = [dict(id=k, **v) for k, v in registry.items()]
        eintraege.sort(key=lambda e: e.get("hochgeladen", ""), reverse=True)
        return eintraege

    def verwaist(self) -> list:
        """Anhänge, die keine Seite mehr referenziert."""
        return [e for e in self.liste() if not e.get("referenzen")]

    # ---------- Upload ----------

    def _asset_ordner(self, heimat_pfad: str) -> Path:
        """Ordner assets/<slug>/ für die Heimatseite; Slug-Kollisionen über Registry vermeiden."""
        slug = heimat_pfad.rsplit("/", 1)[-1]
        registry = self.laden()
        for e in registry.values():
            if e["heimat"] == heimat_pfad:
                return self.store.sicherer_pfad(e["datei"]).parent
        belegt = {Path(e["datei"]).parent.name for e in registry.values() if e["heimat"] != heimat_pfad}
        return self.store.sicherer_pfad("assets/" + slugs.eindeutig(slug, belegt))

    def hochladen(self, heimat_pfad: str, dateiname: str, daten: bytes) -> dict:
        """Speichert Bytes als Anhang (für kleine Dateien und Importe)."""
        return self.hochladen_strom(heimat_pfad, dateiname, io.BytesIO(daten), len(daten))

    def hochladen_strom(self, heimat_pfad: str, dateiname: str, quelle, laenge: int) -> dict:
        """Schreibt eine Datei stückweise nach assets/<slug>/ – ohne Grössenlimit, ohne alles im Speicher zu halten."""
        self.store.seite_laden(heimat_pfad)  # Heimatseite muss existieren
        if laenge <= 0:
            raise StoreFehler("Die Datei ist leer.")
        kopf = quelle.read(min(laenge, 4096))
        typ, endung = typ_erkennen(kopf)
        stamm = slugs.slugify(Path(dateiname or "datei").stem)
        ordner = self._asset_ordner(heimat_pfad)
        ordner.mkdir(parents=True, exist_ok=True)
        belegt = {p.stem for p in ordner.iterdir()}
        name = slugs.eindeutig(stamm, belegt) + "." + endung
        ziel = ordner / name
        teil = ziel.with_name(ziel.name + ".teil")
        geschrieben = len(kopf)
        try:
            with open(teil, "wb") as f:
                f.write(kopf)
                while geschrieben < laenge:
                    stueck = quelle.read(min(BLOCK, laenge - geschrieben))
                    if not stueck:
                        raise StoreFehler("Der Upload wurde unterbrochen.")
                    f.write(stueck)
                    geschrieben += len(stueck)
            teil.replace(ziel)
        except BaseException:
            teil.unlink(missing_ok=True)
            raise
        registry = self.laden()
        aid = secrets.token_hex(4)
        while aid in registry:
            aid = secrets.token_hex(4)
        registry[aid] = {
            "datei": ziel.relative_to(self.store.root).as_posix(),
            "typ": typ, "name": dateiname or name, "heimat": heimat_pfad,
            "groesse": geschrieben, "hochgeladen": _jetzt(), "referenzen": [],
        }
        self.speichern(registry)
        return dict(id=aid, **registry[aid], hinweis=geschrieben > HINWEIS_GROESSE)

    def loeschen(self, aid: str):
        """Löscht einen Anhang, der von keiner Seite mehr referenziert wird."""
        registry = self.laden()
        e = registry.get(aid)
        if not e:
            raise StoreFehler("Anhang nicht gefunden.")
        if e.get("referenzen"):
            raise StoreFehler("Der Anhang wird noch verwendet: " + ", ".join(e["referenzen"]))
        self._datei_entfernen(e["datei"])
        del registry[aid]
        self.speichern(registry)

    def _datei_entfernen(self, relativ: str):
        """Löscht eine Datei und den Ordner, falls er leer geworden ist."""
        datei = self.store.sicherer_pfad(relativ)
        if datei.exists():
            datei.unlink()
        ordner = datei.parent
        if ordner.exists() and ordner != self.store.root and not any(ordner.iterdir()):
            ordner.rmdir()

    # ---------- Referenzen ----------

    @staticmethod
    def ids_in_bloecken(bloecke) -> set:
        """Sammelt Asset-IDs aus Blöcken, auch in Spalten."""
        ids = set()
        for b in bloecke or []:
            if b.get("typ") in ("bild", "video", "pdf", "datei") and b.get("asset"):
                ids.add(b["asset"])
            if b.get("typ") == "spalten":
                for spalte in b.get("spalten", []):
                    ids |= Assets.ids_in_bloecken(spalte)
        return ids

    @staticmethod
    def pfade_in_html(bloecke, css) -> set:
        """Sammelt assets/…-Pfade aus HTML-Blöcken und dem Seiten-CSS (Profi)."""
        texte = [css or ""]
        for b in bloecke or []:
            if b.get("typ") == "html":
                texte.append(b.get("html", ""))
            if b.get("typ") == "spalten":
                for spalte in b.get("spalten", []):
                    texte.extend(x.get("html", "") for x in spalte if x.get("typ") == "html")
        gefunden = set()
        for text in texte:
            for m in re.finditer(r"assets/[A-Za-z0-9._/-]+", text):
                gefunden.add(m.group(0))
        return gefunden

    def referenzen_setzen(self, pfad: str, seite: dict):
        """Trägt die Seite bei allen genutzten Anhängen ein und bei allen anderen aus."""
        registry = self.laden()
        ids = self.ids_in_bloecken(seite.get("bloecke"))
        pfade = self.pfade_in_html(seite.get("bloecke"), seite.get("css"))
        for aid, e in registry.items():
            genutzt = aid in ids or e["datei"] in pfade
            refs = [r for r in e.get("referenzen", []) if r != pfad]
            if genutzt:
                refs.append(pfad)
            e["referenzen"] = refs
        self.speichern(registry)

    def pfade_umbenennen(self, alt: str, neu: str):
        """Nach einer Ordnerumbenennung: Heimat und Referenzen von alt/… auf neu/… umstellen."""
        registry = self.laden()

        def um(p):
            return neu + p[len(alt):] if p == alt or p.startswith(alt + "/") else p

        for e in registry.values():
            e["heimat"] = um(e["heimat"])
            e["referenzen"] = [um(r) for r in e.get("referenzen", [])]
        self.speichern(registry)

    # ---------- Löschen einer Seite ----------

    def loesch_vorschau(self, pfad: str) -> dict:
        """Die drei Listen für den Löschdialog: wird gelöscht, bleibt (mit Seiten), Redirects."""
        registry = self.laden()
        geloescht, bleibt = [], []
        for aid, e in registry.items():
            andere = [r for r in e.get("referenzen", []) if r != pfad]
            if e["heimat"] == pfad:
                if andere:
                    bleibt.append({"id": aid, "name": e["name"], "datei": e["datei"], "seiten": andere,
                                   "neueHeimat": andere[0]})
                else:
                    geloescht.append({"id": aid, "name": e["name"], "datei": e["datei"]})
        redirects = []
        site = self.store.site_laden()
        for v in site["verzeichnisse"]:
            for s in v["seiten"]:
                if s == "->" + pfad:
                    redirects.append({"verzeichnis": v["name"], "ordner": v["ordner"]})
        return {"geloescht": geloescht, "bleibt": bleibt, "redirects": redirects}

    def seite_loeschen(self, pfad: str) -> dict:
        """Löscht die Seite, ihre unreferenzierten Anhänge und Redirects; andere Anhänge wechseln Heimat."""
        vorschau = self.loesch_vorschau(pfad)
        registry = self.laden()
        for e in vorschau["geloescht"]:
            self._datei_entfernen(e["datei"])
            del registry[e["id"]]
        for e in vorschau["bleibt"]:
            eintrag = registry[e["id"]]
            eintrag["heimat"] = e["neueHeimat"]
            eintrag["referenzen"] = [r for r in eintrag["referenzen"] if r != pfad]
            neuer_ordner = self.store.sicherer_pfad("assets/" + e["neueHeimat"].rsplit("/", 1)[-1])
            neuer_ordner.mkdir(parents=True, exist_ok=True)
            alt = self.store.sicherer_pfad(eintrag["datei"])
            if alt.parent != neuer_ordner and alt.exists():
                belegt = {p.stem for p in neuer_ordner.iterdir()}
                neu = neuer_ordner / (slugs.eindeutig(alt.stem, belegt) + alt.suffix)
                alt.replace(neu)
                if not any(alt.parent.iterdir()):
                    alt.parent.rmdir()
                eintrag["datei"] = neu.relative_to(self.store.root).as_posix()
        for aid, e in registry.items():
            e["referenzen"] = [r for r in e.get("referenzen", []) if r != pfad]
        self.speichern(registry)
        self.store.redirects_entfernen(pfad)
        self.store.seite_loeschen(pfad)
        return vorschau


def _jetzt() -> str:
    from .store import jetzt
    return jetzt()
