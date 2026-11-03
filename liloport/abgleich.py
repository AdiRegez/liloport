"""Abgleich zwischen site.json und dem Inhalte-Ordner.

Wer Ordner oder Seiten direkt im Dateimanager löscht oder verschiebt, hinterlässt in site.json
Einträge, die ins Leere zeigen – und auf der Festplatte Dateien, die Liloport nicht kennt. Der
Abgleich erkennt beides, zeigt es im Dashboard und übernimmt es auf Wunsch: verwaiste Einträge
werden entfernt, unbekannte Seiten und Ordner aufgenommen. (Verschieben und Löschen in Liloport
selbst bleibt der bessere Weg – dabei ziehen Anhänge, Verlauf, Kommentare und interne Links mit.)
"""
import json
from pathlib import Path

from .store import Store, StoreFehler

# Ordner auf oberster Ebene, die nie Verzeichnisse sind; _… und versteckte Ordner sind überall ausgenommen
AUSGESCHLOSSEN = {"assets"}
# Dateinamen, die nie als Seite aufgenommen werden (Exporte, die jemand in den Ordner entpackt hat)
KEINE_SEITE = {"site", "liloport", "manifest", "comments", "moderation", "assets"}


def _ist_seite(datei: Path):
    """Liest eine mögliche Seiten-JSON; None, wenn sie keine Liloport-Seite ist."""
    if datei.stem in KEINE_SEITE:
        return None
    try:
        daten = json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if isinstance(daten, dict) and isinstance(daten.get("titel"), str) and isinstance(daten.get("bloecke", []), list):
        return daten
    return None


def bericht(store: Store) -> dict:
    """Beschreibt, was auf der Festplatte anders ist als in site.json – ohne etwas zu ändern."""
    site = store.site_laden()
    nach_ordner = {v["ordner"]: v for v in site["verzeichnisse"]}
    verzeichnisse_fehlen, seiten_fehlen, seiten_neu, ordner_neu = [], [], [], []
    for v in site["verzeichnisse"]:
        ordner = store.sicherer_pfad(v["ordner"])
        if not ordner.is_dir():
            verzeichnisse_fehlen.append({"id": v["id"], "name": v["name"], "ordner": v["ordner"],
                                         "seiten": len([s for s in v["seiten"] if not s.startswith("->")])})
            continue
        bekannt = {s for s in v["seiten"] if not s.startswith("->")}
        for slug in sorted(bekannt):
            if not (ordner / (slug + ".json")).is_file():
                seiten_fehlen.append({"verzeichnis": v["name"], "ordner": v["ordner"], "slug": slug})
        for datei in sorted(ordner.glob("*.json")):
            if datei.stem in bekannt:
                continue
            seite = _ist_seite(datei)
            if seite is not None:
                seiten_neu.append({"verzeichnis": v["name"], "ordner": v["ordner"], "slug": datei.stem,
                                   "titel": seite.get("titel") or datei.stem})

    def unbekannte(pfad: Path, rel: str):
        """Sucht Ordner, die als Verzeichnis fehlen; nur der oberste unbekannte Ordner wird gemeldet."""
        try:
            kinder = sorted(pfad.iterdir())
        except OSError:
            return
        for kind in kinder:
            if not kind.is_dir() or kind.name.startswith(("_", ".")):
                continue
            if not rel and kind.name in AUSGESCHLOSSEN:
                continue
            kind_rel = f"{rel}/{kind.name}" if rel else kind.name
            if kind_rel in nach_ordner:
                unbekannte(kind, kind_rel)
            else:
                anzahl = sum(1 for d in kind.rglob("*.json") if _ist_seite(d) is not None)
                ordner_neu.append({"ordner": kind_rel, "seiten": anzahl})
    unbekannte(store.root, "")
    return {"verzeichnisseFehlen": verzeichnisse_fehlen, "seitenFehlen": seiten_fehlen,
            "seitenNeu": seiten_neu, "ordnerNeu": ordner_neu,
            "anzahl": len(verzeichnisse_fehlen) + len(seiten_fehlen) + len(seiten_neu) + len(ordner_neu)}


