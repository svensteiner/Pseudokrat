; Inno-Setup-Skript für den Pseudokrat-Windows-Installer.
;
; Voraussetzung:  packaging\pseudokrat.spec via PyInstaller gebaut →
;                 dist\Pseudokrat\ enthält den ungesignierten Build.
;
; Bauen:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\installer.iss
;
; Signiert wird der Installer-Output anschließend mit
; packaging\sign_windows.ps1 (siehe SIGNING.md).

#define MyAppName "Pseudokrat"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Pseudokrat"
#define MyAppURL "https://pseudokrat.example.com"
#define MyAppExeName "Pseudokrat.exe"

[Setup]
AppId={{A3B7F0D8-1E2C-4A7F-9C1B-PSEUDOKRAT0001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Privatuser-Variante: keine Admin-Rechte nötig (Profile liegen in %LOCALAPPDATA%).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

OutputDir=..\dist\installer
OutputBaseFilename=PseudokratSetup-{#MyAppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; Code-Signing aktivieren, sobald SignTool registriert ist
; (siehe packaging\sign_windows.ps1):
;   SignTool=signtool $f
;   SignedUninstaller=yes

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; \
  Description: "{cm:CreateDesktopIcon}"; \
  GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "associate"; \
  Description: "Pseudokrat im Rechtsklick-Menü von TXT/CSV/DOCX/XLSX/PDF anzeigen"; \
  GroupDescription: "Datei-Integration:"; Flags: unchecked

[Files]
Source: "..\dist\Pseudokrat\*"; DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
  Tasks: desktopicon

[Registry]
; Dateityp-Kontextmenü „Mit Pseudokrat anonymisieren"
Root: HKCU; Subkey: "Software\Classes\*\shell\Pseudokrat"; \
  ValueType: string; ValueName: ""; \
  ValueData: "Mit Pseudokrat anonymisieren"; Tasks: associate; \
  Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\*\shell\Pseudokrat\command"; \
  ValueType: string; ValueName: ""; \
  ValueData: """{app}\{#MyAppExeName}"" --file ""%1"""; Tasks: associate; \
  Flags: uninsdeletekey

[Run]
Filename: "{app}\{#MyAppExeName}"; \
  Description: "{cm:LaunchProgram,{#MyAppName}}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Modell-Cache und Profile bleiben standardmäßig erhalten — der Nutzer
; entscheidet selbst, ob er sie löscht. Das vermeidet versehentlichen
; Verlust von Mandanten-Mappings beim Update-Reinstall.
; Wer eine vollständige Entfernung will, löscht:
;   %LOCALAPPDATA%\Pseudokrat\
;   %APPDATA%\Pseudokrat\
