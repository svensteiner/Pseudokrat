# Pseudokrat — Installer Bauen

Diese Anleitung beschreibt, wie aus dem Pseudokrat-Quellcode ein **signierter
Windows-Installer** und ein **signiertes macOS-App-Bundle** erstellt werden.

> **Status:** Build-Pipeline ist vollständig automatisiert. Signing-Schritte
> sind vorbereitet, benötigen aber gültige Zertifikate vom OS-Hersteller —
> siehe [SIGNING.md](../SIGNING.md).

---

## Windows

### Voraussetzungen

* Windows 10/11 mit PowerShell 5.1+
* Python 3.11 oder 3.12 (`python --version` im Pfad)
* [Inno Setup 6](https://jrsoftware.org/isinfo.php) installiert
* Für Signing: Code-Signing-Zertifikat (PFX-Datei + Passwort) — siehe
  [SIGNING.md](../SIGNING.md)

### Bauen ohne Signing (Smoke-Test)

```powershell
# Vom Repo-Root aus, in aktiviertem venv:
.\.venv\Scripts\Activate.ps1
pwsh -File packaging\build_windows.ps1
```

Ergebnis:
* `dist\Pseudokrat\Pseudokrat.exe` — Konsolen-CLI (Einstieg für Kunden ohne
  Python): `Pseudokrat.exe setup` fragt Installation vs. Ordner-Lösung,
  `Pseudokrat.exe watch` startet die Ordner-Lösung.
* `dist\Pseudokrat\Pseudokrat-GUI.exe` — das PySide6-Hauptfenster.
* `dist\installer\PseudokratSetup-0.1.0.exe` — ungesignierter Installer

> Der Build bündelt auch die Ordner-Schiene inkl. **PyMuPDF** (PDF-Layout)
> und **RapidOCR** (Text in Bildern). RapidOCR bringt ONNX-Modelle mit; falls
> die EXE beim ersten PDF einen OCR-Importfehler zeigt, im Spec die
> `collect_all`-Liste prüfen (`rapidocr_onnxruntime`, `onnxruntime`, `cv2`).
> ML (torch/transformers) wird bewusst NICHT gebündelt.

> Ungesignierte Installer werden von Windows SmartScreen blockiert. Für
> Endnutzer-Distribution ist Signing **zwingend**.

### Bauen mit Signing (Release)

```powershell
$env:PSEUDOKRAT_SIGN_CERT_PATH = "C:\path\to\codesign.pfx"
$env:PSEUDOKRAT_SIGN_PASSWORD  = "geheim"
pwsh -File packaging\build_windows.ps1 -Sign
```

Das Skript signiert sowohl `Pseudokrat.exe` als auch den finalen
Installer-EXE mit SHA-256 + Timestamp.

---

## macOS

### Voraussetzungen

* macOS 12+ mit Xcode-Command-Line-Tools
* Python 3.11 oder 3.12
* Apple Developer ID (Application + Installer) für Signing
* App-spezifisches Passwort für Notarization

### Bauen

```bash
chmod +x packaging/build_macos.sh
./packaging/build_macos.sh
```

Mit Signing + Notarization:

```bash
export PSEUDOKRAT_APPLE_IDENTITY="Developer ID Application: Your Name (TEAMID)"
export PSEUDOKRAT_APPLE_ID="you@example.com"
export PSEUDOKRAT_APPLE_PASSWORD="app-specific-password"
export PSEUDOKRAT_APPLE_TEAM_ID="ABCDEF1234"
./packaging/build_macos.sh --sign --notarize
```

---

## CI-Builds

Eine `release.yml`-Workflow-Datei (siehe `.github/workflows/release.yml`)
löst den Windows- und macOS-Build bei Push eines `v*`-Tags aus und lädt
die Artefakte als GitHub-Release-Assets hoch.

Die Signing-Zertifikate stehen als GitHub-Actions-Secrets bereit:

| Secret | Beschreibung |
|---|---|
| `WIN_CODESIGN_PFX_B64`     | Base64-kodierte PFX-Datei |
| `WIN_CODESIGN_PASSWORD`    | PFX-Passwort |
| `MAC_DEVELOPER_ID`         | „Developer ID Application: ..." |
| `MAC_APPLE_ID`             | Apple ID für Notarization |
| `MAC_APPLE_PASSWORD`       | App-spezifisches Passwort |
| `MAC_TEAM_ID`              | 10-stellige Apple-Team-ID |

Niemals Secrets in den Repo committen. Siehe [SIGNING.md](../SIGNING.md).

---

## Was im Installer NICHT enthalten ist

Bewusst aus dem Bundle ausgeschlossen, weil zu groß bzw. optional:

* **HuggingFace Privacy-Filter ML-Modell** (~3 GB). Wird beim ersten Start
  vom Wizard auf Wunsch heruntergeladen und unter
  `%LOCALAPPDATA%\Pseudokrat\models\` gecacht.
* **PyTorch / transformers**. Werden erst beim ML-Download zusammen mit
  dem Modell via `pseudokrat model download` installiert. Ohne diese
  Pakete läuft Pseudokrat im Regex-Only-Modus (DACH-Recognizer +
  Email/Phone/URL/Secret/Company).
* **Python-Quelltext**. Endnutzer brauchen kein Python — alles ist im
  PyInstaller-Bundle eingefroren.

---

## Footprint

| Komponente | Größe |
|---|---|
| Installer-EXE                       | ~ 75 MB |
| Entpacktes Programmverzeichnis      | ~ 220 MB |
| Privatuser-Setup-Profile + Mappings | < 1 MB pro Profil |
| Optionales ML-Modell (Cache)        | ~ 3 GB |

Profile liegen unter `%LOCALAPPDATA%\Pseudokrat\profiles\` und werden
bei De-Installation **nicht** gelöscht — der Nutzer muss sie explizit
entfernen.
