# Pseudokrat — Production-Readiness-Status

Diese Datei tracked **alle in der Code-Review identifizierten Lücken**
zwischen dem heutigen Alpha-Stand und einem produktionsreifen Release
für DACH-Berufsträger. Sie ist die Single-Source-of-Truth für „Was
fehlt vor Release?".

**Letzter Stand:** 2026-05-27, autonom + interaktiv.

**UX-Vereinfachung — Phase A (2026-05-27) abgeschlossen:**

* **Simple-Mode landed.** Profile können jetzt ohne Master-Passwort
  angelegt werden (`pseudokrat init --simple`). 256-Bit-Geheimnis liegt
  im OS-Keyring (Windows Credential Manager / DPAPI, macOS Keychain,
  Linux SecretService). Alle CLI-Befehle erkennen Simple-Mode-Profile
  automatisch und überspringen den Passwort-Prompt. Bestehender
  Passwort-Modus bleibt 1:1 erhalten (Power-User / Kanzlei-Compliance).
  Siehe D-039 / S6 im Self-Audit. 21 neue Tests.
* **Phase B (offen):** `pseudokrat install`-Befehl + Explorer-Context-
  Menu + Hotkey-Autostart.
* **Phase C (offen):** GUI versteckt Profil-Selector im Simple-Mode-
  Default; Tray-First-Workflow ohne Hauptfenster.

**Heute hinzu gekommen (Stand-Update):**

* Phase-5-Scaffolds **Word** (`addins/word/`) und **Outlook**
  (`addins/outlook/`) parallel zum bestehenden Excel-Add-in →
  Punkt 8 von 🟡 (nur Excel) auf ✅.
* `SELF_AUDIT.md` — OWASP-ASVS-Level-2-Selbst-Audit + Pseudokrat-
  spezifische Trust-Boundary-Checks. Vorlektorat für Pentest.
* `PILOT_KIT.md` — vollständiges Onboarding-/Test-/Feedback-Material
  für 5-10 Pilotkanzleien. Pilot kann sofort gestartet werden, sobald
  Tester rekrutiert sind.
* `DSGVO_DRAFT.md` — Verarbeitungsverzeichnis, AV-Frage,
  Pseudonymisierungs-Begründung, Mandanten-Aufklärungs-Klausel,
  Kammer-Argumentation. Vorlektorat für DSGVO-Anwalt.
* D-036 — Strict-Mode für die Modell-Revision; eliminiert die
  letzte offene TODO im Production-Code.
* **2026-05-25 Self-Audit-Schliessung:**
    * V14.4.1 (Security-Header) von 🟡 auf ✅ — der lokale HTTP-Backend
      sendet ab sofort `X-Content-Type-Options`, `X-Frame-Options`,
      `Referrer-Policy`, `COOP`/`CORP`, eine harte CSP
      (`default-src 'none'`) sowie `Cache-Control: no-store` und
      `Vary: Origin`. Tests in `tests/test_server.py`.
    * S4 (Modell-Hash-Verifikation) von 🟡 auf ✅ — eigener
      Toplevel-Manifest-Hash über alle Snapshot-Files (siehe D-037).
      Operator kann via `PSEUDOKRAT_PINNED_MANIFEST_SHA256` einen
      bekannten Stand erzwingen; jeder Mismatch bricht den Download
      hart ab. Sechs neue Tests in `tests/test_model_install.py`.
* **2026-05-26 Self-Audit-Schliessung:**
    * F-001 (Rate-Limit auf POST-Endpunkten) **geschlossen** —
      Token-Bucket in `pseudokrat.rate_limit` schützt
      `/v1/anonymize`/`/v1/deanonymize`; 429 + `Retry-After` bei
      Erschöpfung. Defaults via Env-Var konfigurierbar. Siehe D-038.
      Damit ist V2.7.1 im Self-Audit von 🟡 auf ✅ gewandert; offen
      bleiben nur noch dokumentierte „bewusst akzeptierte" Trade-Offs
      und externe Blocker (Pentest/Code-Signing/Pilot/DSGVO).

---

## Übersicht — Punkte aus der Review-Antwort

