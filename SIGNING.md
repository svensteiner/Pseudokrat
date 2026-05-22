# Code-Signing — Pseudokrat

Diese Datei dokumentiert, wie aus dem ungesignierten Build-Output (siehe
[packaging/INSTALLER.md](packaging/INSTALLER.md)) ein **signierter,
verteilbarer** Pseudokrat-Build wird.

> **Status:** Scripts vorbereitet (`packaging/sign_windows.ps1`,
> `packaging/sign_macos.sh`). Zertifikate selbst sind NICHT im Repo —
> sie müssen vor jedem Release-Build über die unten dokumentierten
> Kanäle bezogen werden.

---

## Warum Code-Signing zwingend ist

Ein **unsigniertes** Pseudokrat-Installer-EXE wird unter Windows von
SmartScreen blockiert; auf macOS verweigert Gatekeeper das Starten der
.app. Ein Steuerberater, dem wir einen ungesignierten Build geben,
sieht beim Doppelklick: „Die App ist möglicherweise schädlich" — und
verwirft sie. Damit ist die ganze Vertrauensgrundlage (lokal-only, kein
Phone-Home, datenschutzfreundlich) faktisch nicht mehr kommunizierbar,
weil der OS-Eindruck genau das Gegenteil suggeriert.

---

## Windows

### Zertifikat-Beschaffung

| Variante | Empfohlen für | Preis (2026, Richtwert) | SmartScreen-Reputation |
|---|---|---|---|
| **OV (Organization Validation)** | Bootstrap, kleines Volumen | ~ 250 €/Jahr | Aufbau ab ~10.000 Downloads |
| **EV (Extended Validation)**     | Produktiv-Distribution    | ~ 400-800 €/Jahr + HSM-Token | Sofort vertrauenswürdig |

Anbieter (alphabetisch): DigiCert, GlobalSign, Sectigo, SSL.com.

