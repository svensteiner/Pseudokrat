#requires -Version 5.1
<#
.SYNOPSIS
    Code-Signing für Pseudokrat-Windows-Builds.

.DESCRIPTION
    Signiert eine PE-Datei (EXE oder MSI/Installer) mit SHA-256 und einem
    RFC-3161-Timestamp. Verwendet das Windows-SDK-Tool ``signtool.exe``.

    Voraussetzungen:
      - Code-Signing-Zertifikat (PFX) — am besten EV (Extended Validation),
        damit Windows SmartScreen den Build OHNE Reputation-Aufbau akzeptiert.
        Standard-OV-Cert: Build muss erst über ~10.000 Downloads vorhanden
        sein, bevor SmartScreen vertraut.
      - signtool.exe im PATH oder unter
        "${env:ProgramFiles(x86)}\Windows Kits\10\bin\<sdk>\x64\signtool.exe".

    Geheimnisse werden NICHT als Skript-Parameter angenommen, sondern aus
    Umgebungsvariablen gelesen — damit landen sie nicht in Shell-Historien.

.PARAMETER InstallerPath
    Ein oder mehrere Pfade zu signierenden EXE/MSI-Dateien.

.PARAMETER TimestampUrl
    URL des Timestamp-Servers. Default: digicert (frei nutzbar).

.EXAMPLE
    $env:PSEUDOKRAT_SIGN_CERT_PATH = "C:\certs\codesign.pfx"
    $env:PSEUDOKRAT_SIGN_PASSWORD  = "<aus Tresor>"
    pwsh -File packaging\sign_windows.ps1 -InstallerPath dist\installer\PseudokratSetup-0.1.0.exe
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string[]]$InstallerPath,

    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = 'Stop'

foreach ($path in $InstallerPath) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Zu signierende Datei nicht gefunden: $path"
    }
}

$certPath = $env:PSEUDOKRAT_SIGN_CERT_PATH
$password = $env:PSEUDOKRAT_SIGN_PASSWORD
if (-not $certPath) {
    throw "Env PSEUDOKRAT_SIGN_CERT_PATH fehlt (Pfad zur PFX)."
}
if (-not $password) {
    throw "Env PSEUDOKRAT_SIGN_PASSWORD fehlt (PFX-Passwort)."
}
if (-not (Test-Path $certPath)) {
    throw "Zertifikat nicht gefunden: $certPath"
}

# signtool finden
$signtool = (Get-Command signtool.exe -ErrorAction SilentlyContinue)
if (-not $signtool) {
    $candidates = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Windows Kits\10\bin" `
        -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.Directory.FullName -match 'x64' } |
        Sort-Object FullName -Descending
    if ($candidates.Count -eq 0) {
        throw "signtool.exe nicht gefunden. Installiere das Windows 10 SDK von https://developer.microsoft.com/de-de/windows/downloads/windows-sdk/"
    }
    $signtool = $candidates[0]
}
Write-Host "    signtool: $($signtool.FullName)" -ForegroundColor DarkGray

foreach ($path in $InstallerPath) {
    $resolvedPath = (Resolve-Path -LiteralPath $path).Path
    Write-Host "==> Signiere $resolvedPath" -ForegroundColor Cyan

    # Signieren mit SHA-256 + Timestamp
    & $signtool.FullName sign `
        /fd SHA256 `
        /td SHA256 `
        /tr $TimestampUrl `
        /f $certPath `
        /p $password `
        /v $resolvedPath
    if ($LASTEXITCODE -ne 0) {
        throw "signtool sign fehlgeschlagen für $resolvedPath (Exit $LASTEXITCODE)."
    }

    # Verifizieren
    & $signtool.FullName verify /pa /v $resolvedPath
    if ($LASTEXITCODE -ne 0) {
        throw "signtool verify fehlgeschlagen für $resolvedPath (Exit $LASTEXITCODE)."
    }

    Write-Host "OK: Signatur gültig: $resolvedPath" -ForegroundColor Green
}
