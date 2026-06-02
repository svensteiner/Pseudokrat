#requires -Version 5.1
<#
.SYNOPSIS
    End-to-End-Build des Pseudokrat-Windows-Installers.

.DESCRIPTION
    1. Bereinigt frühere Build-Artefakte (dist, build).
    2. Installiert die zum Bauen benötigten Pakete (pyinstaller).
    3. Baut die Pseudokrat-GUI als PyInstaller-onedir-Bundle.
    4. Erstellt den Inno-Setup-Installer.
    5. Optional: Signiert das Resultat via packaging\sign_windows.ps1.

.PARAMETER InnoSetupPath
    Pfad zur ISCC.exe. Default: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe".

.PARAMETER Sign
    Wenn gesetzt, wird der Installer nach dem Build signiert. Setzt
    PSEUDOKRAT_SIGN_CERT_PATH und PSEUDOKRAT_SIGN_PASSWORD voraus.

.EXAMPLE
    pwsh -File packaging\build_windows.ps1
    pwsh -File packaging\build_windows.ps1 -Sign
#>

[CmdletBinding()]
param(
    [string]$InnoSetupPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    [switch]$Sign
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "==> Pseudokrat-Windows-Build" -ForegroundColor Cyan
Write-Host "    Repo: $RepoRoot"

# 1. Cleanup
foreach ($dir in @('build', 'dist')) {
    $path = Join-Path $RepoRoot $dir
    if (Test-Path $path) {
        Write-Host "    Cleanup: $dir/" -ForegroundColor DarkGray
        Remove-Item -Recurse -Force $path
    }
}

# 2. Bauwerkzeuge + Laufzeit-Abhaengigkeiten (inkl. Ordner-Schiene + OCR)
Write-Host "==> Installiere Abhaengigkeiten + pyinstaller (in aktuellem venv)" -ForegroundColor Cyan
python -m pip install --upgrade pip pyinstaller | Out-Null
python -m pip install -e ".[gui,simple-mode,clipboard,watcher,ocr]" | Out-Null

# 3. PyInstaller (baut Pseudokrat.exe = CLI/Ordner UND Pseudokrat-GUI.exe)
Write-Host "==> PyInstaller-Bundle" -ForegroundColor Cyan
python -m PyInstaller packaging\pseudokrat.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller-Build fehlgeschlagen (Exit $LASTEXITCODE)."
}
$exePath = Join-Path $RepoRoot 'dist\Pseudokrat\Pseudokrat.exe'
if (-not (Test-Path $exePath)) {
    throw "Erwartete EXE nicht gefunden: $exePath"
}
Write-Host "    OK: $exePath" -ForegroundColor Green
$guiPath = Join-Path $RepoRoot 'dist\Pseudokrat\Pseudokrat-GUI.exe'
if (Test-Path $guiPath) {
    Write-Host "    OK: $guiPath" -ForegroundColor Green
}
else {
    Write-Warning "GUI-EXE nicht gefunden ($guiPath) — nur die CLI wurde gebaut."
}
Write-Host "    Test: '$exePath' --version" -ForegroundColor DarkGray
& $exePath --version
if ($LASTEXITCODE -ne 0) {
    throw "Smoke-Test der EXE fehlgeschlagen (Exit $LASTEXITCODE)."
}

# 4. Inno Setup
if (-not (Test-Path $InnoSetupPath)) {
    Write-Warning "Inno Setup nicht gefunden unter $InnoSetupPath."
    Write-Warning "Lade es von https://jrsoftware.org/isinfo.php herunter und"
    Write-Warning "rufe das Skript erneut mit -InnoSetupPath '<pfad>' auf."
    exit 1
}
Write-Host "==> Inno Setup" -ForegroundColor Cyan
& $InnoSetupPath packaging\installer.iss
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup fehlgeschlagen (Exit $LASTEXITCODE)."
}
$installer = Get-ChildItem -Path (Join-Path $RepoRoot 'dist\installer') -Filter 'PseudokratSetup-*.exe' |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $installer) {
    throw "Installer nicht gefunden in dist\installer\."
}
Write-Host "    OK: $($installer.FullName)" -ForegroundColor Green

# 5. Optional: Signing
if ($Sign) {
    Write-Host "==> Code-Signing" -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot 'sign_windows.ps1') -InstallerPath $installer.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "Code-Signing fehlgeschlagen (Exit $LASTEXITCODE)."
    }
}
else {
    Write-Host "==> Signing übersprungen (ohne -Sign)." -ForegroundColor DarkYellow
    Write-Host "    Für die Produktion ist Code-Signing zwingend (siehe SIGNING.md)."
}

Write-Host ""
Write-Host "Fertig. Installer:" -ForegroundColor Green
Write-Host "    $($installer.FullName)" -ForegroundColor Green
