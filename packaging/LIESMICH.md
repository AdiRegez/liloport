# Installer für Liloport

Aus dem Python-Programm werden mit [PyInstaller](https://pyinstaller.org) eigenständige Programme
gebaut. Wer sie installiert, braucht kein Python.

| System | Ergebnis | Desktop-Symbol |
|---|---|---|
| Windows 10/11 (x64, läuft auch auf ARM) | `Liloport-Windows-Setup.exe` (Inno Setup) | ja, plus Startmenü; Installation ohne Administratorrechte |
| macOS 11+ Apple Silicon | `Liloport-macOS-AppleSilicon.dmg` | Programme-Ordner, Launchpad, Dock |
| macOS 11+ Intel | `Liloport-macOS-Intel.dmg` | wie oben |
| Linux x86_64 (glibc 2.39+: Ubuntu 24.04+, Debian 13+, Fedora 40+; ältere Systeme: mit Python starten) | `Liloport-Linux-x86_64.tar.gz` | `installieren.sh`: Programm-Menü und Schreibtisch |

## Dateien

| Datei | Zweck |
|---|---|
| `bauen.py` | baut auf dem aktuellen System: Tests → PyInstaller → Installer bzw. DMG bzw. Archiv |
| `liloport.spec` | PyInstaller-Bauplan (welche Dateien mitkommen, Symbol, Versionsangaben) |
| `windows/liloport.iss` | Inno-Setup-Skript (UTF-8 mit BOM – beim Bearbeiten so speichern) |
| `macos/LIESMICH.txt` | liegt im DMG neben dem Programm |
| `linux/` | `installieren.sh`, `deinstallieren.sh`, `LIESMICH.txt` für das Archiv |
| `icons/` | Programmsymbol: `kachel.svg` (Windows/Linux) und `kachel-mac.svg` (macOS) als Vorlage, daraus `.ico`, `.icns`, `.png` |
| `anforderungen.txt` | PyInstaller-Version zum Bauen |

## Bauen

**Auf GitHub** (alle Systeme auf einmal): Actions → «Installer bauen» → «Run workflow». Die Ergebnisse
liegen unten in der Zusammenfassung des Laufs unter «Artifacts» (ZIP-Dateien zum Herunterladen, 90 Tage
aufbewahrt). Bei einem privaten Repository zählen die Minuten zum Kontingent des Kontos (macOS-Minuten
zählen zehnfach); bei einem öffentlichen Repository ist das kostenlos.

**Lokal** (nur für das System, auf dem man gerade ist):

```
python -m pip install -r packaging/anforderungen.txt
python packaging/bauen.py            # mit Tests; --ohne-tests überspringt sie
```

Windows braucht zusätzlich [Inno Setup 6](https://jrsoftware.org/isinfo.php); ohne entsteht nur eine ZIP
mit dem Programmordner. Das Python muss tkinter enthalten (bei python.org-Installern und unter macOS
dabei; unter Linux z. B. `sudo apt install python3-tk`), sonst hat das Programm kein Startfenster.

## Veröffentlichen

1. Version in `produkt.json` erhöhen (nur Zahlen und Punkte, z. B. `1.2.0`), committen und pushen.
2. GitHub → Releases → «Draft a new release» → «Choose a tag» → neues Tag `v1.2.0` → Titel und Text →
   «Publish release».
3. Der Workflow baut alles und hängt die vier Dateien nach 10–15 Minuten an das Release. Passt das Tag
   nicht zur Version in `produkt.json`, bricht er mit einer Meldung ab.

Feste Links für die Website (zeigen immer auf die neueste Version, sobald das Repository öffentlich ist):

```
https://github.com/AdiRegez/liloport/releases/latest/download/Liloport-Windows-Setup.exe
https://github.com/AdiRegez/liloport/releases/latest/download/Liloport-macOS-AppleSilicon.dmg
https://github.com/AdiRegez/liloport/releases/latest/download/Liloport-macOS-Intel.dmg
https://github.com/AdiRegez/liloport/releases/latest/download/Liloport-Linux-x86_64.tar.gz
```

## Signieren (offen)

Ohne Signatur warnen Windows (SmartScreen) und macOS (Gatekeeper) beim ersten Start; die Anleitung auf
der Website und im DMG erklärt, wie man trotzdem startet. Möglichkeiten für später:

- **Windows:** [SignPath Foundation](https://signpath.org) signiert Open-Source-Projekte kostenlos
  (Antrag nötig, Repository muss öffentlich sein). Alternativ ein eigenes Code-Signing-Zertifikat.
  Mit der Zeit und vielen Downloads verschwindet die SmartScreen-Warnung auch ohne Signatur seltener.
- **macOS:** Apple Developer Program (99 USD/Jahr), dann im Workflow signieren und notarisieren
  (`codesign` mit «Developer ID Application», `xcrun notarytool`). Erst dann entfällt die Warnung ganz.

Bis dahin signiert `bauen.py` das macOS-Programm «ad hoc» (nötig, damit es auf Apple Silicon überhaupt
startet).

## Programmsymbol ändern

`icons/kachel.svg` und `icons/kachel-mac.svg` anpassen, als 1024×1024-PNG exportieren und daraus mit
Pillow `liloport.ico` (16–256 px), `liloport.icns` sowie `liloport-48/256/512.png` und
`static/app-icon.png` (256 px, Fenstersymbol) erzeugen.
