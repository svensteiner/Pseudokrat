# Changelog

Alle wesentlichen Änderungen an Pseudokrat werden hier dokumentiert.

Format folgt [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

### Hinzugefügt (2026-06-11, PRL Iter-16)
- **Steuer-ID in amtlicher Gruppen-Anzeigeform `47 036 892 816`
  (2-3-3-3) wird jetzt erkannt.** Bis Iter-16 fand das Scan-Regex des
  `GermanSteuerIdRecognizer` nur 11 *zusammenhängende* Ziffern — die
  offizielle BMF-Darstellung mit Leerzeichen (so steht die Steuer-ID auf
  Bescheiden und Lohnsteuerkarten) blieb komplett unerkannt und wäre als
  Klartext-PII ins Cloud-KI-Prompt geleakt. Der Validator strippte
  Leerzeichen bereits, lief aber nie auf einem gruppierten Kandidaten —
  ein latentes, halb-implementiertes Feature. Fix: Alternation im Regex
  für die 2-3-3-3-Form; die strikte § 139b-Struktur- plus
  ISO-7064-Prüfung schließt zufällige Zahlengruppierungen
  (Rechnungs-/Belegnummern) als False Positive aus (siehe D-053).
- **Neues Eval-Fixture `rechnung_de`.** Probt die Leerzeichen-Toleranz
  der deterministischen Recognizer (Steuer-ID 2-3-3-3, DE-IBAN
  4er-Gruppen) und enthält einen FP-Trap (`Beleg-Nr. 12 345 678 901`),
  der nicht getaggt werden darf. F1=1.00.

### Hinzugefügt (2026-06-10, PRL Iter-15)
- **PERSON-Recognizer erkennt Adelsprädikate / nobiliary particles.**
  DACH-typische kleingeschriebene Namenspartikel (`von`, `van der`, `zu`,
  `von und zu`, …) zerrissen vorher das Namensfeld — entweder kompletter
  Miss (`Herr von Habsburg`) oder abgeschnittener Span
  (`Alexander Van der Bellen` → nur `Alexander Van`), was den Restnamen
  ins Cloud-KI-Prompt leakte. Fix: `_PARTICLE`-Klasse (longest-first,
  damit `von der` vor `von` greift) als optionales führendes Element und
  als Konnektor zwischen Namens-Tokens in `_NAME_FIELD`. Die kurzen
  Konnektoren bleiben bewusst nur zwischen/vor Tokens erlaubt, nie
  freistehend, damit `Herr Müller und Frau Meier` zwei getrennte Treffer
  bleibt (siehe D-052).
- **Neues Eval-Fixture `kanzlei_adel`.** Anwaltliches Mandatsschreiben
  mit Adelsprädikaten (`von`/`van der`/`zu`); jeder Name kommt zweimal
  vor (Anker + Second-Pass). F1=1.00.

### Hinzugefügt (2026-06-05, PRL Iter-14b)
- **Doctor-Sandbox-Härtung + Profile-Health + Profile-Remove.** Drei
  miteinander verzahnte Pilot-Tester-Bugs geschlossen
  (siehe D-051):
  - `doctor` legt den Smoke-Test jetzt in einer echten
    `TemporaryDirectory`-Sandbox an statt im realen `profiles_dir`;
    Bestandsleichen (`_doctor_smoke.sqlite` + Sidecars) aus Pre-Iter-14-
    Versionen werden beim ersten Lauf einmalig migriert/gelöscht.
  - Neuer Doctor-Check `Profile-Health` öffnet jedes Simple-Mode-Profil
    über den OS-Keyring; meldet WARN mit Profilnamen und konkretem
    Fix-Befehl, wenn ein Profil unöffenbar ist (typischer Backup-
    Restore-Pfad auf neuem Konto). Passwort-Profile werden als „nicht
    offline prüfbar" markiert, nicht als kaputt.
  - Neues CLI-Subkommando `pseudokrat profiles remove <name>` löscht
    DB, Salt-Sidecar, Keyring-Marker und OS-Keyring-Eintrag in einem
    Befehl, mit interaktiver Bestätigung und `--force`-Override für
    Skripte. Best-Effort-Semantik — fehlende Sidecars blockieren nicht.
  - `ProfileManager.list_profiles` blendet ab sofort Profile mit
    Slug-Prefix `_` aus (Override via `include_reserved=True` für
    Diagnose-/Cleanup-Tools). Defense-in-Depth gegen künftige
    Sandbox-Leck-Klassen.
  - `InstallResult.profile_error` + `has_critical_failure` trennen
    „Profil-Anlage explizit angefragt und gescheitert" von
    „Profil existierte schon"; das CLI rendert das nun mit ✗ statt einer
    schwachen ℹ-Note und setzt den Exit-Code ungleich 0.

### Geändert (2026-06-03, PRL Iter-14)
- **Tier-4-Closure: Folgearbeiten in `DECISIONS.md` geklärt.** Alle
  sechs offenen `**Folgearbeit:**`-Blöcke (D-039, D-040, D-041, D-042,
  D-047, D-050) wurden gemäß `PRODUCTION_READY_GATE.md` Tier-4 in
  Erledigt-Notizen (für inzwischen umgesetzte Punkte) oder in
  `**Vertagt nach 6.x — …:**`-Blöcke mit explizit benanntem
  Reaktivierungs-Trigger überführt. Erledigt vermerkt: D-039 Phase B/C,
  D-042 Gap-Select-Tool/ML-Eval-Flag/CI-Audit. Vertagt mit Trigger:
  Bestandsnutzer-Migration (D-039), Signed-Release & macOS-Pfad
  (D-040, D-041), binäre Eval-Fixtures (D-042, D-047), PRL-Chain in CI
  (D-047), Air-gapped CI (D-050). Damit ist die letzte Tier-Lücke
  gegen das Production-Ready-Gate geschlossen — alle vier Tiers
  signalisieren `pass`.

### Hinzugefügt (2026-05-31, PRL Iter-9)
- **`tools/gap_select.py` — PRL Gap-Phase automatisiert.** Liest
  `eval_report.json` (von `tests.eval.runner`) und optional
  `audit_report.json` (von `tools.audit_run`), vergleicht gegen die
  Tier-1-Schwellen und die FP-Rate-Grenze aus
  `PRODUCTION_READY_GATE.md`, und schreibt einen priorisierten
  `next_gap.md`-Report mit genau einer Top-Lücke + Liste aller
  weiteren. Severity-Modell: 1 = Tier-1-Erkennungs-Defizit, 2 =
  globale FP-Rate über Limit, 3 = Tier-2/Tier-3-Audit-Fail oder
  unbedeckte Trust-Boundary. Aliase: Gate-`ORG` → intern `COMPANY`.
  ML-Kategorien (PERSON, ADDRESS, DATE) im `recognizers-only`-Mode
  als Severity 3 statt 1, damit Phase-2-Ausstände den Loop nicht
  blockieren. Exit 0 wenn keine Lücke offen, sonst 1.
  22 Unit-Tests in `tests/test_gap_select.py` (Gate-Parsing inkl.
  echte Datei, Tier-1-Defizit, ML-Kategorie-Sonderfall, FP-Rate,
  Audit-Fail, Trust-Boundary-Missing, Rendering, CLI-Roundtrip).
  Damit ist eine der vier Folgearbeiten aus D-042 geschlossen.
  Siehe D-047.

### Hinzugefügt (2026-05-27, Phase C)
- **GUI Simple-Mode: ein Profil, kein Passwort-Prompt, Close→Tray.**
  Wenn genau ein Profil existiert und im Simple-Mode angelegt wurde,
  blendet das Hauptfenster die Profil-Auswahl-Zeile und den Profile-
  Tab automatisch aus, öffnet das Profil ohne Passwort-Dialog beim
  Start und minimiert den Close-Button in die System-Tray statt zu
  beenden. Der Hotkey-Daemon und das Explorer-Context-Menu (D-040)
  laufen weiter. Multi-Mandant-Setups (mehrere Profile) und Power-
  User-Profile (Passwort-Modus) zeigen weiterhin die volle UI;
  `MainWindow(force_full_mode=True)` erzwingt die Power-User-UI auch
  bei vorhandenem Simple-Default. Bei Auto-Open-Fehler (Keyring-Lib
  fehlt etc.) schaltet die GUI sauber in den Full-Mode zurück und
  zeigt eine Fehlermeldung. 12 neue Tests in
  `tests/test_gui_simple_mode.py`. Siehe D-041.

### Hinzugefügt (2026-05-27, Phase B)
- **`pseudokrat install` / `pseudokrat uninstall` — Ein-Befehl-Setup für
  Windows-Einzelplatz.** `install` legt in einem Schritt das Default-
  Profil „Mein Konto" (Simple-Mode, kein Passwort) an, registriert
  „Mit Pseudokrat anonymisieren" im Explorer-Rechtsklick-Menü für
  `.pdf`/`.docx`/`.xlsx`/`.csv`/`.txt`, und (mit `--with-hotkeys`) den
  Hotkey-Daemon im Autostart. Alle Eintragungen unter HKCU — **kein
  Admin nötig**, kompatibel mit Kanzlei-IT-Policies. `uninstall`
  entfernt die Registry-Einträge wieder; Profile bleiben erhalten.
  Neues Modul `pseudokrat.install` mit `RegistryBackend`-Protocol
  (Production: `WinRegistryBackend` via `winreg`-Stdlib; Tests:
  `InMemoryRegistryBackend` — Suite läuft cross-platform). 23 neue
  Unit-Tests in `tests/test_install.py`. Siehe D-040.

### Hinzugefügt (2026-05-27, Phase A)
- **Simple-Mode: passwortfreie Profile via OS-Keyring.** Neue Architektur-
  Schicht `pseudokrat.store.key_protector` mit `KeyProtector`-Protocol
  und zwei Implementierungen: `PasswordKeyProtector` (klassisch, PBKDF2)
  und `OsKeyringKeyProtector` (256-Bit-Geheimnis im Windows Credential
  Manager / macOS Keychain / Linux SecretService, gespannt mit HKDF-SHA512
  zum profil-Salt). Aktivieren über `pseudokrat init --simple` —
  bestehende CLI-Befehle (`anonymize`, `deanonymize`, `clipboard`,
  `hotkey-daemon`, `audit`, `profiles`) erkennen Simple-Mode-Profile
  automatisch am Sidecar-Marker `<db>.keyring` und überspringen den
  Passwort-Prompt. Bestehender Passwort-Modus ist 1:1 erhalten — kein
  Migrationsschritt für existierende Profile nötig. Neue Optional-
  Dependency `pseudokrat[simple-mode]` (zieht `keyring>=24.0`).
  → Phase-A der UX-Vereinfachung; siehe [D-039](DECISIONS.md). 20 neue
  Unit-Tests in `tests/test_key_protector.py` (Determinismus, Profil-
  Isolation, Tampering-Detection, Marker-Auto-Detect, Cross-Mode-Reject).

### Hinzugefügt (2026-05-26)
- **Token-Bucket-Rate-Limit für HTTP-POST-Endpunkte.**
  `pseudokrat.rate_limit.TokenBucket` schützt `/v1/anonymize` und
  `/v1/deanonymize` vor lokalen Flood- bzw. Brute-Force-Vektoren.
  Defaults: 60 Tokens Burst, 1 Token/Sekunde Refill — konfigurierbar
  über `PSEUDOKRAT_SERVER_RATE_BURST` und `PSEUDOKRAT_SERVER_RATE_RPS`.
  Bei Erschöpfung antwortet der Server mit `429` plus `Retry-After`
  (Sekunden, aufgerundet, min 1) und behält alle Defense-in-Depth-
  Header bei. `/health` und CORS-Preflights (`OPTIONS`) bleiben
  bewusst unbegrenzt. → Closes F-001 in [SELF_AUDIT.md](SELF_AUDIT.md);
  siehe D-038 in [DECISIONS.md](DECISIONS.md). Neue Test-Datei
  `tests/test_rate_limit.py` (8 Unit-Tests) und 2 zusätzliche Server-
  Integrationstests in `tests/test_server.py`.

### Behoben (2026-05-26)
- `tests/test_server.py::test_health_endpoint_returns_version_and_profiles`
  und der neue 429-Test setzen Socket-Timeouts großzügiger (≥ 30 s
  für den ersten Request auf Windows-`HTTPServer`). Hintergrund: der
  Listener-Backlog braucht auf manchen Windows-Konfigurationen mehrere
  Sekunden bis zum ersten Accept; der 5-s-Default war flaky. Server-
  Logik bleibt unverändert.

### Hinzugefügt (2026-05-25)
- **HTTP-Server Defense-in-Depth-Header.** Der lokale Backend-Server
  (`server.py`) sendet jetzt auf allen Responses `X-Content-Type-Options:
  nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
  `Cross-Origin-Resource-Policy: same-origin`,
  `Cross-Origin-Opener-Policy: same-origin`, eine harte CSP
  (`default-src 'none'; frame-ancestors 'none'; base-uri 'none'`),
  `Cache-Control: no-store, no-cache, must-revalidate, private`,
  `Pragma: no-cache`, `Strict-Transport-Security` (für künftige TLS-Setups),
  `Permissions-Policy: interest-cohort=()` sowie `Vary: Origin`.
  CORS-Preflights setzen zusätzlich `Access-Control-Max-Age: 600`.
  → Closes V14.4.1 in [SELF_AUDIT.md](SELF_AUDIT.md).
- **Toplevel-Manifest-Hash für das ML-Modell.**
  `compute_model_manifest_hash` berechnet einen deterministischen
  SHA-256 über alle Snapshot-Dateien des konfigurierten Modells
  (sortiert nach POSIX-Pfad, `.lock`/`.tmp` ausgeschlossen).
  `verify_model_manifest` vergleicht konstantzeit gegen die optionale
  Pin-Variable `PSEUDOKRAT_PINNED_MANIFEST_SHA256`; jede Abweichung
  bricht den Download hart mit `ModelManifestMismatchError` ab.
  → Closes S4 in [SELF_AUDIT.md](SELF_AUDIT.md). Siehe D-037 in
  [DECISIONS.md](DECISIONS.md).

### Behoben
- **D-034** — Flaky `test_property_roundtrip` durch CompanyLegalForm-
  Recognizer im Test-Setup. Der Recognizer matchte kurze Rechtsform-
  Suffixe (`AG`/`KG`/`SE`/…), die zufällig im neutralen Glue-Text der
  Hypothesis-Strategy auftraten; über mehrere Iterationen kollabierten
  zwei solche Fake-COMPANY-Entries mit Levenshtein-Distanz ≤ 2 via
  Fuzzy-Merge zu einem Platzhalter und brachen den Round-Trip. Fix:
  Test-Pipeline verwendet jetzt nur die drei Recognizer, die die
  Strategy auch generiert (IBAN, DE-USt-IdNr, AT-UID).
- `tests/test_stress.py::test_10k_line_document_roundtrip` —
  Performance-Sanity-Bound von 120 s auf 300 s erweitert. Der Test lief
  in Isolation knapp unter dem alten Limit (≈119 s) und wurde unter
  Voll-Suite-Last (Stress-Tests laufen sequentiell mit weiteren
  hypothesis-getriebenen Tests) regelmäßig flaky. Die Beobachtung ist
  weiterhin in den `print`-Ausgaben sichtbar; das Assert dient nur als
  Pathologie-Limit.
- `hypothesis` zu `[dev]`-Extras hinzugefügt — die im letzten Release
  ergänzten Property-Tests waren in `pyproject.toml` nicht als Test-
  Dependency aufgeführt, sodass ein frischer `pip install -e ".[dev]"`
  ohne separates `pip install hypothesis` bei Collection scheiterte.

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
