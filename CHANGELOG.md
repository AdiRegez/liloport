# Änderungen

Alle wesentlichen Änderungen an Liloport. Versionen vor 1.0 sind Beta: Liloport ist nutzbar, es können aber
noch Fehler vorkommen. Rückmeldungen bitte über [GitHub-Issues](https://github.com/AdiRegez/liloport/issues)
oder an kontakt@liloport.ch.

## 0.9.1 Beta

- DOI (Zenodo) in der Fusszeile jeder Liloport-Seite und in der Zitierangabe (CITATION.cff)

## 0.9.0 Beta – erste öffentliche Version

**Portfolio und Seiten**
- Dashboard mit den Reitern Portfolio, Kompetenzen und Verwaltung; Verzeichnisse A–Z oder nach Erstellung
  sortiert, ein- und ausklappbar
- Seiten mit Text, Bild, Video, PDF (mit Startseite), Datei, Button, Trenner, Spalten und Kompetenzen;
  im Profi-Niveau zusätzlich HTML-Blöcke und eigenes CSS
- Datum, Tags, interne Links mit «Verlinkt von», Fussnoten, Weiterleitungen beim Verschieben
- Volltextsuche über Titel, Texte und PDF-Inhalte, auch im Lesemodus per Doppelklick
- Automatisches Speichern, Rückgängig/Wiederherstellen, Verlauf mit früheren Fassungen, Papierkorb
- Beispiel-Portfolio zum Ausprobieren

**Weitergeben**
- Export einer Seite, eines Verzeichnisses oder des ganzen Portfolios als ZIP, wahlweise mit Passwortschutz
- Kommentare in der weitergegebenen Seite, ohne Installation; «Herunterladen» bringt sie zurück
- Abgabe mit Zeitstempel und Prüfsumme; Moderations-Link für eigene Server
- Import von Exporten und Vorlagen («Seite aus ZIP importieren»)

**Kompetenzen**
- Kompetenzrahmen erstellen oder als JSON importieren (Bereich › Kompetenz › Kompetenzstufe › Kompetenzpunkt)
- Kompetenz-Block auf Seiten mit Stand «noch nicht bearbeitet», «in Bearbeitung», «erarbeitet»
- Kompetenzabbildung mit vier Zuständen und Zahlen pro Ebene; Beurteilung in Abgaben

**Sicherheit und Daten**
- Alles bleibt auf dem eigenen Rechner; nichts wird ins Internet gesendet
- Tägliches Backup im Hintergrund: grosse Dateien nur einmal gespeichert, Prüfung des freien Speicherplatzes,
  Backup-Ordner wählbar (z. B. externe Festplatte)
- Grosse Portfolios (viele Gigabyte): Videos in Teilen ausgeliefert, Exporte ohne Arbeitsspeicher-Spitzen,
  PDFs in einem eigenen Prozess gelesen

**Installation**
- Installer für Windows (ohne Administratorrechte), macOS (Apple Silicon und Intel) und Linux,
  mit Startfenster und Desktop-Symbol; weiterhin startbar mit Python 3.10 oder neuer