def anwenden(store: Store, assets=None) -> dict:
    """Übernimmt alle Unterschiede aus bericht() in site.json; gibt eine Zusammenfassung zurück."""
    b = bericht(store)
    site = store.site_laden()

    # 1. Verzeichnisse entfernen, deren Ordner fehlt – samt registrierten Unterverzeichnissen
    weg_ids = {e["id"] for e in b["verzeichnisseFehlen"]}
    gewachsen = True
    while gewachsen:
        gewachsen = False
        for v in site["verzeichnisse"]:
            if v["id"] not in weg_ids and v.get("eltern") in weg_ids:
                weg_ids.add(v["id"])
                gewachsen = True
    weg_ordner = [v["ordner"] for v in site["verzeichnisse"] if v["id"] in weg_ids]
    site["verzeichnisse"] = [v for v in site["verzeichnisse"] if v["id"] not in weg_ids]
    nach_ordner = {v["ordner"]: v for v in site["verzeichnisse"]}

    # 2. Seiten austragen, deren Datei fehlt
    entfernte_pfade = set()
    for e in b["seitenFehlen"]:
        v = nach_ordner.get(e["ordner"])
        if v and e["slug"] in v["seiten"]:
            v["seiten"].remove(e["slug"])
            entfernte_pfade.add(f'{e["ordner"]}/{e["slug"]}')

    # 3. Weiterleitungen bereinigen, deren Ziel entfernt wurde
    def ziel_weg(pfad: str) -> bool:
        return pfad in entfernte_pfade or any(pfad == o or pfad.startswith(o + "/") for o in weg_ordner)
    for v in site["verzeichnisse"]:
        bleibt = []
        for s in v["seiten"]:
            if s.startswith("->") and ziel_weg(s[2:]):
                datei = store.sicherer_pfad(f'{v["ordner"]}/{s[2:].rsplit("/", 1)[-1]}.html')
                if datei.exists():
                    datei.unlink()
                continue
            bleibt.append(s)
        v["seiten"] = bleibt

    # 4. Neue Seiten in bekannten Verzeichnissen aufnehmen
    neue_seiten = 0
    for e in b["seitenNeu"]:
        v = nach_ordner.get(e["ordner"])
        if v and e["slug"] not in v["seiten"]:
            v["seiten"].append(e["slug"])
            _seite_normalisieren(store, f'{e["ordner"]}/{e["slug"]}')
            neue_seiten += 1

    # 5. Neue Ordner als Verzeichnisse aufnehmen (rekursiv, samt Seiten)
    neue_verzeichnisse = 0
    for e in b["ordnerNeu"]:
        zaehler = _ordner_aufnehmen(store, site, e["ordner"])
        neue_verzeichnisse += zaehler["verzeichnisse"]
        neue_seiten += zaehler["seiten"]

    store.site_speichern(site)

    # 6. Anhang-Referenzen auf entfernte Seiten bereinigen (die Dateien selbst bleiben; ohne
    #    Referenzen erscheinen sie im Dashboard unter «Nicht verwendete Dateien»)
    if assets is not None:
        gueltig = {pfad for _v, pfad, _s in store.alle_seiten(site)}
        registry = assets.laden()
        geaendert = False
        for eintrag in registry.values():
            uebrig = [r for r in eintrag.get("referenzen", []) if r in gueltig]
            if uebrig != eintrag.get("referenzen", []):
                eintrag["referenzen"] = uebrig
                geaendert = True
        if geaendert:
            assets.speichern(registry)

    return {"entfernteVerzeichnisse": len(weg_ids), "entfernteSeiten": len(b["seitenFehlen"]),
            "neueSeiten": neue_seiten, "neueVerzeichnisse": neue_verzeichnisse}


def _ordner_aufnehmen(store: Store, site: dict, rel: str) -> dict:
    """Nimmt einen unbekannten Ordner als Verzeichnis auf, mit allen Seiten und Unterordnern."""
    eltern_pfad = rel.rsplit("/", 1)[0] if "/" in rel else ""
    eltern = next((v for v in site["verzeichnisse"] if v["ordner"] == eltern_pfad), None) if eltern_pfad else None
    eltern_id = eltern["id"] if eltern else None
    geschwister = [v for v in site["verzeichnisse"] if (v.get("eltern") or None) == eltern_id]
    neu = {"id": store._neue_id(site), "name": rel.rsplit("/", 1)[-1], "ordner": rel, "inMenue": True,
           "reihenfolge": len(geschwister), "eltern": eltern_id, "seiten": []}
    site["verzeichnisse"].append(neu)
    zaehler = {"verzeichnisse": 1, "seiten": 0}
    ordner = store.sicherer_pfad(rel)
    for datei in sorted(ordner.glob("*.json")):
        if _ist_seite(datei) is None:
            continue
        neu["seiten"].append(datei.stem)
        _seite_normalisieren(store, f"{rel}/{datei.stem}")
        zaehler["seiten"] += 1
    for kind in sorted(ordner.iterdir()):
        if kind.is_dir() and not kind.name.startswith(("_", ".")):
            unter = _ordner_aufnehmen(store, site, f"{rel}/{kind.name}")
            zaehler["verzeichnisse"] += unter["verzeichnisse"]
            zaehler["seiten"] += unter["seiten"]
    return zaehler


def _seite_normalisieren(store: Store, pfad: str):
    """Gleicht den Slug in der Seiten-JSON an den Dateinamen an (wichtig fürs CSS-Scoping)."""
    try:
        seite = store.seite_laden(pfad)
    except StoreFehler:
        return
    slug = pfad.rsplit("/", 1)[-1]
    if seite.get("slug") != slug:
        seite["slug"] = slug
        store.seite_speichern(pfad, seite)
