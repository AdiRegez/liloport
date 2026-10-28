"""Abgabestempel: Zeitpunkt und Prüfsumme eines Exports.

Die Prüfsumme (SHA-256) umfasst Titel, Datum, Tags, Blöcke und CSS aller exportierten Seiten sowie den
Inhalt jeder mitgelieferten Datei. Kommentare gehören nicht dazu – sie dürfen nach der Abgabe dazukommen.
Liloport prüft den Stempel beim Import erneut. Die Prüfsumme belegt, dass der Inhalt seit dem Export
unverändert ist; den Zeitpunkt belegt sie nur, wenn sie bei der Abgabe zusätzlich festgehalten wurde
(z. B. im Abgabeformular der Hochschule).
"""
import hashlib
import json

FELDER = ("titel", "datum", "tags", "css", "bloecke")


def sha256(daten) -> str:
    """SHA-256 von Bytes oder von einem Objekt mit .stuecke() (grosse Dateien stückweise, nie ganz im Speicher)."""
    if isinstance(daten, (bytes, bytearray)):
        return hashlib.sha256(daten).hexdigest()
    h = hashlib.sha256()
    for stueck in daten.stuecke():
        h.update(stueck)
    return h.hexdigest()


def pruefsumme(seiten: list, dateien: dict) -> str:
    """seiten: Liste von Seiten-Dicts (es zählen nur FELDER); dateien: {Pfad im Export: Bytes oder Quelle}."""
    inhalt = {
        "seiten": [{k: s.get(k) for k in FELDER} for s in seiten],
        "dateien": {name: sha256(daten) for name, daten in sorted(dateien.items())},
    }
    roh = json.dumps(inhalt, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(roh).hexdigest()


def text(zeit: str, summe: str, titel: str) -> str:
    """Inhalt von ABGABE.txt."""
    return (
        "Liloport – Abgabestempel\n\n"
        f"Titel:       {titel}\n"
        f"Exportiert:  {zeit}\n"
        f"Prüfsumme:   {summe}\n\n"
        "Die Prüfsumme (SHA-256) umfasst den Inhalt aller Seiten und Dateien dieses Exports, nicht die\n"
        "Kommentare. Liloport prüft sie beim Import («Seite aus ZIP importieren») und meldet, ob der Inhalt\n"
        "seit dem Export verändert wurde. Damit auch der Zeitpunkt belegt ist, die Prüfsumme bei der Abgabe\n"
        "zusätzlich angeben (z. B. im Abgabeformular oder in einer E-Mail an die Dozentin oder den Dozenten).\n"
    )
