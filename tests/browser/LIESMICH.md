# Browser-Tests (optional)

Klicken die Oberfläche in einem echten Browser durch. Brauchen Node.js und Playwright
(`npm install playwright && npx playwright install chromium`); die Python-Tests in `tests/` brauchen das nicht.

```
python server.py /tmp/liloport-test --port 8783 --kein-browser &
node tests/browser/dashboard.e2e.js http://127.0.0.1:8783   # jede Aktion im Dashboard
node tests/browser/export.e2e.js http://127.0.0.1:8783      # Export → Doppelklick → Kommentar → Herunterladen → Import
```

`export.e2e.js` braucht zusätzlich `php` (für den Webserver-Teil) und `unzip`. Beide Skripte erwarten einen leeren
Inhalte-Ordner.
node tests/browser/beurteilung.e2e.js http://127.0.0.1:8787  # Abgabe-Export → Beurteilung der Kompetenzen (PHP) → Import
node tests/browser/rundreise.e2e.js http://127.0.0.1:8787 1  # Doppelklick-Kopie → Kommentar + Beurteilung → Herunterladen → neu öffnen (1 = mit Passwort)
node tests/browser/neuerungen.e2e.js http://127.0.0.1:8787  # ⏻, Niveau-Schalter, Passwort-Hinweis, KR-Editor, vier Zustände, «Verlinkt von», PDF-Startseite/Suche, Spalten
node tests/browser/uebersicht.e2e.js http://127.0.0.1:8787  # Dashboard: A–Z, Einklappen, Reiter; kein falscher Konflikt bei «Fertig» während Autosave
