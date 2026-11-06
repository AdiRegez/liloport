"""Zugriff auf den Inhalte-Ordner: site.json, Seiten-JSON, Verzeichnisse als echte Ordner."""
import json
import re
import shutil
from datetime import date, datetime
from pathlib import Path

from . import slugs

NIVEAUS = ("amateur", "profi")
MENUE_OPTIONEN = ("voll", "seitenmenue", "keine")
INTERN = "_wiki"


class StoreFehler(Exception):
    """Fehler mit einer Meldung, die der Oberfläche gezeigt werden kann."""


def jetzt() -> str:
    """Zeitstempel ohne Mikrosekunden, ISO 8601."""
    return datetime.now().replace(microsecond=0).isoformat()


def _leeres_site() -> dict:
    """Grundzustand von site.json für einen neuen Inhalte-Ordner."""
    return {"version": 1, "titel": "Mein Liloport", "niveau": "amateur",
            "verzeichnisse": [], "export": {"autorAnzeigen": False, "datumAnzeigen": False}}


def tags_pruefen(tags) -> list:
    """Bis 20 Tags à 40 Zeichen, ohne # und Kommas, ohne Doppelte (Gross/Klein egal)."""
    if isinstance(tags, str):
        tags = tags.split(",")
    if not isinstance(tags, list):
        raise StoreFehler("Tags müssen eine Liste sein.")
    ergebnis, gesehen = [], set()
    for t in tags:
        t = re.sub(r"\s+", " ", str(t or "").replace(",", " ")).strip().lstrip("#").strip()[:40]
        if t and t.lower() not in gesehen:
            gesehen.add(t.lower())
            ergebnis.append(t)
    return ergebnis[:20]


def datum_pruefen(datum) -> str:
    """Leer oder JJJJ-MM-TT."""
    datum = str(datum or "").strip()
    if not datum:
        return ""
    try:
        return date.fromisoformat(datum).isoformat()
    except ValueError:
        raise StoreFehler("Ungültiges Datum.")