| # | Punkt aus der Review | Code-Status | Externes nötig? | Release-Blocker? |
|---|---|---|---|---|
| 1 | Kein Installer | ✅ Scaffold (PyInstaller-Spec, Inno-Setup, build-Skripte) | Inno Setup 6 lokal, Apple Dev für DMG | Nein — laufen sobald Build-Maschine steht |
| 2 | Kein Code-Signing-Zertifikat | ✅ Sign-Skripte vorbereitet, Doku komplett | **Ja — Zertifikate kaufen** (Windows EV € 400-800 + macOS Apple Dev € 99) | **JA** für End-User-Distribution |
| 3 | Kein git-Repo / Releases | ✅ `git init` + CHANGELOG | Nein | Nein |
| 4 | ML-Modell „optional" | ✅ `pseudokrat model download` + Wizard-Page integriert | Nein | Nein — opt-in ist auch produktiv-tauglich |
| 5 | SQLCipher-Fallback statt echtem SQLCipher | ✅ Echtes SQLCipher via `sqlcipher3-wheels`, opt-in via `PSEUDOKRAT_USE_SQLCIPHER=1`, Datei-Magic-Detection | Nein | Nein — Fernet-Only ist bereits stark (AES-128-GCM + PBKDF2 256k) |
| 6 | XLSX-Formeln per Regex | ✅ Auf `openpyxl.formula.tokenizer` umgestellt; Named Ranges + Cross-Sheet-Refs werden korrekt behandelt | Nein | Nein |
| 7 | Hotkey-Workflow nur per OS-Tool | ✅ Optionaler `pseudokrat hotkey-daemon` mit `keyboard`/`pynput`-Backends | Nein | Nein |
| 8 | Keine Office-Add-ins | ✅ Scaffolds für **Excel + Word + Outlook**, alle Office.js + TypeScript, lokales HTTP-Backend (`pseudokrat server`) | Microsoft Partner Center für AppSource-Listing (kostenlos) | Nein — Add-in ist Nice-to-Have |
| 9 | Keine Differential-Privacy für Beträge | ✅ Rangbewahrende Permutation (`--dp-amounts`); Sum + Mean bleiben erhalten | Nein | Nein |
| 10 | Kein Bandit/pip-audit | ✅ Beide in CI (`.github/workflows/ci.yml`-Job `security`) | Nein | Nein |
| 11 | Kein Pentest | 🟡 [SELF_AUDIT.md](SELF_AUDIT.md) — OWASP-ASVS-L2-Selbst-Audit fertig, externer Pentest noch offen | **Ja — externer Anbieter** | **JA** für Berufsstand-Distribution |
| 12 | Kein echter User-Test | 🟡 [PILOT_KIT.md](PILOT_KIT.md) — Onboarding/Test/Feedback einsatzbereit, Pilotkanzleien noch nicht rekrutiert | **Ja — DACH-Pilotkunden** | **JA** vor Release |
| 13 | Keine DSGVO-/Berufshaftpflicht-Validierung | 🟡 [DSGVO_DRAFT.md](DSGVO_DRAFT.md) — Verarbeitungsverzeichnis + AV-Argumentation + Klauselvorlage, Anwalts-Sign-off noch offen | **Ja — DSGVO-Anwalt + Kammer-Kontakte** | **JA** für Kammer-Marketing |

**Verbleibende harte Blocker** (Punkte 2, 11, 12, 13): **vier** —
aber 11/12/13 sind durch Vor-Lektorate vorbereitet (s. o.). Externe
Schritte reduzieren sich auf reines Sign-off + Rekrutierung.

---

## Punkte mit Handoff-Plan (nicht autonom abschließbar)

### Punkt 2 — Code-Signing-Zertifikate

**Was fehlt:** Tatsächliches Cert + privater Schlüssel. Pseudokrat selbst
kann keinen Cert kaufen — das setzt eine Rechtsperson und einen
Identitäts-Nachweis voraus.

**Konkretes Vorgehen:**

1. **Windows.** Bei DigiCert oder Sectigo einen **EV Code-Signing Cert**
   bestellen. Identitäts-Nachweis: Handelsregisterauszug + Notar-
   Attestierung der zeichnungsberechtigten Person. Lieferung als
   physischer HSM-USB-Token nach ca. 5-10 Werktagen.
   * Kosten: ~ 400-800 €/Jahr je nach Anbieter.
   * Alternative für Bootstrap: OV-Cert (~ 250 €/Jahr), aber SmartScreen
     verlangt erst ~10.000 Installationen, bevor es nachhaltig vertraut.
   * Cloud-HSM (DigiCert KeyLocker, ssl.com eSigner) erleichtert CI-Builds.

2. **macOS.** Apple Developer Program Mitgliedschaft (€ 99/Jahr) →
   in Xcode „Developer ID Application" + „Developer ID Installer"
   anlegen. Privater Schlüssel landet im Schlüsselbund.

3. **In CI hinterlegen:** Secrets gemäß [SIGNING.md](SIGNING.md) §
   „GitHub Actions".

**Dauer:** 2-4 Wochen von Erstkontakt bis lauffähigem signiertem Build.
**Skripte stehen bereit:** `packaging/sign_windows.ps1`,
`packaging/sign_macos.sh`, dokumentiert in [SIGNING.md](SIGNING.md).

