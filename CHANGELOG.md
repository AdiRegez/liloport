# Änderungen

Alle wesentlichen Änderungen an Liloport. Versionen vor 1.0 sind Beta: Liloport ist nutzbar, es können aber
noch Fehler vorkommen. Rückmeldungen bitte über [GitHub-Issues](https://github.com/AdiRegez/liloport/issues)
oder an kontakt@liloport.ch.

## 0.11.0 Beta

**Seiten**
- **Vollbild für Bilder**: Ein Klick auf ein Bild in der Galerie oder einem Bild-Block öffnet es in
  voller Grösse (dunkler Hintergrund, Bildtext darunter); in Galerien lässt sich mit ‹ › und den
  Pfeiltasten blättern, Schliessen mit ✕, Escape oder Klick daneben. Funktioniert auch auf
  exportierten Seiten und im Lesemodus

**Editor**
- **Automatisches Scrollen beim Ziehen**: Nähert sich ein gezogener Block dem oberen oder unteren
  Fensterrand, scrollt die Seite von selbst – Blöcke lassen sich so auch auf langen Seiten von ganz
  unten nach ganz oben ziehen
- **«+» zwischen den Blöcken**: Beim Überfahren eines Blocks erscheint unten ein «+», das direkt
  danach einen neuen Block einfügt; ein Einfügepunkt ganz oben legt neuen Inhalt zuoberst an –
  ohne Scrollen und Verschieben

**Dashboard**
- **Ordner-Abgleich**: Wer Ordner oder Seiten direkt im Dateimanager löscht, verschiebt oder
  hinzufügt, sieht im Dashboard ein Band «Der Inhalte-Ordner wurde ausserhalb von Liloport
  geändert». «Ansehen und abgleichen» zeigt die Unterschiede und übernimmt sie: verwaiste Einträge
  werden entfernt, neue Seiten und Ordner (samt Unterordnern) aufgenommen; Anhänge ohne Verwendung
  erscheinen unter «Nicht verwendete Dateien»
- Ein Verzeichnis, dessen Seiten-Dateien von Hand gelöscht wurden, lässt sich jetzt auch direkt in
  Liloport löschen (die verwaisten Einträge zählen nicht mehr als Inhalt)

## 0.10.0 Beta

**Seiten**
- Neuer Block **Audio**: MP3, WAV, OGG, M4A und FLAC auf Seiten einbinden – wie bei Videos ohne
  Grössenlimit, mit Spulen (HTTP-Range); der Dateiname steht in der Suche
- Neuer Block **Galerie** (Profi): mehrere Bilder im Masonry-Layout (2 bis 4 Spalten, Bilder in
  Originalproportion), je mit Bildtext; funktioniert auch im Export und im Lesemodus ohne JavaScript
- **Trenner** sind gestaltbar: Farbe, Dicke, Linienart (durchgezogen, gestrichelt, gepunktet, doppelt)
  sowie Abstand zum Block davor und danach
- **Nach-oben-Knopf**: erscheint beim Scrollen unten rechts und bringt einen auf langen Seiten schnell
  zurück zu «Bearbeiten» und «Exportieren»

**Dashboard**
- **Verzeichnisse verschieben**: ein Verzeichnis samt Unterverzeichnissen, Seiten, Anhängen, Verlauf und
  Kommentaren in ein anderes Verzeichnis oder auf die oberste Ebene bringen; interne Links ziehen mit
- **Menü-Anzeige der Seiten** (Verwaltung): Übersicht aller Seiten mit ihrer Menü-Art
  (Menübar ganz / Seitenmenü / kein Menü), direkt dort umschaltbar
- **Ganzes Portfolio exportieren** steht neu im Reiter «Verwaltung» (mit Hinweis, dass grosse Portfolios
  einige Minuten brauchen können) statt prominent im Dashboard-Kopf
- **Import**: «Neu › Aus ZIP importieren» legt Verzeichnis- und Portfolio-Exporte auf Wunsch als neues
  Verzeichnis auf oberster Ebene an (Unterverzeichnisse werden nachgebildet); auch ohne bestehende
  Verzeichnisse nutzbar

**Export und Allgemeines**
- **Export-Dialog neu gegliedert**: zuerst der Zweck – «Weitergeben als ZIP» (E-Mail, USB-Stick) oder
  «Auf einem Webserver veröffentlichen» –, danach die Gruppen Kommentare, Angaben und Abgabe/Schutz.
  Moderations-Link und Servername erscheinen nur noch beim Zweck Webserver; die Hinweise nach dem
  Download passen zum gewählten Zweck
- **Favicon** im Browser-Tab (Dashboard, Seiten, Kompetenzseiten, Impressum/Datenschutz und Exporte)
- Links in der Liloport-Fusszeile (GitHub, DOI, Lizenz, Impressum, Datenschutz) öffnen in einem neuen Tab

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