class Store:
    """Liest und schreibt den Inhalte-Ordner; kennt keine HTML-Erzeugung."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.letzte_umbenennung = None  # (alter_ordner, neuer_ordner) nach verzeichnis_aendern

    # ---------- Grundlagen ----------

    def anlegen(self):
        """Legt den Inhalte-Ordner mit site.json und _wiki/ an, falls nicht vorhanden."""
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / INTERN).mkdir(exist_ok=True)
        if not (self.root / "site.json").exists():
            self.site_speichern(_leeres_site())

    def sicherer_pfad(self, relativ: str) -> Path:
        """Löst einen relativen Pfad auf und weist alles ausserhalb des Inhalte-Ordners ab."""
        relativ = (relativ or "").replace("\\", "/").lstrip("/")
        ziel = (self.root / relativ).resolve()
        if ziel != self.root and self.root not in ziel.parents:
            raise StoreFehler("Pfad liegt ausserhalb des Inhalte-Ordners.")
        return ziel

    def site_laden(self) -> dict:
        """Liest site.json."""
        with open(self.root / "site.json", encoding="utf-8") as f:
            return json.load(f)

    def site_speichern(self, site: dict):
        """Schreibt site.json."""
        self._json_schreiben(self.root / "site.json", site)

    @staticmethod
    def _json_schreiben(pfad: Path, daten):
        """Schreibt JSON lesbar und UTF-8."""
        pfad.parent.mkdir(parents=True, exist_ok=True)
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=2)
            f.write("\n")

    def niveau_setzen(self, niveau: str):
        """Speichert das globale Niveau (amateur / profi)."""
        if niveau not in NIVEAUS:
            raise StoreFehler("Unbekanntes Niveau.")
        site = self.site_laden()
        site["niveau"] = niveau
        self.site_speichern(site)

    # ---------- Verzeichnisse ----------

    def verzeichnis(self, site: dict, vid: str) -> dict:
        """Findet ein Verzeichnis per ID."""
        for v in site["verzeichnisse"]:
            if v["id"] == vid:
                return v
        raise StoreFehler("Verzeichnis nicht gefunden.")

    def kinder(self, site: dict, vid) -> list:
        """Alle direkten Unterverzeichnisse von vid (None = oberste Ebene)."""
        return sorted((v for v in site["verzeichnisse"] if v.get("eltern") == vid),
                      key=lambda v: (v.get("reihenfolge", 0), v["name"].lower()))

    def _neue_id(self, site: dict) -> str:
        """Nächste freie Verzeichnis-ID d1, d2, …"""
        n = 1
        ids = {v["id"] for v in site["verzeichnisse"]}
        while f"d{n}" in ids:
            n += 1
        return f"d{n}"

    def verzeichnis_anlegen(self, name: str, eltern=None, in_menue=True) -> dict:
        """Legt ein Verzeichnis in site.json und als Ordner an."""
        name = (name or "").strip()
        if not name:
            raise StoreFehler("Der Name darf nicht leer sein.")
        site = self.site_laden()
        eltern_ordner = ""
        if eltern:
            eltern_ordner = self.verzeichnis(site, eltern)["ordner"]
        geschwister = {Path(v["ordner"]).name for v in self.kinder(site, eltern)}
        slug = slugs.eindeutig(slugs.slugify(name), geschwister)
        if not eltern and slug.startswith("_"):
            raise StoreFehler("Ordnernamen dürfen nicht mit _ beginnen.")
        ordner = f"{eltern_ordner}/{slug}" if eltern_ordner else slug
        if self.sicherer_pfad(ordner).exists():
            raise StoreFehler(f"Der Ordner «{ordner}» existiert bereits.")
        neu = {"id": self._neue_id(site), "name": name, "ordner": ordner,
               "inMenue": bool(in_menue), "reihenfolge": len(geschwister),
               "eltern": eltern or None, "seiten": []}
        self.sicherer_pfad(ordner).mkdir(parents=True)
        site["verzeichnisse"].append(neu)
        self.site_speichern(site)
        return neu

    def verzeichnis_aendern(self, vid: str, name=None, in_menue=None) -> dict:
        """Benennt ein Verzeichnis um (verschiebt den Ordner) oder ändert die Menü-Anzeige."""
        site = self.site_laden()
        v = self.verzeichnis(site, vid)
        if in_menue is not None:
            v["inMenue"] = bool(in_menue)
        if name is not None and name.strip() and name.strip() != v["name"]:
            name = name.strip()
            geschwister = {Path(x["ordner"]).name for x in self.kinder(site, v.get("eltern"))
                           if x["id"] != vid}
            neuer_slug = slugs.eindeutig(slugs.slugify(name), geschwister)
            alter_ordner = v["ordner"]
            eltern_ordner = str(Path(alter_ordner).parent).replace("\\", "/")
            neuer_ordner = f"{eltern_ordner}/{neuer_slug}" if eltern_ordner != "." else neuer_slug
            if neuer_ordner != alter_ordner:
                shutil.move(self.sicherer_pfad(alter_ordner), self.sicherer_pfad(neuer_ordner))
                for x in site["verzeichnisse"]:
                    if x["ordner"] == alter_ordner or x["ordner"].startswith(alter_ordner + "/"):
                        x["ordner"] = neuer_ordner + x["ordner"][len(alter_ordner):]
                    x["seiten"] = [self._redirect_umbenennen(s, alter_ordner, neuer_ordner) for s in x["seiten"]]
                self.letzte_umbenennung = (alter_ordner, neuer_ordner)
            v["name"] = name
        self.site_speichern(site)
        return v

    def verzeichnis_verschieben(self, vid: str, neue_eltern=None) -> dict:
        """Verschiebt ein Verzeichnis samt Unterverzeichnissen und Seiten in ein anderes Verzeichnis
        oder auf die oberste Ebene (neue_eltern=None). Merkt die Umbenennung in letzte_umbenennung,
        damit der Server Links, Anhänge, Verlauf und Kommentare nachziehen kann."""
        site = self.site_laden()
        v = self.verzeichnis(site, vid)
        neue_eltern = neue_eltern or None
        if neue_eltern == vid:
            raise StoreFehler("Ein Verzeichnis kann nicht in sich selbst verschoben werden.")
        eltern_ordner = ""
        if neue_eltern:
            ziel = self.verzeichnis(site, neue_eltern)
            lauf = ziel
            while lauf is not None:   # Ziel darf kein Unterverzeichnis des verschobenen Verzeichnisses sein
                if lauf["id"] == vid:
                    raise StoreFehler("Ein Verzeichnis kann nicht in eines seiner Unterverzeichnisse verschoben werden.")
                lauf = next((x for x in site["verzeichnisse"] if x["id"] == lauf.get("eltern")), None)
            eltern_ordner = ziel["ordner"]
        if (v.get("eltern") or None) == neue_eltern:
            raise StoreFehler("Das Verzeichnis liegt bereits dort.")
        alter_ordner = v["ordner"]
        geschwister = {Path(x["ordner"]).name for x in self.kinder(site, neue_eltern) if x["id"] != vid}
        slug = slugs.eindeutig(Path(alter_ordner).name, geschwister)
        if not neue_eltern and slug.startswith("_"):
            raise StoreFehler("Ordnernamen dürfen nicht mit _ beginnen.")
        neuer_ordner = f"{eltern_ordner}/{slug}" if eltern_ordner else slug
        if self.sicherer_pfad(neuer_ordner).exists():
            raise StoreFehler(f"Der Ordner «{neuer_ordner}» existiert bereits.")
        shutil.move(self.sicherer_pfad(alter_ordner), self.sicherer_pfad(neuer_ordner))
        for x in site["verzeichnisse"]:
            if x["ordner"] == alter_ordner or x["ordner"].startswith(alter_ordner + "/"):
                x["ordner"] = neuer_ordner + x["ordner"][len(alter_ordner):]
            x["seiten"] = [self._redirect_umbenennen(s, alter_ordner, neuer_ordner) for s in x["seiten"]]
        self.letzte_umbenennung = (alter_ordner, neuer_ordner)
        v["eltern"] = neue_eltern
        v["reihenfolge"] = len(geschwister)
        self.site_speichern(site)
        return v

    @staticmethod
    def _redirect_umbenennen(eintrag: str, alt: str, neu: str) -> str:
        """Passt einen Redirect-Eintrag ->alt/… an einen umbenannten Ordner an."""
        if not eintrag.startswith("->"):
            return eintrag
        ziel = eintrag[2:]
        if ziel == alt or ziel.startswith(alt + "/"):
            return "->" + neu + ziel[len(alt):]
        return eintrag

    # ---------- Redirect-Seiten ----------

    def redirect_hinzufuegen(self, vid: str, ziel_pfad: str) -> str:
        """Trägt eine Seite als Redirect in ein weiteres Verzeichnis ein."""
        site = self.site_laden()
        v = self.verzeichnis(site, vid)
        self.seite_laden(ziel_pfad)
        ziel_ordner, slug = ziel_pfad.rsplit("/", 1)
        if ziel_ordner == v["ordner"]:
            raise StoreFehler("Die Seite liegt bereits in diesem Verzeichnis.")
        if "->" + ziel_pfad in v["seiten"]:
            raise StoreFehler("Die Seite ist hier bereits zugeordnet.")
        if slug in v["seiten"] or self.sicherer_pfad(f"{v['ordner']}/{slug}.html").exists():
            raise StoreFehler(f"Im Verzeichnis gibt es schon eine Datei «{slug}.html».")
        v["seiten"].append("->" + ziel_pfad)
        self.site_speichern(site)
        return "->" + ziel_pfad

    def redirect_entfernen(self, vid: str, ziel_pfad: str):
        """Entfernt einen Redirect-Eintrag samt HTML-Datei."""
        site = self.site_laden()
        v = self.verzeichnis(site, vid)
        eintrag = "->" + ziel_pfad
        if eintrag not in v["seiten"]:
            raise StoreFehler("Redirect nicht gefunden.")
        v["seiten"].remove(eintrag)
        self._redirect_datei_loeschen(v, ziel_pfad)
        self.site_speichern(site)

    def redirects_entfernen(self, ziel_pfad: str):
        """Entfernt alle Redirects, die auf eine Seite zeigen (beim Löschen der Seite)."""
        site = self.site_laden()
        for v in site["verzeichnisse"]:
            if "->" + ziel_pfad in v["seiten"]:
                v["seiten"].remove("->" + ziel_pfad)
                self._redirect_datei_loeschen(v, ziel_pfad)
        self.site_speichern(site)

    def _redirect_datei_loeschen(self, v: dict, ziel_pfad: str):
        datei = self.sicherer_pfad(f"{v['ordner']}/{ziel_pfad.rsplit('/', 1)[-1]}.html")
        if datei.exists():
            datei.unlink()

    def verzeichnis_loeschen(self, vid: str):
        """Löscht ein leeres Verzeichnis (keine Seiten, keine Unterverzeichnisse).

        Einträge zu Dateien, die es nicht mehr gibt – etwa weil der Ordner oder einzelne Seiten von
        Hand im Dateimanager gelöscht wurden –, zählen nicht als Inhalt und werden mit ausgetragen."""
        site = self.site_laden()
        v = self.verzeichnis(site, vid)
        ordner = self.sicherer_pfad(v["ordner"])

        def existiert(eintrag: str) -> bool:
            if eintrag.startswith("->"):
                return self.sicherer_pfad(eintrag[2:] + ".json").is_file()
            return (ordner / (eintrag + ".json")).is_file()
        uebrig = [s for s in v["seiten"] if existiert(s)]
        if uebrig != v["seiten"]:
            v["seiten"] = uebrig
            self.site_speichern(site)
        if v["seiten"]:
            raise StoreFehler("Das Verzeichnis enthält noch Seiten.")
        if self.kinder(site, vid):
            raise StoreFehler("Das Verzeichnis enthält noch Unterverzeichnisse.")
        if ordner.exists():
            shutil.rmtree(ordner)
        site["verzeichnisse"] = [x for x in site["verzeichnisse"] if x["id"] != vid]
        self.site_speichern(site)

    # ---------- Seiten ----------

    def seiten_pfad(self, v: dict, slug: str) -> str:
        """Relativer Pfad einer Seite ohne Endung, z. B. semester-1/lernjournal."""
        return f"{v['ordner']}/{slug}"

    def seite_laden(self, pfad: str) -> dict:
        """Liest die JSON einer Seite."""
        datei = self.sicherer_pfad(pfad + ".json")
        if not datei.exists():
            raise StoreFehler("Seite nicht gefunden.")
        with open(datei, encoding="utf-8") as f:
            return json.load(f)

    def seite_speichern(self, pfad: str, seite: dict):
        """Schreibt die JSON einer Seite."""
        self._json_schreiben(self.sicherer_pfad(pfad + ".json"), seite)

    def seite_anlegen(self, titel: str, vid: str, menue="voll", bloecke=None) -> tuple:
        """Legt eine neue Seite an und trägt sie im Verzeichnis ein; gibt (pfad, seite) zurück."""
        titel = (titel or "").strip()
        if not titel:
            raise StoreFehler("Der Titel darf nicht leer sein.")
        if menue not in MENUE_OPTIONEN:
            raise StoreFehler("Unbekannte Menü-Option.")
        site = self.site_laden()
        v = self.verzeichnis(site, vid)
        belegt = {s[2:].rsplit("/", 1)[-1] if s.startswith("->") else s for s in v["seiten"]}
        belegt |= {p.stem for p in self.sicherer_pfad(v["ordner"]).glob("*.json")}
        slug = slugs.eindeutig(slugs.slugify(titel), belegt)
        seite = {"slug": slug, "titel": titel, "erstellt": jetzt(), "geaendert": jetzt(),
                 "datum": date.today().isoformat(), "tags": [],
                 "menue": menue, "kommentare": False, "css": "",
                 "bloecke": bloecke if bloecke is not None else []}
        pfad = self.seiten_pfad(v, slug)
        self.seite_speichern(pfad, seite)
        v["seiten"].append(slug)
        self.site_speichern(site)
        return pfad, seite

    def seite_aktualisieren(self, pfad: str, titel=None, menue=None, bloecke=None, css=None, kommentare=None,
                            datum=None, tags=None, verweise=None, gliederung=None) -> dict:
        """Ändert Titel, Menü-Option, Blöcke, Seiten-CSS, Kommentar-Flag, Datum, Tags oder «Verlinkt von» einer Seite."""
        seite = self.seite_laden(pfad)
        if verweise is not None:
            if verweise:
                seite.pop("verweise", None)      # Standard: «Verlinkt von» zeigen
            else:
                seite["verweise"] = False
        if gliederung is not None:
            # Profi: Hierarchie der Überschriften sichtbar machen (linien | flaechen | nummern); leer = aus
            if gliederung in ("linien", "flaechen", "nummern"):
                seite["gliederung"] = gliederung
            else:
                seite.pop("gliederung", None)
        if datum is not None:
            seite["datum"] = datum_pruefen(datum)
        if tags is not None:
            seite["tags"] = tags_pruefen(tags)
        if css is not None:
            seite["css"] = css
        if kommentare is not None:
            seite["kommentare"] = bool(kommentare)
        if titel is not None and titel.strip():
            seite["titel"] = titel.strip()
        if menue is not None:
            if menue not in MENUE_OPTIONEN:
                raise StoreFehler("Unbekannte Menü-Option.")
            seite["menue"] = menue
        if bloecke is not None:
            seite["bloecke"] = bloecke
        seite["geaendert"] = jetzt()
        self.seite_speichern(pfad, seite)
        return seite

    def seite_verschieben(self, pfad: str, ziel_vid: str) -> str:
        """Verschiebt JSON und HTML einer Seite in ein anderes Verzeichnis; gibt den neuen Pfad zurück.

        Anhänge, Verlauf, Kommentare und interne Links passt der Server danach mit den vorhandenen
        Umbenennungs-Helfern an (alt = neu auf Seitenebene).
        """
        site = self.site_laden()
        ziel = self.verzeichnis(site, ziel_vid)
        ordner, slug = pfad.rsplit("/", 1)
        quelle = next((v for v in site["verzeichnisse"] if v["ordner"] == ordner and slug in v["seiten"]), None)
        if quelle is None:
            raise StoreFehler("Seite nicht gefunden.")
        if quelle["id"] == ziel["id"]:
            raise StoreFehler("Die Seite liegt bereits in diesem Verzeichnis.")
        belegt = {s[2:].rsplit("/", 1)[-1] if s.startswith("->") else s for s in ziel["seiten"]}
        belegt |= {p.stem for p in self.sicherer_pfad(ziel["ordner"]).glob("*.json")}
        neuer_slug = slugs.eindeutig(slug, belegt)
        neu = self.seiten_pfad(ziel, neuer_slug)
        for endung in (".json", ".html"):
            datei = self.sicherer_pfad(pfad + endung)
            if datei.exists():
                datei.rename(self.sicherer_pfad(neu + endung))
        seite = self.seite_laden(neu)
        seite["slug"] = neuer_slug
        self.seite_speichern(neu, seite)
        quelle["seiten"].remove(slug)
        ziel["seiten"].append(neuer_slug)
        # Weiterleitungen alter Fassungen auf diese Seite mitziehen bzw. entfernen, wenn sie ins Ziel zeigen würden
        for v in site["verzeichnisse"]:
            v["seiten"] = [("->" + neu if s == "->" + pfad else s) for s in v["seiten"] if not (s == "->" + pfad and v["id"] == ziel["id"])]
        self.site_speichern(site)
        self._redirect_datei_loeschen(ziel, pfad)
        return neu

    def seite_loeschen(self, pfad: str):
        """Entfernt JSON und HTML einer Seite und den Eintrag im Verzeichnis."""
        site = self.site_laden()
        ordner, slug = pfad.rsplit("/", 1)
        for v in site["verzeichnisse"]:
            if v["ordner"] == ordner and slug in v["seiten"]:
                v["seiten"].remove(slug)
        for endung in (".json", ".html"):
            datei = self.sicherer_pfad(pfad + endung)
            if datei.exists():
                datei.unlink()
        self.site_speichern(site)

    def alle_seiten(self, site=None) -> list:
        """Liste aller Seiten als (verzeichnis, pfad, seite), in Verzeichnisreihenfolge."""
        site = site or self.site_laden()
        ergebnis = []
        for v in site["verzeichnisse"]:
            for slug in v["seiten"]:
                if slug.startswith("->"):
                    continue
                pfad = self.seiten_pfad(v, slug)
                try:
                    ergebnis.append((v, pfad, self.seite_laden(pfad)))
                except StoreFehler:
                    continue
        return ergebnis
