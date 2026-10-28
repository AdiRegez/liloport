; Inno-Setup-Skript für den Windows-Installer von Liloport.
; Wird von packaging/bauen.py aufgerufen, das VERSION, QUELLE, AUSGABE, ICON und LIZENZ übergibt:
;   ISCC.exe /DVERSION=1.2.0 /DQUELLE=...\dist\Liloport /DAUSGABE=...\ausgabe ... liloport.iss
; Installiert ohne Administratorrechte für den aktuellen Benutzer (wichtig auf Schul- und Firmengeräten);
; mit Administratorrechten auf Wunsch für alle Benutzer. Inhalte (Ordner «Liloport» im Benutzerordner)
; werden weder installiert noch beim Deinstallieren gelöscht.

#ifndef VERSION
  #define VERSION "0.0.0"
#endif
#ifndef QUELLE
  #define QUELLE "..\dist\Liloport"
#endif
#ifndef AUSGABE
  #define AUSGABE "..\ausgabe"
#endif
#ifndef ICON
  #define ICON "..\icons\liloport.ico"
#endif
#ifndef LIZENZ
  #define LIZENZ "..\..\LICENSE"
#endif

[Setup]
; Die AppId nie ändern: Daran erkennt Windows frühere Installationen (Aktualisieren statt doppelt installieren).
AppId={{8B2F6C1E-4D7A-4E58-9A6B-3C1D2E5F7A90}
AppName=Liloport
AppVersion={#VERSION}
AppVerName=Liloport {#VERSION}
AppPublisher=Adrian Regez
AppPublisherURL=https://liloport.ch
AppSupportURL=https://github.com/AdiRegez/liloport
AppUpdatesURL=https://github.com/AdiRegez/liloport/releases
AppContact=kontakt@liloport.ch
AppComments=Portfolio-Wiki für lebenslanges Lernen
VersionInfoVersion={#VERSION}
VersionInfoDescription=Liloport Setup
DefaultDirName={autopf}\Liloport
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#AUSGABE}
OutputBaseFilename=Liloport-Windows-Setup
SetupIconFile={#ICON}
UninstallDisplayIcon={app}\Liloport.exe
UninstallDisplayName=Liloport
LicenseFile={#LIZENZ}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
; Läuft Liloport, bittet Setup bzw. die Deinstallation, es zuerst zu beenden (Mutex setzt das Programm)
AppMutex=LiloportLaeuft
CloseApplications=no
ShowLanguageDialog=no

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Messages]
de.FinishedLabel=Liloport ist installiert und lässt sich über das Desktop-Symbol oder das Startmenü starten.%n%nDeine Inhalte liegen im Ordner «Liloport» in deinem Benutzerordner. Beim Deinstallieren bleiben sie erhalten.

[Tasks]
Name: "desktopicon"; Description: "Symbol auf dem Desktop erstellen"; GroupDescription: "Zusätzliche Symbole:"

[InstallDelete]
; Reste einer früheren Version entfernen (das Programm liegt vollständig in diesen beiden Teilen)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#QUELLE}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Liloport"; Filename: "{app}\Liloport.exe"; Comment: "Portfolio-Wiki für lebenslanges Lernen"
Name: "{autodesktop}\Liloport"; Filename: "{app}\Liloport.exe"; Comment: "Portfolio-Wiki für lebenslanges Lernen"; Tasks: desktopicon

[Run]
Filename: "{app}\Liloport.exe"; Description: "Liloport jetzt starten"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Nur Programmdateien; Inhalte und Einstellungen (%APPDATA%\Liloport) bleiben
Type: dirifempty; Name: "{app}"
