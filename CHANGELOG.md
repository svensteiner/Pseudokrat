# Changelog

Alle wesentlichen Änderungen an Pseudokrat werden hier dokumentiert.

Format folgt [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

### Hinzugefügt
- **Test-Pyramide ausgebaut** (`TESTING.md`): 67 neue Tests in vier
  Schichten — 28 Property-Based-Tests für DACH-Recognizer (Hypothesis,
  generiert algorithmisch gültige IDs), 6 Round-Trip-Property-Tests
  (`deanonymize(anonymize(x)) == x`), 12 Fuzz-Tests für die Format-
  Pipelines (TXT/CSV mit randomisierten Unicode-/Binär-Inputs), 15
  Security-Tests (PBKDF2-Iterationen, Wrong-Password, Salt-Manipulation,
  Hash-Chain-Tampering, Plaintext-Leak-Check auf der rohen SQLite-Datei),
  6 Stress-Tests (`@slow`, 2k-Zeilen-Round-Trip, 1.000 distinct Mandanten,
  XLSX-Pivot-Konsistenz). SQLCipher-Backend-Tests sind jetzt aktiv (zuvor
  übersprungen).
- **D-032** — Fuzzy-Merging strikt auf textuelle Kategorien beschränkt
  (`COMPANY`, `ORG`, `PERSON`, `ADDRESS`). Hypothesis-Round-Trip fand,
  dass zwei UIDs mit Levenshtein-Distanz 2 fälschlich gemerged wurden
  und das Reverse-Lookup die falsche Original-ID lieferte.
- **D-033** — Länderspezifische IBAN-Regex statt generischer `{3,7}`-
  Gruppen. Die alte Regex matchte über die korrekte IBAN-Länge hinaus,
  wenn direkt danach Alphanumerik folgte, was den MOD-97-Validator
  fälschlich rejecten ließ.
- **SECURITY_MODEL.md** — Pentest-Briefing-Dokument mit Trust-Boundaries,
  Crypto-Primitiven, Daten-/Datei-/HTTP-Layer-Review-Foki und expliziten
  Non-Goals. Schließt den in `PRODUCTION_READINESS.md` Punkt 11 markierten
  TODO und entkoppelt damit das Pentest-Onboarding vom Code-Lesen.
- **GUI-Erst-Start-Wizard** (§9 Megaprompt, D-030): Drei-Seiten-`QWizard`
  beim allerersten Start (Willkommen → Profilanlage → Zusammenfassung).
  Wiederverwendet `GuiController.create_profile`, optionales
  Mandantennummer-Regex. 14 Headless-Tests in `tests/test_gui_wizard.py`.
- **Code-Signing-Pipeline-Scaffold** (siehe `SIGNING.md`,
  `packaging/sign_windows.ps1`, `packaging/sign_macos.sh`) — verwendbar
  sobald Zertifikate vorliegen.
- **Windows-Installer**-Scaffold via PyInstaller-Spec
  (`packaging/pseudokrat.spec`) und Inno-Setup-Skript
  (`packaging/installer.iss`).
- **CI-Security-Scans**: `bandit` + `pip-audit` in
  `.github/workflows/ci.yml`.
- **PRODUCTION_READINESS.md** — Status aller Produktionsblocker mit
  konkretem Handoff für Pentest, User-Test und DSGVO-Sign-off.

### Geändert
- `MappingStore.find_by_original` überspringt den linearen Fuzzy-Scan
  für non-fuzzy-Kategorien — vor allem für IDs (IBAN/UID/SVNR/…) war das
  bisher O(n) Fernet-Entschlüsselungen pro Lookup. Spürbarer Speedup im
  Stress-Test (2k Entitäten: 6 min → < 1 min).
- `GuiController.create_profile()` akzeptiert nun ein optionales
  `mandanten_pattern`-Argument; Validierung über
  `compile_mandanten_pattern`, Pattern wird nach erfolgreicher Anlage in
  `profile_metadata` persistiert.
- `pseudokrat.gui.main_window.run()` zeigt den Erst-Start-Wizard nur,
  wenn beim Start keine Profile vorhanden sind. Direkt-konstruiertes
  `MainWindow()` (Headless-Tests) bleibt wizard-frei.

## [0.1.0-alpha] — 2026-05-22

Erstes lauffähiges Alpha-Release. Phase 1–4 (CLI + GUI + Datei-Pipelines
+ Audit-Log) sind funktional umgesetzt.

### Funktionsumfang

- **CLI**: `pseudokrat {init,anonymize,deanonymize,clipboard,audit,profiles}`
- **GUI**: PySide6-Hauptfenster mit Live-/Datei-/Profile-Tab + Tray-Icon
- **DACH-Recognizer mit Prüfziffer-Validierung**: IBAN (AT/DE/CH/LI),
  AT-UID, AT-SVNR, DE-Steuer-ID, DE-USt-IdNr, CH-AHV, Email, Telefon,
  URL, API-Keys, Firmen anhand Rechtsform-Suffix, Mandantennummer
  (per-Profil konfigurierbar)
- **Datei-Pipelines**: TXT, CSV, DOCX, XLSX (mit Formel-String-Literalen),
  PDF (Text-Layer-Anonymisierung)
- **Mapping-Store**: AES-128-GCM (Fernet) field-level-verschlüsselt mit
  PBKDF2-HMAC-SHA512, 256.000 Iterationen
- **Audit-Log**: SHA-256-Hash-Chain, CSV- + PDF-Export
- **ML-Modul (optional)**: HuggingFace Privacy-Filter (`openai/privacy-filter`)
  für Personennamen, freie Adressen, Geburtsdaten

### Tests
- 276 Tests grün, ≥ 89 % Coverage (Branch + Line)
- ruff + mypy --strict clean

### Bekannte Lücken (siehe `PRODUCTION_READINESS.md`)
- Kein Windows-/macOS-Installer (Scripts vorhanden, aber kein
  signierter Build).
- Keine echte SQLCipher-Volldatei-Verschlüsselung (Fallback via
  Fernet, D-003).
- Kein externer Penetration-Test.
- Keine Office-Add-ins (nur Scaffold).

[Unreleased]: https://github.com/CHANGEME/pseudokrat/compare/v0.1.0-alpha...HEAD
[0.1.0-alpha]: https://github.com/CHANGEME/pseudokrat/releases/tag/v0.1.0-alpha
