# PyInstaller-Bauplan für Liloport (Windows, macOS, Linux).
# Aufruf über packaging/bauen.py; direkt: pyinstaller --noconfirm packaging/liloport.spec
# Ergebnis: packaging/dist/Liloport/ (Windows: Liloport.exe, Linux: liloport) bzw. Liloport.app (macOS).
# Bewusst «onedir» statt einer einzelnen .exe: startet schneller und wird von Virenscannern seltener
# fälschlich gemeldet.
import json
import sys
from pathlib import Path

BASIS = Path(SPECPATH).resolve().parent          # Ordner mit server.py
ICONS = Path(SPECPATH).resolve() / "icons"
VERSION = json.loads((BASIS / "produkt.json").read_text(encoding="utf-8"))["version"]
WINDOWS, MAC = sys.platform.startswith("win"), sys.platform == "darwin"

datas = [
    (str(BASIS / "static"), "static"),
    (str(BASIS / "templates"), "templates"),
    (str(BASIS / "export-templates"), "export-templates"),
    (str(BASIS / "produkt.json"), "."),
    (str(BASIS / "LICENSE"), "."),
]

a = Analysis(
    [str(BASIS / "server.py")],
    pathex=[str(BASIS)],
    datas=datas,
    hiddenimports=["liloport.fenster", "tkinter", "tkinter.ttk", "tkinter.font", "tkinter.messagebox"],
    excludes=["pytest", "IPython", "numpy", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)

versionsdatei = None
if WINDOWS:
    # Versionsangaben in den Dateieigenschaften der .exe
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                      VarFileInfo, VarStruct, VSVersionInfo)
    nummern = tuple(int(x) for x in (VERSION.split(".") + ["0", "0", "0"])[:4])
    versionsdatei = VSVersionInfo(
        ffi=FixedFileInfo(filevers=nummern, prodvers=nummern),
        kids=[
            StringFileInfo([StringTable("040704B0", [
                StringStruct("CompanyName", "Adrian Regez"),
                StringStruct("FileDescription", "Liloport – Portfolio-Wiki für lebenslanges Lernen"),
                StringStruct("FileVersion", VERSION),
                StringStruct("InternalName", "Liloport"),
                StringStruct("LegalCopyright", "MIT-Lizenz"),
                StringStruct("OriginalFilename", "Liloport.exe"),
                StringStruct("ProductName", "Liloport"),
                StringStruct("ProductVersion", VERSION),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0407, 1200])]),
        ],
    )

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Liloport" if (WINDOWS or MAC) else "liloport",
    console=False,               # kein Konsolenfenster; Liloport zeigt ein eigenes kleines Fenster
    disable_windowed_traceback=False,
    upx=False,
    icon=str(ICONS / ("liloport.ico" if WINDOWS else "liloport.icns")) if (WINDOWS or MAC) else None,
    version=versionsdatei,
    argv_emulation=False,
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Liloport")

if MAC:
    app = BUNDLE(
        coll,
        name="Liloport.app",
        icon=str(ICONS / "liloport.icns"),
        bundle_identifier="ch.liloport.app",
        version=VERSION,
        info_plist={
            "CFBundleName": "Liloport",
            "CFBundleDisplayName": "Liloport",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSApplicationCategoryType": "public.app-category.education",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSHumanReadableCopyright": "Adrian Regez · MIT-Lizenz",
        },
    )
