# Liloport

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23725695.svg)](https://doi.org/10.5281/zenodo.23725695)

Liloport («Lilo» für Lifelong Learning, «Port» für Portfolio) ist ein lokales Portfolio-Wiki für
Studierende: Seiten und Verzeichnisse liegen als normale HTML-Dateien und Ordner auf dem eigenen
Rechner, lassen sich per Doppelklick lesen und mit einem kleinen Python-Server bearbeiten.

> **Beta (Version 0.9).** Liloport ist vollständig nutzbar, aber noch jung: Es können Fehler vorkommen.
> Bitte regelmässig Backups machen (Dashboard › Verwaltung › Backup) und Fehler melden – über
> [GitHub-Issues](https://github.com/AdiRegez/liloport/issues) oder an kontakt@liloport.ch. Was sich von
> Version zu Version ändert, steht im [CHANGELOG](CHANGELOG.md).

*In English:* Liloport (Lifelong Learning Portfolio) is a local, offline portfolio wiki for students and
lifelong learners. Pages and folders are plain HTML files on your own computer that open with a double
click; a small built-in server lets you edit them in the browser. Pages can be shared as ZIP files that
others can read and comment on without installing anything, competences can be mapped to pages, and
everything stays on your machine. The user interface is in German. Installers for Windows, macOS and Linux
are on the [Releases page](https://github.com/AdiRegez/liloport/releases). License: MIT.

Funktionen: Dashboard, Verzeichnisse, Seiten mit Text, Bild, Video, PDF, ZIP-Datei, Button, Spalten, HTML
und Seiten-CSS; Amateur/Profi; Anhänge mit Löschlogik; Weiterleitungen; Export mit Passwortschutz und
Kommentaren; Abgabe mit Prüfsumme; Kompetenzrahmen und -abbildung; Profil; Volltextsuche inkl.
PDF-Inhalten; automatisches Speichern, Undo/Redo, Verlauf, Papierkorb, Backups.

**Zitieren:** Regez, A. Liloport – Lifelong-Learning-Portfolio [Software]. Zenodo. https://doi.org/10.5281/zenodo.23725695
(der DOI führt immer zur neuesten Version; «Cite this repository» rechts auf GitHub liefert weitere Formate).

## Zwei Designebenen

Alles, was zum Werkzeug gehört, ist pastellfarben (Lavendel, Rosa, Pink, Eisblau): die Liloport-Leiste
oben, das Dashboard, Dialoge und die Editor-Werkzeuge. Die eigenen Seiten sehen anders aus (warmes
Papier, Teal-Akzent, Titel in Bricolage Grotesque), damit klar ist: Hier bearbeitet man den eigenen Inhalt. Die
Liloport-Leiste lässt sich mit ▲ nach oben einklappen; ein kleiner Griff in der Mitte holt sie zurück.
Der Schalter Amateur/Profi sitzt in der Leiste der Seiten (nur dort ändert er etwas: welche Werkzeuge der
Editor anbietet); im Dashboard, bei Kompetenzrahmen und Abbildung erscheint er nicht. Seiten mit der Menü-Option
«Seitenmenü» bekommen eine Seitenleiste links mit auf- und zuklappbaren Verzeichnisgruppen und
markierter aktueller Seite; sie lässt sich mit ‹ einklappen und über «Menü» wieder öffnen.

## Installieren und starten

**Mit Installer (empfohlen, kein Python nötig).** Auf der Release-Seite des Projekts liegen:

| System | Datei | Installation |
|---|---|---|
| Windows 10/11 | `Liloport-Windows-Setup.exe` | Doppelklick, «Weiter», fertig. Ohne Administratorrechte; legt ein Desktop-Symbol und einen Startmenü-Eintrag an. |
| macOS (M1 und neuer) | `Liloport-macOS-AppleSilicon.dmg` | Öffnen, Liloport auf «Programme» ziehen. |
| macOS (Intel) | `Liloport-macOS-Intel.dmg` | wie oben |
| Linux (x86_64; Ubuntu 24.04+, Debian 13+, Fedora 40+) | `Liloport-Linux-x86_64.tar.gz` | Entpacken, `./installieren.sh` – Programm-Menü und Desktop-Symbol, ohne Administratorrechte. |

Noch sind die Programme nicht mit einem kostenpflichtigen Zertifikat signiert. Beim ersten Start warnt
darum das Betriebssystem einmal: Windows («Der Computer wurde durch Windows geschützt» → «Weitere
Informationen» → «Trotzdem ausführen»), macOS («Apple konnte nicht überprüfen …» → Systemeinstellungen →
Datenschutz & Sicherheit → «Dennoch öffnen»).

**Beim Start** erscheint ein kleines Fenster «Liloport», und das Dashboard öffnet sich im Browser. Das
Fenster offen lassen, solange man arbeitet; es öffnet bei Bedarf das Dashboard oder den Inhalte-Ordner
wieder. Beendet wird Liloport über «Beenden» im Fenster, durch Schliessen des Fensters oder mit ⏻ in der
Liloport-Leiste. Ein zweiter Klick auf das Desktop-Symbol öffnet nur das Dashboard. Ohne Konsole schreibt
das Programm seine Meldungen in `liloport.log` im Einstellungsordner (siehe unten).

**Mit Python (für Entwicklung oder ohne Installer).**

1. Python 3.10 oder neuer installieren (https://www.python.org), falls noch nicht vorhanden.
   Windows: die heruntergeladene ZIP vor dem Entpacken freigeben (Rechtsklick → Eigenschaften →
   «Zulassen» → OK), sonst blockiert Windows die Programmdateien (.js) beim Entpacken.
2. Im Ordner `liloport/` ausführen: `python server.py` (unter macOS/Linux ggf. `python3 server.py`);
   mit `--fenster` erscheint dasselbe Startfenster wie beim installierten Programm.
3. Der Browser öffnet das Dashboard unter `http://127.0.0.1:8000/`. Mit **Neu** ein erstes
   Verzeichnis und eine erste Seite anlegen. Das Dashboard zeigt, in welchem Ordner auf dem Rechner
   alles liegt, und öffnet ihn auf Wunsch im Dateimanager. Beenden mit Ctrl+C oder ⏻ in der Leiste.

Der Inhalte-Ordner wird beim ersten Start unter `~/Liloport` angelegt; ein anderer Ordner lässt
sich angeben: `python server.py /pfad/zum/ordner`. Der zuletzt verwendete Ordner steht in
`config.json` im Einstellungsordner des Benutzers (Windows `%APPDATA%\Liloport`, macOS
`~/Library/Application Support/Liloport`, Linux `~/.config/liloport`) – nicht im Programmordner, damit
auch ein installiertes Programm ihn schreiben darf. Läuft Liloport schon, öffnet ein zweiter Start nur
das Dashboard im Browser, statt einen zweiten Server zu starten (Port und Prozess stehen dafür in
`laufend.json` im Einstellungsordner). Deinstallieren entfernt nur das Programm; Inhalte und Einstellungen
bleiben.

Beim ersten Start bietet das Dashboard ein **Beispiel-Portfolio** an (Seiten, Bilder, Spalten, Tags,
Fussnoten, interne Links); es liegt in einem eigenen Verzeichnis und lässt sich wieder löschen.

## Datum, Tags, interne Links, Fussnoten

- Jede Seite hat ein **Datum** (vorbelegt mit dem Tag des Anlegens) und **Tags**; beides steht unter dem
  Titel. Ein Klick auf einen Tag zeigt im Dashboard alle Seiten mit diesem Tag; im Suchfeld sucht
  `#Tag` genau nach einem Tag, normale Suchwörter finden Tags ebenfalls.
- **Link** im Textblock öffnet eine Auswahl aller Seiten (mit Suche) oder nimmt eine Webadresse. Auch
  Buttons können auf eine Seite zeigen («Seite wählen»). Interne Links werden als `lp:pfad`
  gespeichert und bleiben gültig, wenn Verzeichnisse umbenannt werden; zeigt ein Link auf eine
  gelöschte Seite, erscheint er gepunktet als Text. Jede Seite listet unten, von wo sie verlinkt wird
  («Verlinkt von»); im Profi-Niveau lässt sich das pro Seite in der Editor-Leiste ausschalten.
- **PDF** öffnet auf Wunsch auf einer bestimmten Seite («Öffnen auf Seite»; Chrome, Edge, Firefox). Der Text
  des PDFs ist gleich nach dem Hochladen in der Suche (bis 2 Mio. Zeichen, ein 300-seitiges PDF braucht
  rund 0,3 s); gescannte PDFs ohne Textebene findet die Suche nur über den Dateinamen.
- **Fussnote** fügt an der Cursorposition eine Fussnote ein; auf der Seite erscheinen hochgestellte
  Zahlen und unten die nummerierte Liste mit Rücksprung.

## Mehrere Geräte

Liegt der Inhalte-Ordner in einem Cloud-Ordner (OneDrive, iCloud, SWITCHdrive …), warnen Dashboard und
Editor, wenn Liloport gleichzeitig auf einem anderen Gerät mit demselben Ordner läuft. Speichert der
Editor eine Seite, die inzwischen anderswo geändert wurde, fragt er nach: eigene Fassung speichern
(die andere bleibt im Verlauf) oder die andere laden.

## Zwei Modi

- **Lesemodus:** Jede HTML-Datei im Inhalte-Ordner funktioniert per Doppelklick, ohne laufenden
  Server. Ein Band oben zeigt «Lesemodus».
- **Editiermodus:** Mit laufendem `server.py` erscheinen auf jeder Seite unter dem Verzeichnismenü
  die Knöpfe **Bearbeiten** und **Exportieren**; das Dashboard bietet Anlegen, Bearbeiten und Löschen.

## Ordnerstruktur der Inhalte

```
Liloport/                     Inhalte-Ordner (gehört der Person, nicht dem Programm)
  site.json                   Verzeichnisbaum, Niveau, Einstellungen
  index.html                  Dashboard (generiert)
  _wiki/                      Tool-intern: style.css, reader.js, editor.js, app.js, menu.js, logo.svg,
                              assets.json (Registry der Anhänge), history/ (Versionen, Papierkorb),
                              backups/ (Backups, sofern kein eigener Backup-Ordner gewählt ist)
  assets/<slug>/              Anhänge, ein Unterordner pro Heimatseite
  semester-1/                 ein Verzeichnis = ein Ordner
    lernjournal.json          Quelle der Seite (JSON ist die Wahrheit)
    lernjournal.html          generierte Seite
    projekte/                 Unterverzeichnis
```

## Niveaus

Der Schalter **Amateur / Profi** in der Liloport-Leiste gilt global. Amateur bietet Text (H1 bis H3,
Fett/Kursiv/Unterstrichen, Listen, Zitat, Ausrichtung, Link), Bild (mit Breite und Ausrichtung), Video,
PDF, ZIP-Datei, Button mit Link, Trenner und Spalten (2 bis 4); Blöcke lassen sich per Drag und Drop
verschieben, auch in Spalten hinein, sowie einklappen und duplizieren. Profi schaltet rohe HTML-Blöcke,
Seiten-CSS (automatisch auf die Seite eingegrenzt), H4, Code, Farbe, Tabellen und freie Bildbreiten frei. Ein Wechsel verliert keine Daten: HTML-Blöcke bleiben im Amateur-Niveau
sichtbar, nur gesperrt. PDF- und ZIP-Blöcke öffnen per Klick den Ordner, in dem die Datei liegt.

## Anhänge

Eine Datei gehört zur Seite, auf der sie hochgeladen wurde (Heimat), kann aber von anderen Seiten
über «Vorhandene Datei» eingebettet werden. Beim Löschen einer Seite zeigt ein Dialog, welche
Anhänge mitgelöscht werden, welche bleiben (und zu welcher Seite sie wechseln) und welche
Weiterleitungen entfernt werden. Nicht mehr verwendete Dateien listet das Dashboard unten auf.

## Exportieren und weitergeben

«Exportieren» (auf der Seite oder im Dashboard, in beiden Niveaus gleich) erzeugt eine ZIP. Entpackt
enthält sie oben nur zwei Dinge:

```
export-lernjournal-2026-10-26/
  Seite öffnen.html     ← doppelklicken: öffnet die Seite im Browser, ohne Internet und Zusatzprogramm
  inhalt/               ← alles andere; dieser Ordner kommt bei Bedarf auf den Webserver
```

**Keine .js-Dateien in der ZIP:** Windows blockiert beim Entpacken einer heruntergeladenen ZIP alle
`.js`-Dateien («Windows-Sicherheitswarnung … Zugriff blockiert»), und manche Mailprogramme lehnen solche ZIPs
ganz ab. Die Skripte stehen darum direkt in jeder Seite. Trotzdem gilt: die ZIP zuerst entpacken
(Windows: Rechtsklick → «Alle extrahieren…»); wer im ZIP-Fenster doppelklickt, bekommt nur die eine Datei.
Die Seite zeigt dann selbst einen Hinweis zum Entpacken, die Kommentare bleiben als Text lesbar. Bei
Passwortschutz bleibt auch die mit «Herunterladen» erzeugte Kopie verschlüsselt.

Im Ordner `inhalt` liegen die Seite (ohne Liloport-Leiste und Menü), nur ihre eigenen Anhänge,
`style.css` mit den Schriften, `robots.txt`, `manifest.json`, `dateien.html` und eine `LIESMICH.txt`.
Weitergeben geht damit auch ohne Webserver: ZIP per E-Mail oder USB-Stick, die andere Person öffnet
«Seite öffnen», kommentiert und schickt über «Herunterladen» die ZIP mit ihren Kommentaren zurück. Im Dashboard lässt sich auch ein **Verzeichnis** (mit allen
Unterverzeichnissen) oder das **ganze Portfolio** exportieren: Dann gibt es eine Startseite mit
Inhaltsverzeichnis, jede Seite hat «‹ vorherige · nächste ›», und interne Links zwischen den
exportierten Seiten funktionieren (Links auf nicht exportierte Seiten werden zu Text). Der Dialog
erinnert daran, Personen und Fallbeispiele nur mit Einverständnis bzw. anonymisiert zu veröffentlichen.

**Als Abgabe kennzeichnen** setzt einen Abgabestempel: Zeitpunkt des Exports und eine Prüfsumme
(SHA-256 über Inhalt und Dateien, ohne Kommentare) stehen auf jeder Seite und in `ABGABE.txt`. Beim
Import prüft Liloport die Prüfsumme und zeigt, ob der Inhalt seit dem Export verändert wurde. Damit auch
der Zeitpunkt belegt ist, die Prüfsumme bei der Abgabe zusätzlich angeben. Der Dateiname ist 32 zufällige Zeichen; nur wer die Adresse
kennt, findet die Seite. Autor, Zeitstempel und Bild-Metadaten (EXIF) werden entfernt, sofern sie im
Dialog nicht eingeschaltet sind. Mit Passwortschutz wird der Inhalt mit AES-256-GCM verschlüsselt und
erst im Browser nach Eingabe des Passworts entschlüsselt – das funktioniert über `https://` oder lokal
per Doppelklick, nicht über `http://`.

## Kommentare und Herunterladen

Mit «Kommentare erlauben» im Export-Dialog können alle, die die Seite aufrufen, kommentieren
(Name freiwillig). Kommentare lassen sich formatieren – Überschriften, fett, kursiv, Listen, Zitate,
Code, Links – und über den Knopf «HTML» auch direkt als HTML schreiben; Skripte, Event-Handler,
iframes und unsichere Links werden dreifach herausgefiltert (beim Speichern durch `comments.php`
bzw. `comments.py`, beim Anzeigen durch den Kommentar-Editor in der Seite). Gespeichert werden nur Name, Text und Zeit. Die Seite
sucht sich selbst den passenden Weg, je nachdem, was der Webserver kann:

| Webserver kann … | Speicherort | Wer sieht die Kommentare |
| --- | --- | --- |
| PHP (übliches Webhosting) | `comments.php` → `comments.json` auf dem Server | alle Besucher |
| Python-CGI (viele Uni-Server) | `comments.py` → `comments.json` auf dem Server | alle Besucher |
| nur Dateien ausliefern (GitHub Pages u. ä.) | Browser der kommentierenden Person | nur sie selbst; sie gibt die Seite mit «Herunterladen» als ZIP weiter |

Wer kommentiert, kann den eigenen Kommentar im selben Browser **bearbeiten oder löschen** (der Server
gibt dafür einen Schlüssel aus, gespeichert wird nur dessen Hash). Die Autorin oder der Autor der Seite
**moderiert** mit dem Moderations-Link, den der Export-Dialog anzeigt (`…html#moderation=…`; Liloport
merkt ihn sich unter «Frühere Exporte»): Damit lassen sich alle Kommentare bearbeiten und löschen.
Der Link lässt sich im Export-Dialog abwählen. **Bei einer Abgabe ist er immer ausgeschaltet**:
Sonst könnte die abgebende Person Kommentare und Beurteilungen der Lehrperson ändern oder löschen.
Der Abgabestempel auf der Seite und `ABGABE.txt` vermerken das («Moderations-Link ausgeschaltet»),
`moderation.json` enthält keinen Hash, und die Seite nimmt keinen Moderationsschlüssel an. Grenze: Wer den
Webspace selbst verwaltet, kann `comments.json` dort weiterhin direkt bearbeiten. Als verlässlicher Beleg
dient darum die Kopie, die die Lehrperson nach der Beurteilung mit «Herunterladen» speichert.

Ein Server, der nur Dateien ausliefert, kann grundsätzlich nichts speichern – darum die dritte Stufe,
bei der die Seite das offen sagt. Jede exportierte Seite hat unten den Knopf **Herunterladen**: Er
packt den ganzen Ordner inklusive aller Kommentare (auch der nur im Browser gespeicherten) wieder als
ZIP im selben Aufbau. Das funktioniert auch in einer per Doppelklick geöffneten Kopie, weil alle
Dateien bis zu einer Gesamtgrösse von 60 MB zusätzlich in `dateien.html` liegen – ein Browser darf aus
einer lokalen Datei die Nachbardateien nicht lesen, sie aber in einem unsichtbaren Rahmen öffnen, der
ihren Inhalt an die Seite schickt. Grössere Dateien liegen in
der ZIP, fehlen aber in späteren Downloads aus einer lokalen Kopie (die Seite sagt das). Für `comments.py` muss
die Datei ausführbar und der Ordner beschreibbar sein; die ZIP setzt das Ausführungsrecht bereits.

## Sicherheit

- Der Server antwortet nur auf `127.0.0.1` bzw. `localhost` (Schutz gegen DNS-Rebinding) und nimmt
  schreibende Anfragen nur von Liloport selbst an, nie von anderen Websites (Origin/Sec-Fetch-Site-Prüfung).
- Importierte Seiten werden gefiltert: Skripte und Event-Handler in HTML-Blöcken werden entfernt.
- Hochgeladene SVGs werden mit einer Sandbox-CSP ausgeliefert; Seiten-CSS kann `<style>` nicht verlassen.
- Uploads haben kein Grössenlimit und werden stückweise auf die Platte geschrieben.
- Eigene Profi-HTML-Blöcke dürfen Skript enthalten. Darum keinen HTML-Code aus unbekannten Quellen einfügen.

## Zurück nach Liloport: Seite aus ZIP importieren

Dashboard → **Neu** → **Seite aus ZIP importieren**: Die Export-ZIP oder der heruntergeladene Ordner
(gezippt) wird gelesen, eine Vorschau zeigt Titel, Blöcke, Anhänge, Kommentare und – falls vorhanden –
ob der Abgabestempel noch stimmt; dann wählt man Verzeichnis und Titel. Verzeichnis- und Portfolio-
Exporte legen alle Seiten an und bilden die Unterverzeichnisse nach; interne Links bleiben erhalten.
So lassen sich auch Vorlagen weitergeben, etwa von Dozierenden oder der Hochschule. Die Seite wird neu angelegt, Anhänge werden übernommen, Kommentare erscheinen
unter der Seite. Grundlage ist die Datei `liloport.json` in jedem Export (Blöcke und Anhang-Zuordnung,
ohne Zeitstempel); passwortgeschützte Exporte enthalten sie nicht und lassen sich nicht importieren.

## Produkt-Fusszeile, Impressum, Datenschutz

Am unteren Rand jeder Seite und des Dashboards steht die Liloport-Fusszeile (Name, Version, GitHub, DOI,
Lizenz, Impressum, Datenschutz); auf exportierten Seiten eine schlanke Zeile «Erstellt mit Liloport».
Die Angaben stammen aus `produkt.json` im Programm-Ordner: dort Version, GitHub-Projekt, DOI und die
Angaben zum Impressum (verantwortliche Person, Adresse, Kontakt) eintragen – solange GitHub und DOI
leer sind, stehen gestrichelte Platzhalter. Impressum und Datenschutzerklärung werden aus
`templates/impressum.html` und `templates/datenschutz.html` erzeugt und liegen unter `_wiki/`.

## Suche

Das Suchfeld im Dashboard durchsucht Titel, Texte, Bildbeschriftungen, Button-Texte, Anhangnamen und
den Text von PDFs. Der PDF-Text wird ohne Zusatzpakete gelesen (`liloport/pdftext.py`: Objektströme,
FlateDecode/ASCII85, ToUnicode-CMaps für eingebettete Schriften); gescannte PDFs ohne Textebene
liefern nur den Dateinamen. Der Index liegt als `_wiki/suchindex.js` vor, die Suche funktioniert
deshalb auch im Lesemodus per Doppelklick. Neue PDFs liest ein Hintergrund-Thread, jedes PDF in einem eigenen
Prozess (pro PDF höchstens 60 Sekunden, danach wird der Prozess beendet; Ergebnis im Cache
`_wiki/pdftext.json`). Speichern und Start warten nie darauf, und auch ein ungewöhnlich aufgebautes PDF kann
Liloport nicht anhalten. Inhaltsströme werden in linearer Zeit zerlegt (`tests/test_pdftext.py`).

## Dashboard

Drei Reiter: **Portfolio** (Suche und Verzeichnisbaum), **Kompetenzen** (Rahmen anlegen, importieren,
Abbildung) und **Verwaltung** (Backup, Papierkorb, nicht verwendete Dateien, Profil). So bleibt die
Verwaltung auch bei sehr vielen Verzeichnissen erreichbar; ein veraltetes Backup zeigt ⚠ am Reiter.
Verzeichnisse und Seiten sind standardmässig **A–Z** sortiert (mit Umlauten und Zahlen in natürlicher
Reihenfolge: «Woche 2» vor «Woche 10»), umschaltbar auf «Erstellt». Jedes Verzeichnis lässt sich auf- und
zuklappen und zeigt eingeklappt, wie viele Seiten und Unterverzeichnisse es enthält; dazu «Alle
aufklappen/zuklappen». Ab 13 Verzeichnissen startet die Übersicht eingeklappt. Sortierung, Reiter und
Klappzustand merkt sich der Browser.

## Speichern, Verlauf, Backup

Der Editor speichert zwei Sekunden nach der letzten Änderung automatisch; Rückgängig und
Wiederherstellen gibt es für Blockänderungen (Ctrl+Z / Ctrl+Y ausserhalb des Textes, im Text
übernimmt der Browser). «Verlauf» zeigt die letzten 50 Fassungen (90 Tage) mit Vorschau und
Wiederherstellen. Gelöschte Seiten liegen 30 Tage im Papierkorb des Dashboards.

**Backup.** Rund 20 Sekunden nach dem ersten Start am Tag sichert Liloport den Inhalte-Ordner im
Hintergrund (Windows: mit niedriger Priorität); «Backup jetzt», Fortschritt und «Wiederherstellen» stehen im
Dashboard unter «Verwaltung». Auch Portfolios mit vielen Gigabyte Videos sind dafür ausgelegt:

- Jedes Backup ist ein vollständiger Stand (ZIP mit Seiten und Einstellungen), aber Dateien ab 32 KB
  (Bilder, Videos, PDFs) liegen nur einmal im gemeinsamen Dateispeicher `dateien/`, benannt nach ihrer
  SHA-256-Prüfsumme. Unveränderte Dateien werden nicht neu gelesen. Das erste Backup kopiert alles einmal,
  jedes weitere nur Neues; 10 Backups eines 50-GB-Portfolios belegen etwa 50 GB statt 500 GB.
- Vor jedem Backup prüft Liloport den freien Platz und lässt immer mindestens 1 GB bzw. 2 % des Laufwerks
  frei; reicht es nicht, gibt es kein Backup, aber eine Meldung im Dashboard (⚠ am Reiter «Verwaltung»).
  Wird das Laufwerk der Inhalte knapp, warnt das Dashboard ebenfalls.
- Der **Backup-Ordner** ist wählbar (Verwaltung › Backup › «Ändern …»), z. B. auf einer externen
  Festplatte; dann schützt das Backup auch vor einem Defekt des Laufwerks. Liloport legt dort einen eigenen
  Unterordner pro Inhalte-Ordner an (`Liloport-Backups/<Name>-<Kennung>`, erkennbar an
  `.liloport-backups.json`) und räumt nur darin auf. Ist die Festplatte nicht angeschlossen, meldet das
  Dashboard das. Eine Sperrdatei verhindert, dass zwei Liloport (z. B. zwei Geräte am selben Cloud-Ordner)
  gleichzeitig in denselben Backup-Ordner schreiben.
- Gespeicherte Dateien werden mit `fsync` geschrieben, beim nächsten Backup auf ihre Grösse geprüft und beim
  Wiederherstellen gegen ihre Prüfsumme; eine beschädigte Kopie wird gemeldet statt still zurückgegeben.
- Wiederherstellen entpackt in einen neuen, leeren Ordner (nie in den laufenden). Backups aus Testversionen vor 0.9
  (vollständige ZIPs) lassen sich weiterhin wiederherstellen.
- Bricht Liloport mitten im Backup ab, bleibt kein halbes Backup liegen.

**Grosse Dateien.** Videos werden in Teilen ausgeliefert (HTTP-Range: spulen, Safari), Uploads und Exporte
laufen stückweise über die Festplatte statt über den Arbeitsspeicher; ein Export des ganzen Portfolios
braucht darum auch bei vielen Gigabyte nur wenig Arbeitsspeicher (aber vorübergehend so viel freien Platz im
Temp-Ordner, wie die ZIP gross wird). Beim Neuschreiben der Seiten bleiben unveränderte Dateien unberührt.

Speichern zwei Vorgänge desselben Editors gleichzeitig (z. B. automatisches Speichern und «Fertig»),
wartet der zweite auf den ersten; der Server erkennt eigene frühere Speicherungen und meldet nur echte
Konflikte (zweites Gerät, Cloud-Synchronisation).

## Wenn etwas hängt

Das installierte Programm schreibt `liloport.log` in den Einstellungsordner (Windows `%APPDATA%\Liloport`,
macOS `~/Library/Application Support/Liloport`, Linux `~/.config/liloport`): Startzeitpunkt und -dauer,
Anfragen, die länger als 5 Sekunden dauern, und – wenn eine Anfrage länger als eine Minute hängt – einmal
den Zustand aller Threads, ausserdem den freien Speicherplatz beim Start. Diese Datei hilft bei der
Fehlersuche. Startet Liloport ungewöhnlich lange, sagt das Startfenster das nach etwa zwölf Sekunden.

Das Startfenster zeigt immer die Adresse des Dashboards (z. B. `http://127.0.0.1:8787/`) mit «Adresse
kopieren». Lässt sich der Standardbrowser nicht öffnen (z. B. weil er beschädigt oder deinstalliert ist),
versucht Liloport unter Windows Microsoft Edge und sagt sonst im Fenster, dass man die Adresse selbst in
einen Browser einfügen soll.

## Kompetenzen: Rahmen, Block, Abbildung

Im Dashboard unter **Kompetenzen** lässt sich ein **Kompetenzrahmen** erstellen oder als JSON importieren
(z. B. der Rahmen einer Hochschule, weitergegeben über «Als JSON weitergeben»). Ein Rahmen ist ein Baum
Bereich › Kompetenz › Kompetenzstufe › Kompetenzpunkt; seine Seite `_kompetenzen/<id>.html` zeigt ihn
und macht ihn mit laufendem Liloport bearbeitbar.

Auf jeder Seite gibt es in beiden Niveaus den Block **Kompetenzen**: Rahmen wählen, die Knoten ankreuzen,
an denen die Seite arbeitet, und pro Knoten den Stand setzen – **weiss** (noch nicht bearbeitet),
**orange** (in Bearbeitung), **grün** (erarbeitet). Der Stand lässt sich auch ohne Editor direkt auf der
fertigen Seite umschalten. Mehrere Seiten können denselben Knoten belegen; es zählt der höchste Stand.

Die **Kompetenzabbildung** `_kompetenzen/<id>-abbildung.html` zeigt jeden Knoten mit Farbe, wie viele
Seiten daran arbeiten und welche (mit Link). Sie unterscheidet vier Zustände: **erarbeitet** (grün),
**in Bearbeitung** (orange), **noch nicht bearbeitet** (grau: einer Seite zugeordnet, aber nicht begonnen)
und **offen** (gestrichelt: noch keiner Seite zugeordnet); auch «Zahlen pro Ebene» zählt sie getrennt.
Regeln: Ein oranger Punkt färbt alle Ebenen darüber orange; ist ein Unterpunkt nur zugeordnet, gilt die
Ebene darüber als «noch nicht bearbeitet» statt «offen».
Eine Stufe wird grün, sobald alle ihre Punkte grün sind; sind alle Stufen einer Kompetenz grün, ist sie
grün, und sind alle Kompetenzen eines Bereichs grün, der Bereich. Ein direkt gesetzter Stand gilt
zusätzlich zur Ableitung. Beispiel-Anwendung: Studierende schätzen sich anhand des importierten Rahmens
selbst ein; die Abbildung dient als Grundlage für Standortgespräche.

**Beurteilung:** Wird eine Seite mit Kompetenz-Block «als Abgabe» exportiert (mit Kommentaren), erscheint
auf der exportierten Seite unter den Kompetenzen der Abschnitt «Beurteilung der Kompetenzen»: dieselben
Knoten ohne Stand, je mit wählbarer Skala (0–1 bis 0–10), Wert und Kommentar. Beurteilungen werden wie
Kommentare gespeichert (`comments.json`, Feld `art: beurteilung`), lassen sich bearbeiten und löschen und
kommen mit «Herunterladen» und dem Import zurück nach Liloport, wo sie unter der Seite erscheinen.

## Profil, Verschieben, Weitergabe

Unter **Profil für Exporte** im Dashboard stehen Anzeigename und ID-Nummer (z. B. Matrikelnummer). Beide
werden im Export-Dialog vorbelegt; ob sie auf den exportierten Seiten erscheinen, entscheidet ein Schalter
je Export. **Verschieben** bringt eine Seite samt Datei, Anhängen, Verlauf, Kommentaren und internen Links
in ein anderes Verzeichnis (ersetzt die früheren Weiterleitungen).

## Sicherheit und Meldungen

Siehe `SECURITY.md`: Architektur, Netzwerkverhalten, Schutzmassnahmen, bekannte Grenzen und wie man
Sicherheitslücken vertraulich meldet.

## Tests

```
python -m unittest discover -s tests -v
```

## Installer bauen und veröffentlichen

Alles dazu liegt in `packaging/` (Anleitung: `packaging/LIESMICH.md`). Kurz:

- **Auf GitHub (empfohlen):** Actions → «Installer bauen» → «Run workflow». Nach etwa 10–15 Minuten
  liegen die Installer für Windows, macOS (Apple Silicon und Intel) und Linux als «Artifacts» beim Lauf.
- **Veröffentlichen:** Version in `produkt.json` setzen, committen, auf GitHub ein Release mit dem Tag
  `v` + Version erstellen (z. B. `v1.2.0`). Der Workflow hängt die Installer an das Release. Die
  Dateinamen enthalten keine Versionsnummer, darum zeigen Links wie
  `https://github.com/AdiRegez/liloport/releases/latest/download/Liloport-Windows-Setup.exe` immer auf
  die neueste Version.
- **Lokal:** `python -m pip install -r packaging/anforderungen.txt`, dann `python packaging/bauen.py`
  auf dem jeweiligen Betriebssystem (Windows zusätzlich mit Inno Setup 6).

`tests.yml` führt bei jedem Push die Tests unter Windows, macOS und Linux mit Python 3.10 und 3.13 aus.

## Lizenz

MIT, siehe `LICENSE`.
