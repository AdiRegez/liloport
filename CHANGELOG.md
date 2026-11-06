# Änderungen

Alle wesentlichen Änderungen an Liloport. Versionen vor 1.0 sind Beta: Liloport ist nutzbar, es können aber
noch Fehler vorkommen. Rückmeldungen bitte über [GitHub-Issues](https://github.com/AdiRegez/liloport/issues)
oder an kontakt@liloport.ch.

## 0.12.0 Beta

**Fehlerbehebung**
- **Fett, kursiv und unterstrichen gehen beim Speichern nicht mehr verloren**: Der Editor liess den Browser
  diese Formate als `<span style="font-weight: bold">` schreiben, und der HTML-Filter entfernte sie beim
  Speichern. Jetzt entstehen echte `<strong>`, `<em>`, `<u>`; der Filter übernimmt zudem solche
  span-Formate (und `<font color>`) als Auszeichnung bzw. Farbe, statt sie zu verwerfen

**Editor (Profi)**
- **Schriftfarbe** mit Palette: zwölf Farben passend zum Seitendesign, dazu ein Feld für HEX-Codes
  (`#2a7f78`, `#c25`, auch `rgb(…)`), der bisherige RGB-Farbwähler des Systems und «Standardfarbe»
- **Textmarker**: Text farbig hinterlegen mit einer festen Palette (Gelb, Rosa, Pink, Lavendel, Eisblau,
  Mint, Pfirsich, Teal, Violett, Pflaume). Die Schriftfarbe wird automatisch angepasst – dunkle Schrift auf
  hellen, weisse Schrift auf dunklen Tönen –, so bleibt markierter Text auch im dunklen Modus lesbar;
  «Markierung entfernen» nimmt sie wieder weg
- **Tabellen ausgebaut**: «▦ Tabelle» fragt Zeilen, Spalten, Kopfzeile und Design ab. Steht der Cursor in
  einer Tabelle, erscheint die Tabellen-Leiste: Zeilen oben/unten und Spalten links/rechts einfügen oder
  löschen; Hintergrundfarbe (zwölf Töne, Schrift automatisch dunkel bzw. weiss) und Ausrichtung für Zelle,
  ganze Zeile oder ganze Spalte; Schalter für Kopfzeile, erste Spalte, Summenzeile, Beschriftung, volle
  Breite, kompakt und zentriert; sieben Designs mit Vorschau (Raster, Schlicht, Gestreift, Teal, Lavendel,
  Pastell, Luftig); Tabelle löschen. Tab/Shift+Tab springt von Zelle zu Zelle, Tab in der letzten Zelle hängt
  eine Zeile an. Breite Tabellen scrollen auf der Seite in ihrem Rahmen, statt über das Layout hinauszuragen
- **Gliederung**: macht die Hierarchie der Überschriften sichtbar – welcher Inhalt zu welcher H1, H2, H3, H4
  gehört. Wahl pro Seite in der Editor-Leiste («Gliederung: Standard / Leitlinien / Flächen / Nummeriert»):
  *Leitlinien* zeichnet je Ebene eine zarte, gepunktete Linie am rechten Rand, eng gestaffelt; die Strichstärke
  unterscheidet die Ebenen (H1 am kräftigsten); *Flächen* zeigt verschachtelte Karten mit Kopfstreifen in sehr
  zurückhaltenden Tönen, damit die Farben beim Lesen nicht stören; *Nummeriert* setzt Gliederungsnummern
  (1, 1.1, 1.1.1) vor die Überschriften. Ausser bei Flächen beginnen alle Überschriften links auf derselben
  Höhe. Ein Abschnitt umfasst alles bis zur nächsten Überschrift gleicher oder höherer Ordnung, auch Bilder
  und andere Blöcke dazwischen; Textblöcke mit mehreren Überschriften werden dafür aufgeteilt. Einklappbare
  Blöcke und Spalten bleiben als Ganzes erhalten. Funktioniert auch im Export, im Lesemodus und ohne
  JavaScript; der Import übernimmt die Wahl

**Editor (Amateur und Profi)**
- **Trenner-Vorlagen**: drei Knöpfe setzen alle Einstellungen eines Trenners auf einmal – «Grosse Punkte»
  (Standardfarbe, gepunktet, 8 px, Abstand oben/unten je 50 px), «Akzentlinie» (Teal, durchgezogen, 3 px,
  je 32 px) und «Dezent gestrichelt» (Standardfarbe, gestrichelt, 2 px, je 16 px); danach lässt sich alles
  weiter anpassen

**Seiten (Amateur und Profi)**
- **Übersichtliche Menüs für grosse Portfolios** (viele Verzeichnisse, tiefe Verschachtelung, lange Seitenlisten):
  - *Leiste oben*: die Hauptverzeichnisse in einer Zeile, was nicht passt, liegt unter «Mehr»; das aktuelle
    Verzeichnis bleibt sichtbar und ist markiert. Ein Klick öffnet ein Panel mit den Seiten in Spalten,
    Unterverzeichnissen zum Aufklappen (der Weg zur aktuellen Seite ist offen), Seitenzahlen und ab elf Seiten
    einem Suchfeld. Schliessen mit Escape oder Klick daneben
  - *Seitenmenü*: Suchfeld oben; nur der Weg zur aktuellen Seite ist aufgeklappt (selbst Auf- und Zugeklapptes
    bleibt gemerkt); Führungslinien für tiefe Ebenen; Seitenzahl je Verzeichnis; Listen ab 13 Seiten zeigen
    zuerst acht (plus die aktuelle) und «Alle … Seiten zeigen»; «⊟» klappt alles zu; die aktuelle Seite wird in
    die Leiste gescrollt
  - *Brotkrumen* über dem Titel zeigen, wo die Seite liegt; ein Klick öffnet das Menü an dieser Stelle
  - *Seitensuche* mit Strg/Cmd+K (oder «Seite suchen»): alle Seiten nach Titel, Verzeichnis und Tags, auch ohne
    Umlaute; ohne Eingabe die zuletzt bearbeiteten; Pfeiltasten und Enter
- **Neues Standarddesign für Überschriften**: Kapitel links bündig, Überschriften in der Farbe ihrer Ebene
  (H1 Teal, H2 Violett, H3 Pink, H4 Eisblau) – entspricht «Nummeriert» ohne Nummern und gilt für alle Seiten,
  auch im Amateur-Modus (dort ohne Wahl). Die frühere Linie unter H2 entfällt
- **Drucken**: Ein dezentes Drucker-Symbol links neben «Exportieren» bereitet die Seite für A4 auf – nur der
  Inhalt, helle Farben, Seitenzahlen, keine Menüs. Überschriften bleiben bei ihrem Text, Bilder, Tabellenzeilen,
  Zitate und Kästen werden nicht zerschnitten, die Kopfzeile von Tabellen wiederholt sich auf jeder Seite.
  Eingeklappte Bereiche werden ausgeklappt gedruckt. Für Video, Audio, PDF, ZIP-Dateien und eingebettete
  Inhalte steht ein kurzer Hinweis mit Dateinamen, dass die digitale Version hier mehr bereithält;
  Schaltflächen bleiben sichtbar, darunter steht klein, wohin sie führen. Gilt auch für Strg/Cmd+P und
  exportierte Seiten
- **Nach-unten-Knopf** neben dem Nach-oben-Knopf: erscheint, solange die Seite weiter nach unten reicht,
  und springt ans Ende (Fussnoten, «Verlinkt von», Kommentare)
- Unter dem Titel steht neben dem Datum neu **«zuletzt bearbeitet»** mit Datum und Uhrzeit der letzten
  Speicherung (im Export nur, wenn das Datum angezeigt wird)
- **Lange Links** (z. B. 400 Zeichen) brechen um, statt über das Layout hinauszuragen

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
