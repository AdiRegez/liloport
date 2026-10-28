#!/usr/bin/env python3
"""Baut das installierbare Liloport für das Betriebssystem, auf dem es läuft.

    python packaging/bauen.py              # Tests, dann bauen
    python packaging/bauen.py --ohne-tests

Braucht Python 3.10+ mit tkinter und PyInstaller (pip install -r packaging/anforderungen.txt).
Ergebnis in packaging/ausgabe/:
    Windows  Liloport-Windows-Setup.exe        (mit Inno Setup 6; ohne Inno Setup: Liloport-Windows.zip)
    macOS    Liloport-macOS-AppleSilicon.dmg   bzw. Liloport-macOS-Intel.dmg
    Linux    Liloport-Linux-x86_64.tar.gz      (mit installieren.sh)
Dasselbe Skript verwendet der GitHub-Workflow .github/workflows/release.yml.
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

PACKAGING = Path(__file__).resolve().parent
BASIS = PACKAGING.parent
DIST, BUILD, AUSGABE = PACKAGING / "dist", PACKAGING / "build", PACKAGING / "ausgabe"
ICONS = PACKAGING / "icons"


def schritt(text):
    print(f"\n=== {text}", flush=True)


def ausfuehren(befehl, **kw):
    print("  $ " + " ".join(str(b) for b in befehl), flush=True)
    subprocess.run([str(b) for b in befehl], check=True, **kw)


def version() -> str:
    v = json.loads((BASIS / "produkt.json").read_text(encoding="utf-8"))["version"]
    teile = v.split(".")
    if not (1 <= len(teile) <= 4 and all(t.isdigit() for t in teile)):
        sys.exit(f"Version «{v}» in produkt.json: bitte nur Zahlen mit Punkten (z. B. 1.2.0) – Windows verlangt das.")
    return v


def pruefen():
    if sys.version_info < (3, 10):
        sys.exit("Python 3.10 oder neuer nötig.")
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("WARNUNG: Dieses Python hat kein tkinter – das gebaute Programm hätte kein Startfenster.")
        if os.environ.get("LILOPORT_TK_PFLICHT"):
            sys.exit("Abbruch: tkinter fehlt (LILOPORT_TK_PFLICHT gesetzt).")
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.exit("PyInstaller fehlt: python -m pip install -r packaging/anforderungen.txt")


def tests():
    schritt("Tests")
    ausfuehren([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=BASIS)


def pyinstaller():
    schritt("PyInstaller")
    for ordner in (DIST, BUILD):
        shutil.rmtree(ordner, ignore_errors=True)
    ausfuehren([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
                "--distpath", DIST, "--workpath", BUILD, PACKAGING / "liloport.spec"], cwd=BASIS)


def iscc_finden():
    kandidaten = [shutil.which("iscc"), shutil.which("ISCC")]
    for umg in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        basis = os.environ.get(umg)
        if basis:
            kandidaten.append(str(Path(basis) / "Inno Setup 6" / "ISCC.exe"))
            kandidaten.append(str(Path(basis) / "Programs" / "Inno Setup 6" / "ISCC.exe"))
    return next((k for k in kandidaten if k and Path(k).exists()), None)


def windows(v):
    quelle = DIST / "Liloport"
    if not (quelle / "Liloport.exe").exists():
        sys.exit("Liloport.exe fehlt im Build.")
    iscc = iscc_finden()
    if not iscc:
        schritt("Inno Setup nicht gefunden – erstelle eine ZIP ohne Installer")
        ziel = AUSGABE / "Liloport-Windows.zip"
        with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as z:
            for d in sorted(quelle.rglob("*")):
                z.write(d, Path("Liloport") / d.relative_to(quelle))
        return ziel
    schritt("Inno Setup")
    ausfuehren([iscc, "/Qp", f"/DVERSION={v}", f"/DQUELLE={quelle}", f"/DAUSGABE={AUSGABE}",
                f"/DICON={ICONS / 'liloport.ico'}", f"/DLIZENZ={BASIS / 'LICENSE'}",
                PACKAGING / "windows" / "liloport.iss"])
    return AUSGABE / "Liloport-Windows-Setup.exe"


def macos(v):
    app = DIST / "Liloport.app"
    if not app.exists():
        sys.exit("Liloport.app fehlt im Build.")
    schritt("Signatur prüfen (ad hoc)")
    pruef = subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], capture_output=True, text=True)
    if pruef.returncode != 0:
        print(pruef.stderr)
        ausfuehren(["codesign", "--force", "--deep", "--sign", "-", app])
        ausfuehren(["codesign", "--verify", "--deep", "--strict", app])
    schritt("DMG")
    arch = "AppleSilicon" if platform.machine() == "arm64" else "Intel"
    stufe = BUILD / "dmg"
    shutil.rmtree(stufe, ignore_errors=True)
    stufe.mkdir(parents=True)
    ausfuehren(["ditto", app, stufe / "Liloport.app"])
    (stufe / "Programme").symlink_to("/Applications")
    shutil.copy(PACKAGING / "macos" / "LIESMICH.txt", stufe / "LIESMICH.txt")
    ziel = AUSGABE / f"Liloport-macOS-{arch}.dmg"
    # hdiutil scheitert auf GitHub-Rechnern gelegentlich mit «Resource busy»: dann kurz warten und wiederholen
    for versuch in range(1, 4):
        try:
            ausfuehren(["hdiutil", "create", "-volname", f"Liloport {v}", "-srcfolder", stufe, "-ov",
                        "-format", "UDZO", ziel])
            break
        except subprocess.CalledProcessError:
            if versuch == 3:
                raise
            import time
            time.sleep(10 * versuch)
    return ziel


def linux(v):
    quelle = DIST / "Liloport"
    if not (quelle / "liloport").exists():
        sys.exit("liloport fehlt im Build.")
    schritt("Linux-Archiv")
    arch = platform.machine() or "x86_64"
    ziel = AUSGABE / f"Liloport-Linux-{arch}.tar.gz"
    wurzel = "liloport"

    def info(name, modus):
        def f(t):
            t.name = f"{wurzel}/{name}" if name else wurzel
            t.uid = t.gid = 0
            t.uname = t.gname = ""
            if modus is not None and t.isfile():
                t.mode = modus
            return t
        return f

    with tarfile.open(ziel, "w:gz") as tar:
        tar.add(quelle, arcname=f"{wurzel}/app")
        for name in ("installieren.sh", "deinstallieren.sh"):
            tar.add(PACKAGING / "linux" / name, filter=info(name, 0o755))
        tar.add(PACKAGING / "linux" / "LIESMICH.txt", filter=info("LIESMICH.txt", 0o644))
        for g in (48, 256, 512):
            tar.add(ICONS / f"liloport-{g}.png", filter=info(f"icons/liloport-{g}.png", 0o644))
    return ziel


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ohne-tests", action="store_true")
    args = parser.parse_args()
    v = version()
    pruefen()
    print(f"Liloport {v} · {platform.system()} {platform.machine()} · Python {platform.python_version()}")
    if not args.ohne_tests:
        tests()
    pyinstaller()
    shutil.rmtree(AUSGABE, ignore_errors=True)
    AUSGABE.mkdir()
    if sys.platform.startswith("win"):
        ziel = windows(v)
    elif sys.platform == "darwin":
        ziel = macos(v)
    else:
        ziel = linux(v)
    schritt(f"Fertig: {ziel} ({ziel.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
