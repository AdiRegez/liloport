# Sicherheit von Liloport

## Sicherheitslücken melden

Bitte melde vermutete Sicherheitslücken **nicht** als öffentliches GitHub-Issue, sondern vertraulich:

- über «Security → Report a vulnerability» im GitHub-Repository (private Meldung), oder
- per E-Mail an **kontakt@liloport.ch** (Betreff «Sicherheit»).

Hilfreich sind: betroffene Version (steht in der Fusszeile, z. B. v0.9.2), Betriebssystem und Browser,
Schritte zum Nachvollziehen und – falls vorhanden – ein Beispiel (z. B. eine präparierte ZIP-Datei).
Wir bestätigen den Eingang innerhalb von 7 Tagen und melden uns mit einer Einschätzung. Bitte gib uns
bis zur Veröffentlichung einer Korrektur 90 Tage Zeit. Wer eine Lücke verantwortungsvoll meldet, wird –
wenn gewünscht – in den Versionshinweisen genannt.

## Unterstützte Versionen

Sicherheitskorrekturen gibt es für die jeweils neueste veröffentlichte Version.

| Version | Unterstützt |
| --- | --- |
| neueste 0.x | ja |
| ältere | nein – bitte aktualisieren |

## Überblick für Technikverantwortliche

**Architektur.** Liloport ist ein lokales Programm in Python (nur Standardbibliothek, keine
Fremdpakete) mit einer Oberfläche im Browser (HTML/CSS/JavaScript ohne Frameworks, ohne CDN). Die
Inhalte liegen als JSON-, HTML- und Mediendateien in einem Ordner der Person (Standard `~/Liloport`).

**Netzwerkverhalten.**

- Der Editierserver lauscht nur auf `127.0.0.1` (Standardport 8000), nie auf einer Netzwerkschnittstelle.
- Liloport baut von sich aus keine Verbindungen ins Internet auf: kein Tracking, keine Telemetrie,
  keine Updates im Hintergrund, keine Schriften oder Skripte von fremden Servern.
- Einzige ausgehende Verbindung: die optionale Funktion «Kommentare von einer Adresse importieren», die
  eine von der Person eingegebene URL abruft.

**Schutz der lokalen API.**

- Host-Prüfung gegen DNS-Rebinding: beantwortet werden nur Anfragen an `127.0.0.1:<port>` bzw. `localhost:<port>`.
- Schreibende Anfragen (POST/PUT/DELETE) von fremden Websites werden über `Origin` und
  `Sec-Fetch-Site` abgewiesen (Schutz gegen CSRF).
- Antwort-Header: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
  `Content-Security-Policy: frame-ancestors 'self'` (gegen Clickjacking).
- Alle Dateipfade werden auf den Inhalte-Ordner begrenzt (kein Verzeichnis-Ausbruch).

**Umgang mit Inhalten.**

- Textblöcke und Kommentare laufen durch einen Whitelist-HTML-Filter (Tags, Attribute, Link-Schemata, CSS-Eigenschaften).
- HTML-Blöcke im Niveau «Profi» werden bewusst ungefiltert übernommen. Sie stammen von der Person selbst;
  die Oberfläche weist darauf hin, keinen HTML-Code aus unbekannten Quellen einzufügen.
- Importierte Seiten (ZIP von anderen Personen) werden vollständig gefiltert: Skripte und Event-Handler in
  HTML-Blöcken werden entfernt, Seiten-CSS kann `<style>` nicht verlassen, unbekannte Blocktypen fallen weg.
- Hochgeladene Dateien werden am Inhalt erkannt, nicht an der Endung (Bilder, Video, PDF, ZIP). SVGs werden
  mit einer Sandbox-CSP ausgeliefert, damit darin enthaltenes Skript nicht läuft.

**Export auf einen Webserver.**

- Exportierte Seiten haben zufällige, 32 Zeichen lange Dateinamen, `noindex`, `robots.txt` und `no-referrer`.
- Metadaten (EXIF, XMP, Autor, Zeitstempel) werden aus Bildern und der ZIP entfernt, sofern nicht ausdrücklich gewünscht.
- Optionaler Passwortschutz: AES-256-GCM, Schlüssel über PBKDF2-SHA-256 mit 310 000 Runden; entschlüsselt
  wird erst im Browser (Web Crypto, braucht `https://`). Ein vergessenes Passwort lässt sich nicht wiederherstellen.
- Kommentare (`comments.php` oder `comments.py`): Whitelist-Filter beim Speichern und beim Anzeigen,
  Längenlimit, Honeypot-Feld, Frequenzbremse über einen täglich wechselnden Hash der IP-Adresse (die
  IP-Adresse selbst wird nicht gespeichert). Bearbeiten und Löschen nur mit dem Schlüssel, den die
  kommentierende Person beim Speichern erhält, oder mit dem Moderationsschlüssel der Autorin bzw. des
  Autors. Auf dem Server liegen nur SHA-256-Hashes dieser Schlüssel.

**Bekannte Grenzen.**

- Die Inhalte liegen unverschlüsselt auf der Festplatte. Empfehlung: Festplattenverschlüsselung des
  Betriebssystems (BitLocker, FileVault, LUKS).
- Backups liegen standardmässig im Inhalte-Ordner. Für Schutz vor Datenverlust zusätzlich extern sichern.
- Wer den Link zu einer exportierten Seite kennt, kann sie lesen und – falls eingeschaltet – kommentieren.
  Für vertrauliche Inhalte den Passwortschutz verwenden.
- Der Abgabestempel weist nach, dass ein Export seit seiner Erstellung unverändert ist. Den Zeitpunkt
  belegt er nur, wenn die Prüfsumme bei der Abgabe zusätzlich festgehalten wird.

**Prüfung.** Die automatischen Tests (`python -m unittest discover -s tests`) decken unter anderem den
HTML-Filter, die Host- und Origin-Prüfung, den Import präparierter ZIP-Dateien, die Verschlüsselung (gegen
NIST-Testvektoren) und das Entfernen von Metadaten ab.