### Punkt 11 — Externer Pentest

**Was fehlt:** Audit durch zertifizierten Pentest-Anbieter (OWASP ASVS
oder BSI IT-Grundschutz konform).

**Konkretes Vorgehen:**

1. **Scope definieren.** Empfohlen mindestens:
   * Crypto-Review (PBKDF2-Parameter, AES-Modi, Salt-Handling,
     SQLCipher-Konfiguration).
   * File-Layer-Review (Datei-Handling, XLSX-Formula-Injection,
     PDF-Text-Extraktion).
   * HTTP-Backend-Review (Token-Vergleich, CORS, Replay-Schutz).
   * Memory-Hygiene (Originaltexte im Speicher länger als nötig?).
   * Audit-Log-Hash-Chain (Manipulationssicherheit, Race-Conditions).

2. **Anbieter (DACH-Markt):**
   * **Cure53** (Berlin, sehr renommiert, ~ 8.000-15.000 €/Pentest-Woche).
   * **SEC Consult** (Wien, gut für DACH-Kontext, ähnliche Preisspanne).
   * **Securai** (München, KMU-orientiert, ~ 5.000-10.000 €).
   * **Internet Security AG** (Schweiz, gut für CH-Fokus).

3. **Erwartete Dauer:** 2-3 Wochen für ein Audit dieser Größe inklusive
   Report-Erstellung. Plus 1-2 Wochen für Remediation und Re-Test.

**Kosten gesamt:** 8.000-20.000 € einmalig + jährliches Re-Audit.

**Vor dem Pentest:** Lege dem Anbieter [SECURITY_MODEL.md](SECURITY_MODEL.md)
vor (Trust-Boundaries, Crypto-Primitive, Pentest-Scope-Empfehlung),
damit das Audit fokussiert ist.

### Punkt 12 — Echter User-Test mit Berufsträgern

**Was fehlt:** Beta-Test mit echten Steuerberatern / Wirtschafts-
prüfern / Anwälten unter echten Mandanten-Texten (anonymisiert NACH
dem Test, niemals VORHER an uns geschickt).

**Konkretes Vorgehen:**

1. **5-10 Beta-Tester** aus dem persönlichen Netzwerk anwerben.
   Ideales Profil: Einzelkanzlei oder kleine Sozietät (≤ 5 Mitarbeiter),
   technisch interessiert aber nicht IT-Pro.

2. **Strukturierter Test-Plan:**
   * Tag 1: Installation aus dem signierten Installer.
   * Tag 2-4: Anonymisierung echter (synthetischer/aggregierter)
     Mandantenkorrespondenz.
   * Tag 5: Audit-Log-Review.
   * Wöchentliches 30-Minuten-Feedback-Call.

3. **Feedback-Kanäle:**
   * Github Issues (öffentlich, nur für Funktionalitäts-Bugs).
   * Privates Slack/Signal für sensible Beobachtungen.
   * Nach 4 Wochen: anonymes Feedback-Formular.

4. **Erfolgs-Kriterien:**
   * ≥ 80 % der Tester bleiben nach 4 Wochen aktiv.
   * Keine kritischen False-Negatives (PII übersehen) in den ersten 2 Wochen.
   * Keine Datenverluste (Profil-Korruption, vergessene Master-PW haben
     Garantie-Charakter — aber Logiklücken in Speicher-Pfaden sind Bugs).

**Dauer:** 6-8 Wochen von Recruiting bis Auswertung.
**Kosten:** Pro Tester ~ 200-500 € Aufwandsentschädigung (8-12 h zeitlicher
Aufwand) → 1.500-5.000 € Gesamtbudget.

### Punkt 13 — DSGVO / Berufshaftpflicht / Kammer

**Was fehlt:**

* **DSGVO-Auftragsverarbeitungsvertrag (AVV)** ist für rein lokal
  laufende Software **nicht erforderlich** (Pseudokrat ist kein
  Auftragsverarbeiter, weil niemand außer dem Nutzer die Daten sieht).
  Eine eindeutige Bestätigung dafür von einem DSGVO-Anwalt schützt aber
  vor späteren Diskussionen.
* **Berufshaftpflicht-Anerkennung** durch die größten DACH-Versicherer
  (Allianz, HDI, R+V) — sie sollen den Pseudokrat-Audit-Log als
  ausreichende Dokumentation der Anonymisierungs-Sorgfalt akzeptieren.
* **Kammer-Sponsoring / Marketplaces:**
  * WPK (Wirtschaftsprüferkammer): Listing in der Tool-Datenbank.
  * BStBK (Bundessteuerberaterkammer): Hinweis im Mitgliederbereich.
  * IFA (DACH-Anwaltskammern): DATEV-Marketplace.

