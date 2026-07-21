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
#define MyAppVersion GetEnv("PSEUDOKRAT_VERSION")
#if MyAppVersion == ""
  #error PSEUDOKRAT_VERSION must be set by packaging\build_windows.ps1
#endif
#define MyAppPublisher "Pseudokrat"
#define MyAppURL "https://github.com/svensteiner/Pseudokrat"
#define MyAppExeName "Pseudokrat.exe"
#define MyAppGuiExeName "Pseudokrat-GUI.exe"

[Setup]
AppId={{A3B7F0D8-1E2C-4A7F-9C1B-5E4D3A2B1001}
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
PrivilegesRequiredOverridesAllowed=commandline

MinVersion=10.0.17763
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

OutputDir=..\dist\installer
OutputBaseFilename=PseudokratSetup-{#MyAppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppGuiExeName}

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
  Description: "Pseudokrat im Rechtsklick-Menü von TXT/CSV/DOCX/XLSX/PDF einrichten"; \
  GroupDescription: "Datei-Integration:"; Flags: unchecked

[Files]
Source: "..\dist\Pseudokrat\*"; DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppGuiExeName}"
Name: "{group}\{#MyAppName} Einrichtung"; Filename: "{app}\{#MyAppExeName}"; \
  Parameters: "setup"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppGuiExeName}"; \
  Tasks: desktopicon

[Run]
; Die Anwendung selbst registriert ausschließlich die unterstützten
; Dateitypen und verwendet dabei das tatsächlich angelegte Profil. So gibt
; es keine zweite, abweichende Registry-Implementierung im Installer.
Filename: "{app}\{#MyAppExeName}"; Parameters: "install --no-hotkeys"; \
  Tasks: associate; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppGuiExeName}"; \
  Description: "{cm:LaunchProgram,{#MyAppName}}"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "uninstall --yes"; \
  Flags: runhidden waituntilterminated; RunOnceId: "PseudokratRemoveIntegration"

[UninstallDelete]
; Modell-Cache und Profile bleiben standardmäßig erhalten — der Nutzer
; entscheidet selbst, ob er sie löscht. Das vermeidet versehentlichen
; Verlust von Mandanten-Mappings beim Update-Reinstall.
; Wer eine vollständige Entfernung will, löscht:
;   %LOCALAPPDATA%\Pseudokrat\
;   %APPDATA%\Pseudokrat\
