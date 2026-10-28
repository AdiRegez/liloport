"""Beispiel-Portfolio: wird beim ersten Start angeboten und zeigt die wichtigsten Funktionen.

Alles liegt unter einem einzigen Verzeichnis «Beispiel-Portfolio»; wer es nicht mehr braucht, löscht
die Seiten und das Verzeichnis im Dashboard.
"""
import io
import struct
import zipfile
import zlib

from .store import Store


def beispiel_png(breite=320, hoehe=180) -> bytes:
    """Kleines Farbverlauf-PNG ohne externe Bibliothek."""
    zeilen = []
    for y in range(hoehe):
        zeile = bytearray(b"\x00")
        for x in range(breite):
            zeile += bytes((205 - x * 40 // breite, 180 + y * 40 // hoehe, 219 + x * 35 // breite))
        zeilen.append(bytes(zeile))

    def chunk(typ, daten):
        return struct.pack(">I", len(daten)) + typ + daten + struct.pack(">I", zlib.crc32(typ + daten) & 0xffffffff)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", breite, hoehe, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(zeilen))) + chunk(b"IEND", b""))


BEISPIEL_RAHMEN = {
    "titel": "Beispiel-Kompetenzrahmen", "quelle": "Liloport-Beispiel", "version": "1",
    "beschreibung": "Ein kleiner Rahmen, der zeigt, wie Seiten mit Kompetenzen verknüpft werden.",
    "bereiche": [
        {"id": "b1a2c3", "titel": "Reflektieren", "kompetenzen": [
            {"id": "k1a2c3", "titel": "Eigenes Lernen beobachten", "stufen": [
                {"id": "s1a2c3", "titel": "beschreibt", "beschreibung": "beschreibt, was gelernt wurde", "punkte": [
                    {"id": "p1a2c3", "titel": "hält Lernschritte im Journal fest"},
                    {"id": "p1b2c3", "titel": "benennt Schwierigkeiten"}]},
                {"id": "s1b2c3", "titel": "bewertet", "beschreibung": "beurteilt das eigene Vorgehen", "punkte": [
                    {"id": "p1c2c3", "titel": "vergleicht Ziel und Ergebnis"}]},
                {"id": "s1c2c3", "titel": "entwickelt weiter", "punkte": [
                    {"id": "p1d2c3", "titel": "leitet nächste Schritte ab"}]}]}]},
        {"id": "b2a2c3", "titel": "Gestalten", "kompetenzen": [
            {"id": "k2a2c3", "titel": "Inhalte strukturieren", "stufen": [
                {"id": "s2a2c3", "titel": "ordnet", "punkte": [{"id": "p2a2c3", "titel": "legt Verzeichnisse und Seiten sinnvoll an"}]},
                {"id": "s2b2c3", "titel": "verknüpft", "punkte": [{"id": "p2b2c3", "titel": "verlinkt Seiten untereinander"}]}]}]}
    ]}


def anlegen(store: Store, assets, kompetenzen=None) -> str:
    """Legt das Beispiel an und gibt den Pfad der Startseite zurück."""
    rahmen_id = kompetenzen.anlegen(dict(BEISPIEL_RAHMEN))["id"] if kompetenzen else None
    haupt = store.verzeichnis_anlegen("Beispiel-Portfolio")
    sem = store.verzeichnis_anlegen("Semester 1", eltern=haupt["id"])
    proj = store.verzeichnis_anlegen("Projekte", eltern=sem["id"])
    notizen = store.verzeichnis_anlegen("Private Notizen", eltern=haupt["id"], in_menue=False)

    start, _ = store.seite_anlegen("Willkommen", haupt["id"], "seitenmenue", [])
    lj, _ = store.seite_anlegen("Lernjournal", sem["id"], "seitenmenue", [])
    pa, _ = store.seite_anlegen("Projekt A", proj["id"], "seitenmenue", [])

    store.seite_aktualisieren(start, tags=["Einstieg"], bloecke=[
        {"id": "b1", "typ": "text", "html":
            "<h2>So funktioniert Liloport</h2>"
            "<p>Dieses Beispiel zeigt, was eine Portfolio-Seite kann. Oben rechts schaltest du zwischen "
            "<strong>Amateur</strong> und <strong>Profi</strong> um; mit <em>Bearbeiten</em> änderst du die Seite.</p>"
            "<ul><li>Verzeichnisse sind echte Ordner auf deinem Rechner.</li>"
            "<li>Jede Seite hat ein Datum und Tags. Ein Klick auf einen Tag sucht alle Seiten mit diesem Tag.</li>"
            "<li>Interne Links zeigen auf andere Seiten, zum Beispiel auf das "
            f'<a href="lp:{lj}">Lernjournal</a>. Die verlinkte Seite zeigt unten, von wo sie verlinkt wird.</li></ul>'
            "<p>Wenn du das Beispiel nicht mehr brauchst: im Dashboard die Seiten und dann das Verzeichnis "
            "«Beispiel-Portfolio» löschen.</p>"},
        {"id": "b2", "typ": "button", "text": "Zum Projekt A", "ziel": f"lp:{pa}", "stil": "voll", "ausrichtung": "links"},
    ])

    bild = assets.hochladen(lj, "farbverlauf.png", beispiel_png())
    seite = store.seite_aktualisieren(lj, tags=["Reflexion", "Woche 1"], bloecke=[
        {"id": "b1", "typ": "text", "html":
            "<h2>Woche 1</h2><p>Heute habe ich mein Portfolio angelegt. Wichtig war mir, dass alles auf meinem "
            'eigenen Rechner bleibt<span class="fussnote">Liloport speichert nichts in der Cloud, solange ich '
            "den Inhalte-Ordner nicht selbst dorthin lege.</span>.</p>"},
        {"id": "b2", "typ": "bild", "asset": bild["id"], "bildtext": "Ein Bild, hochgeladen auf dieser Seite",
         "breite": "halb", "ausrichtung": "mitte"},
        {"id": "b3", "typ": "text", "klapp": "zu", "klappTitel": "Woche 2 (zum Aufklappen)", "html":
            "<p>Blöcke lassen sich auf der Seite einklappen. Mein Projekt beschreibe ich unter "
            f'<a href="lp:{pa}">Projekt A</a>.</p>'},
    ] + ([{"id": "b4", "typ": "kr", "rahmen": rahmen_id, "knoten": {"p1a2c3": "gruen", "p1b2c3": "orange", "s1b2c3": "weiss"}}] if rahmen_id else []))
    assets.referenzen_setzen(lj, seite)

    zipdaten = io.BytesIO()
    with zipfile.ZipFile(zipdaten, "w") as z:
        z.writestr("material/hinweise.txt", "Beispielinhalt eines ZIP-Archivs.\n")
    archiv = assets.hochladen(pa, "material.zip", zipdaten.getvalue())
    seite = store.seite_aktualisieren(pa, tags=["Projekt"], css=".eigen { padding: 12px; border-left: 4px solid #cdb4db; }", bloecke=[
        {"id": "b1", "typ": "text", "html": "<p>Diese Seite liegt zwei Ordner tief und zeigt das Seitenmenü links.</p>"},
        {"id": "b2", "typ": "spalten", "spalten": [
            [{"id": "b3", "typ": "text", "html": "<h3>Linke Spalte</h3><p>Spalten gibt es in beiden Niveaus.</p>"},
             {"id": "b4", "typ": "bild", "asset": bild["id"], "bildtext": "Dasselbe Bild, hier nur eingebettet", "breite": "voll"}],
            [{"id": "b5", "typ": "html", "html": "<div class=\"eigen\"><p>Ein HTML-Block mit eigenem Seiten-CSS (Profi).</p></div>"},
             {"id": "b6", "typ": "button", "text": "Zurück zur Übersicht", "ziel": f"lp:{start}", "stil": "umrandet", "ausrichtung": "links"}],
        ]},
        {"id": "b7", "typ": "datei", "asset": archiv["id"]},
    ] + ([{"id": "b8", "typ": "kr", "rahmen": rahmen_id, "knoten": {"p2a2c3": "gruen", "p2b2c3": "gruen", "p1b2c3": "orange"}}] if rahmen_id else []))
    assets.referenzen_setzen(pa, seite)
    store.seite_anlegen("Gedanken", notizen["id"], "keine", [
        {"id": "b1", "typ": "text", "html": "<p>Dieses Verzeichnis ist <u>nicht</u> im Menü, die Seite hat "
                                             "<em>kein</em> Menü. Erreichbar über das Dashboard.</p>"},
    ])
    return start
