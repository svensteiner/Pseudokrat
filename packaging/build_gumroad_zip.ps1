#requires -Version 5.1
<#
.SYNOPSIS
    Schnuert das Gumroad-Verkaufspaket (portables ZIP) aus dem
    PyInstaller-Build.

.DESCRIPTION
    Erwartet einen fertigen PyInstaller-Build unter dist\Pseudokrat\
    (siehe build_windows.ps1 bzw. `python -m PyInstaller
    packaging\pseudokrat.spec`). Baut daraus:

        dist\gumroad\Pseudokrat-<version>-Windows.zip

    ZIP-Inhalt (so sieht es der Kaeufer nach dem Entpacken):

        Pseudokrat-<version>-Windows\
            START.bat               <- Doppelklick-Einstieg
            ANLEITUNG.txt           <- Kaeufer-Anleitung (nicht-technisch)
            Begriffe.example.txt    <- Vorlage fuer eigene Begriffe
            LIZENZ.txt              <- Lizenztext
            Pseudokrat\             <- EXE-Bundle (CLI + GUI + Laufzeit)

.EXAMPLE
    pwsh -File packaging\build_gumroad_zip.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BundleDir = Join-Path $RepoRoot 'dist\Pseudokrat'

if (-not (Test-Path (Join-Path $BundleDir 'Pseudokrat.exe'))) {
    throw ("PyInstaller-Build fehlt: $BundleDir\Pseudokrat.exe nicht gefunden. " +
        "Zuerst bauen: python -m PyInstaller packaging\pseudokrat.spec --noconfirm")
}

# Version aus pyproject.toml lesen.
$pyproject = Get-Content (Join-Path $RepoRoot 'pyproject.toml')
$versionLine = $pyproject | Where-Object { $_ -match '^version\s*=\s*"(.+)"' } | Select-Object -First 1
if (-not $versionLine) { throw 'Version nicht in pyproject.toml gefunden.' }
$Version = [regex]::Match($versionLine, '"(.+)"').Groups[1].Value

$PackageName = "Pseudokrat-$Version-Windows"
$OutDir = Join-Path $RepoRoot 'dist\gumroad'
$StageDir = Join-Path $OutDir $PackageName
$ZipPath = Join-Path $OutDir "$PackageName.zip"

Write-Host "==> Gumroad-Paket: $PackageName" -ForegroundColor Cyan

if (Test-Path $StageDir) { Remove-Item -Recurse -Force $StageDir }
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
New-Item -ItemType Directory -Force $StageDir | Out-Null

# 1. EXE-Bundle.
Write-Host '    Kopiere EXE-Bundle ...' -ForegroundColor DarkGray
Copy-Item -Recurse $BundleDir (Join-Path $StageDir 'Pseudokrat')

# 2. Kaeufer-Dateien.
Copy-Item (Join-Path $PSScriptRoot 'gumroad\START.bat') $StageDir
Copy-Item (Join-Path $PSScriptRoot 'gumroad\ANLEITUNG.txt') $StageDir
Copy-Item (Join-Path $RepoRoot 'Begriffe.example.txt') $StageDir
Copy-Item (Join-Path $RepoRoot 'LICENSE') (Join-Path $StageDir 'LIZENZ.txt')

# 3. ZIP.
Write-Host '    Erstelle ZIP ...' -ForegroundColor DarkGray
Compress-Archive -Path $StageDir -DestinationPath $ZipPath -CompressionLevel Optimal

$sizeMb = [math]::Round((Get-Item $ZipPath).Length / 1MB, 1)
Write-Host ''
Write-Host "Fertig: $ZipPath ($sizeMb MB)" -ForegroundColor Green
Write-Host 'Diese ZIP-Datei ist das Gumroad-Download-Artefakt.' -ForegroundColor Green
