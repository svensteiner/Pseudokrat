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

$cliExe = Join-Path $BundleDir 'Pseudokrat.exe'
$guiExe = Join-Path $BundleDir 'Pseudokrat-GUI.exe'
if (-not (Test-Path -LiteralPath $cliExe -PathType Leaf)) {
    throw ("PyInstaller-Build fehlt: $BundleDir\Pseudokrat.exe nicht gefunden. " +
        "Zuerst bauen: python -m PyInstaller packaging\pseudokrat.spec --noconfirm")
}
if (-not (Test-Path -LiteralPath $guiExe -PathType Leaf)) {
    throw "Unvollständiger PyInstaller-Build: $guiExe fehlt."
}

# Version aus pyproject.toml lesen.
$Version = python -c "import pathlib,tomllib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8'))['project']['version'])"
if ($LASTEXITCODE -ne 0 -or $Version -notmatch '^\d+\.\d+\.\d+(?:[A-Za-z0-9.+-]*)$') {
    throw "Ungültige oder nicht lesbare Projektversion: $Version"
}
$Version = $Version.Trim()
$reportedVersion = & $cliExe --version
if ($LASTEXITCODE -ne 0 -or $reportedVersion.Trim() -ne "pseudokrat $Version") {
    throw "Bundle-Version '$reportedVersion' stimmt nicht mit pyproject.toml ($Version) überein."
}

$PackageName = "Pseudokrat-$Version-Windows"
$OutDir = Join-Path $RepoRoot 'dist\gumroad'
$StageDir = Join-Path $OutDir $PackageName
$ZipPath = Join-Path $OutDir "$PackageName.zip"
$HashPath = "$ZipPath.sha256"

Write-Host "==> Gumroad-Paket: $PackageName" -ForegroundColor Cyan

$outRoot = [IO.Path]::GetFullPath($OutDir).TrimEnd('\') + '\'
foreach ($ownedPath in @($StageDir, $ZipPath, $HashPath)) {
    $resolved = [IO.Path]::GetFullPath($ownedPath)
    if (-not $resolved.StartsWith($outRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsicherer Packaging-Pfad außerhalb von dist\gumroad: $resolved"
    }
}
if (Test-Path -LiteralPath $StageDir) { Remove-Item -LiteralPath $StageDir -Recurse -Force }
if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
if (Test-Path -LiteralPath $HashPath) { Remove-Item -LiteralPath $HashPath -Force }
New-Item -ItemType Directory -Force $StageDir | Out-Null

# 1. EXE-Bundle.
Write-Host '    Kopiere EXE-Bundle ...' -ForegroundColor DarkGray
Copy-Item -Recurse $BundleDir (Join-Path $StageDir 'Pseudokrat')

# 2. Kaeufer-Dateien.
Copy-Item (Join-Path $PSScriptRoot 'gumroad\START.bat') $StageDir
Copy-Item (Join-Path $PSScriptRoot 'gumroad\ANLEITUNG.txt') $StageDir
Copy-Item (Join-Path $RepoRoot 'Begriffe.example.txt') $StageDir
Copy-Item (Join-Path $RepoRoot 'LICENSE') (Join-Path $StageDir 'LIZENZ.txt')

# 3. Integritätsmanifest für Support/Forensik nach dem Entpacken.
$manifestPath = Join-Path $StageDir 'SHA256SUMS.txt'
$manifestLines = Get-ChildItem -LiteralPath $StageDir -File -Recurse |
    Sort-Object FullName |
    ForEach-Object {
        $relative = $_.FullName.Substring($StageDir.Length + 1).Replace('\', '/')
        $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $relative"
    }
[IO.File]::WriteAllLines($manifestPath, $manifestLines, [Text.UTF8Encoding]::new($false))

# 4. ZIP.
Write-Host '    Erstelle ZIP ...' -ForegroundColor DarkGray
Compress-Archive -Path $StageDir -DestinationPath $ZipPath -CompressionLevel Optimal

$sizeMb = [math]::Round((Get-Item $ZipPath).Length / 1MB, 1)
$zipHash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText($HashPath, "$zipHash  $([IO.Path]::GetFileName($ZipPath))`n", [Text.UTF8Encoding]::new($false))
Write-Host ''
Write-Host "Fertig: $ZipPath ($sizeMb MB)" -ForegroundColor Green
Write-Host "SHA-256: $zipHash" -ForegroundColor Green
Write-Host 'Diese ZIP-Datei ist das Gumroad-Download-Artefakt.' -ForegroundColor Green