**Konkretes Vorgehen:**

1. **DSGVO-Anwalt beauftragen** (Kostenpunkt: 1.500-3.000 € einmaliges
   Gutachten). Frage: „Ist Pseudokrat eine Auftragsverarbeitung?
   Welche Dokumentation muss bei Mandanten-Aufklärung vorgelegt werden?"
   Empfohlene Kanzleien: Reuschlaw (Hannover), CMS Hasche Sigle.

2. **Versicherer-Termine** mit den drei größten DACH-Berufshaftpflicht-
   Anbietern. Vorbereitung: 1-seitiges Whitepaper „Wie Pseudokrat
   Verschwiegenheitspflicht stützt".

3. **Kammer-Pitch-Deck.** Zielgruppe: Vorstandsmitglied „Digitalisierung"
   pro Kammer. Inhalt: Live-Demo + Audit-Log-Beispiel + Lizenz-Modell
   für Mitglieder.

**Dauer:** 3-6 Monate Vorlauf bis erste Kammer-Listings.
**Kosten:** 5.000-15.000 € (Anwalt + Whitepaper + Reisekosten).

---

## Empfohlene Release-Reihenfolge

```
Heute             →   Alpha (jetziger Stand, nur für interne Tests)
+ Wochen 1-2      →   Code-Signing-Cert erworben + signierte Builds verifiziert
+ Wochen 3-6      →   Externer Pentest abgeschlossen, Findings remediated
+ Wochen 7-14     →   User-Test (6-8 Wochen) parallel zur Kammer-Anbahnung
+ Woche 15        →   1.0-Release auf eigener Webseite (signiert, getestet, DSGVO-attestiert)
+ Quartal 4 nach 1.0 →  Office-Add-ins in AppSource verfügbar
```

**Gesamt-Zeitplan:** Realistisch 4-6 Monate vom heutigen Code-Stand bis
1.0-Release für Kanzlei-Distribution.

**Gesamt-Budget für Punkte 2/11/12/13:**
Code-Signing 500-900 € + Apple Dev 99 € + Pentest 8-20k € + User-Test
1,5-5k € + Recht/Kammer 5-15k € = **15.000-41.000 € einmalig**
+ 500-900 €/Jahr laufend.

---

## Was heute aus dem Repo testbar ist

Ohne externe Resources prüfbar:

* **Tests:** `pytest` → 340 Tests grün, ≥ 89 % Coverage.
* **Linting:** `ruff check src tests` → clean.
* **Type-Check:** `mypy src/pseudokrat` → clean.
* **Security-Scan:** `bandit -r src/pseudokrat -c pyproject.toml --severity-level medium`
  → no issues.
* **Dep-Audit:** `pip-audit --desc` → no known vulnerabilities.
* **Smoke-CLI:** `pseudokrat init --profile demo --password testtest123 && pseudokrat anonymize --profile demo --password testtest123 --text "Hofer Bau GmbH"`.
* **SQLCipher (opt-in):** `PSEUDOKRAT_USE_SQLCIPHER=1 pytest tests/test_sqlcipher_backend.py`.
* **Build-Smoke:** `python -m PyInstaller packaging/pseudokrat.spec --noconfirm` (verlangt
  PyInstaller im venv installiert).

---

## Code-Schichten, die der Pentester einsehen sollte

Folgende Module sind die **kritischen Crypto/Trust-Boundaries** —
Audit-Fokus sollte hier liegen:

| Modul | Was prüfen |
|---|---|
| `src/pseudokrat/store/secure_db.py` | Key derivation, salt handling, SQLCipher PRAGMA, Verification-Token |
| `src/pseudokrat/store/mapping_store.py` | Field-Level-Encryption, HMAC-Lookup, Fuzzy-Match-Side-Channel |
| `src/pseudokrat/store/audit_log.py` | Hash-Chain, prev_hash, Manipulation-Detection |
| `src/pseudokrat/server.py` | Token-Vergleich (constant-time), CORS, Bind-Adresse |
| `src/pseudokrat/dp/numeric_permute.py` | Fisher-Yates-Determinismus, Subkey-Domain-Separation |
| `src/pseudokrat/formats/xlsx_handler.py` | Formula-AST-Pfad, Named-Range-Mutation, kein Code-Eval |
| `src/pseudokrat/formats/pdf_handler.py` | Text-Extraktion, kein Markdown/HTML-Eval |

---

## Pflege dieser Datei

Bei jedem Release einen Eintrag in [CHANGELOG.md](CHANGELOG.md) hinzufügen
und HIER den Status der vier Blocker (2/11/12/13) updaten. Wenn ein Blocker
fällt, hier dokumentieren wann + wer + welcher Anbieter + welche Doku-IDs.
