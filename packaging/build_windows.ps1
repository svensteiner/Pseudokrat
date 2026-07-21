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

.PARAMETER SkipDependencyInstall
    Verwendet die bereits installierte Build-Umgebung. Für CI bzw. einen
    zuvor aus einem Lockfile vorbereiteten Build-Runner.

.PARAMETER SkipInstaller
    Baut und prüft nur den portablen PyInstaller-Ordner.

.EXAMPLE
    pwsh -File packaging\build_windows.ps1
    pwsh -File packaging\build_windows.ps1 -Sign
#>

[CmdletBinding()]
param(
    [string]$InnoSetupPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    [switch]$Sign,
    [switch]$SkipDependencyInstall,
    [switch]$SkipInstaller
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Remove-ReleaseDirectory {
    param([Parameter(Mandatory)][string]$RelativePath)

    $target = [IO.Path]::GetFullPath((Join-Path $RepoRoot $RelativePath))
    $rootPrefix = [IO.Path]::GetFullPath($RepoRoot).TrimEnd('\') + '\'
    if (-not $target.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsicherer Cleanup-Pfad außerhalb des Repos: $target"
    }
    if (Test-Path -LiteralPath $target) {
        Write-Host "    Cleanup: $RelativePath" -ForegroundColor DarkGray
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

$pythonInfo = python -c 'import platform, struct, sys; print(f"{sys.version_info.major}.{sys.version_info.minor}|{struct.calcsize(''P'') * 8}|{platform.python_implementation()}")'
if ($LASTEXITCODE -ne 0 -or -not $pythonInfo) {
    throw "Python konnte nicht gestartet werden."
}
$pythonParts = $pythonInfo.Trim().Split('|')
if ($pythonParts[0] -notin @('3.11', '3.12')) {
    throw "Release-Builds erfordern Python 3.11 oder 3.12; gefunden: $($pythonParts[0])."
}
if ($pythonParts[1] -ne '64' -or $pythonParts[2] -ne 'CPython') {
    throw "Release-Builds erfordern 64-Bit-CPython; gefunden: $pythonInfo."
}

$Version = python -c "import pathlib,tomllib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8'))['project']['version'])"
if ($LASTEXITCODE -ne 0 -or $Version -notmatch '^\d+\.\d+\.\d+(?:[A-Za-z0-9.+-]*)$') {
    throw "Ungültige oder nicht lesbare Projektversion: $Version"
}
$Version = $Version.Trim()

Write-Host "==> Pseudokrat-Windows-Build" -ForegroundColor Cyan
Write-Host "    Repo: $RepoRoot"

# 1. Cleanup — nur die von diesem Build besessenen Verzeichnisse.
Remove-ReleaseDirectory 'build'
Remove-ReleaseDirectory 'dist\Pseudokrat'
Remove-ReleaseDirectory 'dist\installer'

# 2. Bauwerkzeuge + Laufzeit-Abhaengigkeiten (inkl. Ordner-Schiene + OCR)
if (-not $SkipDependencyInstall) {
    Write-Host "==> Installiere Build- und Laufzeit-Abhaengigkeiten" -ForegroundColor Cyan
    python -m pip install --disable-pip-version-check "PyInstaller==6.18.0"
    if ($LASTEXITCODE -ne 0) {
        throw "Installation von PyInstaller fehlgeschlagen (Exit $LASTEXITCODE)."
    }
    python -m pip install --disable-pip-version-check -e ".[gui,simple-mode,clipboard,watcher,ocr]"
    if ($LASTEXITCODE -ne 0) {
        throw "Installation der Bundle-Abhängigkeiten fehlgeschlagen (Exit $LASTEXITCODE)."
    }
}
else {
    $pyInstallerVersion = python -c "import PyInstaller; print(PyInstaller.__version__)"
    if ($LASTEXITCODE -ne 0 -or $pyInstallerVersion.Trim() -ne '6.18.0') {
        throw "-SkipDependencyInstall erfordert PyInstaller 6.18.0."
    }
}

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
$reportedVersion = & $exePath --version
if ($LASTEXITCODE -ne 0) {
    throw "Smoke-Test der EXE fehlgeschlagen (Exit $LASTEXITCODE)."
}
if ($reportedVersion.Trim() -ne "pseudokrat $Version") {
    throw "EXE meldet unerwartete Version '$reportedVersion' (erwartet: pseudokrat $Version)."
}
& $exePath --help | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "CLI-Hilfe-Smoke-Test fehlgeschlagen (Exit $LASTEXITCODE)."
}

# Eigene PE-Dateien werden vor dem Verpacken signiert, damit der Installer
# nicht signierte Nutzlast ausliefert.
if ($Sign) {
    Write-Host "==> Code-Signing der Programmdateien" -ForegroundColor Cyan
    $programExecutables = @($exePath)
    if (Test-Path -LiteralPath $guiPath) {
        $programExecutables += $guiPath
    }
    & (Join-Path $PSScriptRoot 'sign_windows.ps1') -InstallerPath $programExecutables
    if ($LASTEXITCODE -ne 0) {
        throw "Code-Signing der Programmdateien fehlgeschlagen (Exit $LASTEXITCODE)."
    }
}

# 4. Inno Setup
if ($SkipInstaller) {
    Write-Host "==> Installer übersprungen (-SkipInstaller)." -ForegroundColor DarkYellow
    Write-Host ""
    Write-Host "Fertig. Portables Bundle:" -ForegroundColor Green
    Write-Host "    $(Join-Path $RepoRoot 'dist\Pseudokrat')" -ForegroundColor Green
    exit 0
}
if (-not (Test-Path -LiteralPath $InnoSetupPath -PathType Leaf)) {
    Write-Warning "Inno Setup nicht gefunden unter $InnoSetupPath."
    Write-Warning "Lade es von https://jrsoftware.org/isinfo.php herunter und"
    Write-Warning "rufe das Skript erneut mit -InnoSetupPath '<pfad>' auf."
    exit 1
}
Write-Host "==> Inno Setup" -ForegroundColor Cyan
$previousVersion = $env:PSEUDOKRAT_VERSION
try {
    $env:PSEUDOKRAT_VERSION = $Version
    & $InnoSetupPath packaging\installer.iss
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup fehlgeschlagen (Exit $LASTEXITCODE)."
    }
}
finally {
    $env:PSEUDOKRAT_VERSION = $previousVersion
}
$installer = Get-ChildItem -Path (Join-Path $RepoRoot 'dist\installer') -Filter 'PseudokratSetup-*.exe' |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $installer) {
    throw "Installer nicht gefunden in dist\installer\."
}
Write-Host "    OK: $($installer.FullName)" -ForegroundColor Green

# 5. Optional: Signing des äußeren Installers
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