Für EV-Cert: physisches HSM (USB-Token) wird per Post zugeschickt. Damit
das im CI-Build (siehe „GitHub Actions") funktioniert, brauchst du einen
**Code-Signing-Cloud-Service** (z. B. DigiCert KeyLocker, ssl.com
eSigner) oder eine eigene HSM-Maschine im Build-Netz.

### Anwendung

```powershell
$env:PSEUDOKRAT_SIGN_CERT_PATH = "C:\certs\pseudokrat-codesign.pfx"
$env:PSEUDOKRAT_SIGN_PASSWORD  = "<aus Tresor>"
pwsh -File packaging\sign_windows.ps1 -InstallerPath dist\installer\PseudokratSetup-0.1.0.exe
```

Das Skript signiert die EXE mit SHA-256 + RFC-3161-Timestamp und
verifiziert die Signatur (`signtool verify /pa`). Schlägt einer der
Schritte fehl, bricht das Skript mit Non-Zero-Exit ab.

### Inno-Setup signiert sowohl Inhalt als Installer

Wenn `installer.iss` mit ``SignTool=signtool $f`` versehen ist (im
Skript auskommentiert; Aktivierung beim Release), signiert Inno-Setup
die enthaltene `Pseudokrat.exe` UND den finalen Installer-EXE in einem
Pass. Anleitung: [Inno-Setup signing docs](https://jrsoftware.org/ishelp/index.php?topic=setup_signtool).

---

## macOS

### Zertifikat-Beschaffung

1. Apple Developer Program Mitgliedschaft (€ 99/Jahr).
2. In Xcode → Settings → Accounts → Manage Certificates → „Developer ID
   Application" erstellen.
3. Falls ein DMG/PKG signiert werden soll: zusätzlich „Developer ID
   Installer" erstellen.
4. Privater Schlüssel landet im macOS-Schlüsselbund — exportieren als
   `.p12` für CI.

### Notarization

Apple verlangt seit macOS 10.15, dass jede aus dem Internet bezogene
App **notarisiert** ist (Apple bekommt einen Build-Hash, scannt
automatisiert auf bekannte Malware, gibt OK zurück). Ohne Notarization
zeigt Gatekeeper: „Pseudokrat lässt sich nicht öffnen, weil der
Entwickler nicht überprüft werden kann".

```bash
export PSEUDOKRAT_APPLE_IDENTITY="Developer ID Application: Beispiel GmbH (ABCD123456)"
export PSEUDOKRAT_APPLE_ID="release@pseudokrat.example.com"
export PSEUDOKRAT_APPLE_PASSWORD="$(security find-generic-password -s NOTARIZE -w)"
export PSEUDOKRAT_APPLE_TEAM_ID="ABCD123456"
NOTARIZE=1 ./packaging/sign_macos.sh dist/Pseudokrat.app
```

App-spezifisches Passwort gibts unter https://appleid.apple.com/account/manage.

---

## CI: GitHub Actions

Empfohlene Secrets im Repository (Settings → Secrets and variables →
Actions):

| Secret | Typ | Beschreibung |
|---|---|---|
| `WIN_CODESIGN_PFX_B64`     | Base64-PFX | `base64 codesign.pfx > codesign.pfx.b64` |
| `WIN_CODESIGN_PASSWORD`    | String     | PFX-Passwort |
| `MAC_DEVELOPER_ID`         | String     | „Developer ID Application: ..." |
| `MAC_APPLE_ID`             | String     | Apple ID für Notarization |
| `MAC_APPLE_PASSWORD`       | String     | App-spezifisches Passwort |
| `MAC_TEAM_ID`              | String     | 10-stellige Apple Team ID |
| `MAC_CERT_P12_B64`         | Base64-P12 | Developer-ID-Cert als .p12 (für Import in Runner-Keychain) |
| `MAC_CERT_PASSWORD`        | String     | Passwort des P12 |

Im Workflow:

```yaml
- name: Decode Windows cert
  if: runner.os == 'Windows'
  run: |
    [System.Convert]::FromBase64String($env:CERT_B64) | Set-Content -Path codesign.pfx -Encoding Byte
  env:
    CERT_B64: ${{ secrets.WIN_CODESIGN_PFX_B64 }}

- name: Sign Windows installer
  if: runner.os == 'Windows'
  env:
    PSEUDOKRAT_SIGN_CERT_PATH: ${{ github.workspace }}\codesign.pfx
    PSEUDOKRAT_SIGN_PASSWORD: ${{ secrets.WIN_CODESIGN_PASSWORD }}
  run: pwsh -File packaging\sign_windows.ps1 -InstallerPath dist\installer\PseudokratSetup-*.exe
```

Wichtig: **Cert-Datei nach dem Sign-Schritt löschen**, damit sie nicht
in Artifacts landet.

---

## Verifikation nach dem Build

Vor jedem Release manuell prüfen:

```powershell
# Windows
signtool verify /pa /v dist\installer\PseudokratSetup-0.1.0.exe
```

```bash
# macOS
codesign --verify --deep --strict --verbose=2 dist/Pseudokrat.app
spctl --assess --type execute --verbose dist/Pseudokrat.app
```

Beide Befehle MÜSSEN „valid" liefern. Wenn nicht: nicht releasen.

---

## Was diese Schicht NICHT leistet

* **Reproducible Builds.** PyInstaller produziert verschiedene Hashes
  bei jedem Lauf (Build-Timestamp + Random-Salting). Wer reproducible
  builds will, muss `SOURCE_DATE_EPOCH` setzen und PyInstaller
  determinieren (siehe PyInstaller-Issue #6543).
* **Supply-Chain-Verification der Dependencies.** Das macht `pip-audit`
  separat (CI-Job `security`).
* **Code-Signing der ML-Modell-Dateien.** Die werden vom HuggingFace-
  Hub geladen, nicht von uns ausgeliefert. HuggingFace ist seit 2024
  TUF-signiert; mehr braucht es da nicht.
