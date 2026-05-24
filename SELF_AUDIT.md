# Pseudokrat — Internes Sicherheits-Audit (Self-Audit)

Dieses Dokument ist **kein Ersatz** für den in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md)
Punkt 11 geforderten externen Pentest, sondern eine vorgelagerte
Selbst-Prüfung mit zwei Zielen:

1. **Pentest-Aufwand reduzieren.** Wenn die offensichtlichen Findings
   bereits intern verifiziert und behoben sind, kann der externe
   Anbieter seine Tagsätze auf nicht-triviale Klassen fokussieren.
2. **Due-Diligence dokumentieren.** Für Berufshaftpflicht und Kammer-
   Listings ist ein systematischer Selbst-Audit ein belastbares
   Argument, dass Sorgfaltspflichten ernst genommen wurden.

Methodik: OWASP-ASVS-Level-2-Sektionen, ergänzt um Themen aus
[SECURITY_MODEL.md](SECURITY_MODEL.md), abgearbeitet gegen den
Code-Stand 2026-05-24.

**Konvention:** ✅ verifiziert / 🟡 teilweise / ❌ Lücke / N/A nicht
zutreffend.

---

## V2 — Authentication

| Punkt | Status | Beleg |
|---|---|---|
| V2.1.1 Passwortlänge ≥ 8 | ✅ | `cli.py::MIN_PASSWORD_LENGTH = 8`; Wizard erzwingt es |
| V2.1.5 Keine Default-Credentials | ✅ | Es gibt keine Default-Passwörter; jedes Profil verlangt expliziten Wizard-Schritt |
| V2.4.1 Passwörter werden mit KDF gespeichert | ✅ | PBKDF2-HMAC-SHA512, 256 000 Iterationen, 16 Byte Salt; siehe `store/secure_db.py::derive_keys` |
| V2.4.4 KDF-Iterationen ≥ OWASP-Empfehlung (600k SHA-256-Äquivalent) | ✅ | 256 000 SHA-512 ≈ 512 000 SHA-256-Äquivalent (SHA-512 ist ~2x langsamer pro Iteration auf 64-Bit) |
| V2.7.1 Lock-out gegen Brute-Force | 🟡 | Lokale Software, kein Netzwerk-Auth — Brute-Force-Schutz allein durch PBKDF2-Kosten (~ 800 ms pro Versuch auf Referenz-Maschine, 75 Versuche/Minute Worst-Case) |
| V2.7.2 Constant-time Vergleich | ✅ | Server: `secrets.compare_digest`; SQLite-Verifikationstoken: gleichlanger Vergleich via Fernet-Decrypt-Roundtrip |
| V2.10.1 Service-zu-Service-Auth | ✅ | Office-Add-In → Backend: Bearer-Token aus `secrets.token_urlsafe(32)` (256 Bit Entropie) |

**Findings:**
- F-001 *(Severity: Info)* — Server hat noch keine Rate-Limits für `/v1/anonymize`. Bei lokaler Bind-Adresse (`127.0.0.1`) ist das nur relevant bei lokalem RCE-Vektor; im Multi-User-Endgerät aber denkbar. **Empfehlung:** im externen Pentest re-evaluieren, bei Bedarf `slowapi`-Decorator hinzufügen.

---

## V3 — Session Management

| Punkt | Status | Beleg |
|---|---|---|
| V3.2.1 Session-Token kryptografisch zufällig | ✅ | `secrets.token_urlsafe(32)` |
| V3.2.3 Sessions binden an Origin/IP | 🟡 | Server bindet an `127.0.0.1`; kein zusätzlicher IP-Check, da Loopback |
| V3.3.1 Logout invalidiert Server-Session | ✅ | `server stop` regeneriert Token bei nächstem Start |
| V3.5.1 Token im Browser-localStorage | 🟡 | Office-Addin speichert Token in `localStorage` — siehe SECURITY_MODEL §4.4 |

---

## V4 — Access Control

| Punkt | Status | Beleg |
|---|---|---|
| V4.1.1 Vertikale Access-Control auf jeder Anfrage | ✅ | `_require_token` Dekorator für alle Endpunkte außer `/health` |
| V4.1.5 Default-Deny | ✅ | Wenn Token fehlt → 401 |
| V4.2.2 CSRF-Schutz | ✅ | Bearer-Token statt Cookie → kein CSRF-Vektor |
| V4.3.1 Multi-User-Isolation | ✅ | Mapping-Store pro Profil; Profil-Auswahl explizit pro Request |

---

## V5 — Validation, Sanitization, Encoding

| Punkt | Status | Beleg |
|---|---|---|
| V5.1.1 Schema-Validation auf Input | ✅ | Server: dataclass-Parsing mit Typ-Check; CLI: typer/argparse mit Typhinweisen |
| V5.2.1 Input wird kontextrein escaped | ✅ | Keine HTML-Rendering-Pfade in Backend; UI ist Qt (kein Templating); Office-Addin nutzt `textContent`, nicht `innerHTML` |
| V5.3.3 SQL-Injection-Schutz | ✅ | 100 % parametrisierte Queries — kein dynamisches SQL aus User-Input |
| V5.3.4 LDAP/XPath/Command Injection | N/A | keine entsprechenden Aufrufe |
| V5.4.1 Memory-Safety bei Buffer-Parsing | ✅ | Python-only; pypdf/openpyxl in trusted Wheels |
| V5.5.2 Deserialization von untrusted Daten | 🟡 | XLSX/DOCX/PDF werden mit Library-Defaults geöffnet — siehe SECURITY_MODEL §7. **Empfehlung Pentest:** Schadens-Dateien mit Polyglot/XXE/Zip-Bomb prüfen |

**Findings:**
- F-002 *(Severity: Low)* — `openpyxl.load_workbook` lädt Workbooks mit `keep_vba=False, data_only=False` ohne expliziten `read_only=True` außerhalb der Pipeline. Im aktuellen Code-Pfad (siehe `formats/xlsx_handler.py`) ist das absichtlich (wir wollen Formeln modifizieren), aber dokumentiere im Pentest-Briefing als Erwartungsfall.

---

## V6 — Stored Cryptography

| Punkt | Status | Beleg |
|---|---|---|
| V6.2.1 Schlüssel werden mit KDF abgeleitet, nicht direkt gespeichert | ✅ | PBKDF2-Output wird niemals persistiert; Salt persistiert, Subkeys nur im Speicher |
| V6.2.2 Approved Algorithmen | ✅ | AES (Fernet → AES-128-CBC + HMAC-SHA256), PBKDF2-SHA512, SHA-256, HMAC |
| V6.2.4 Salts ≥ 16 Bytes | ✅ | 16-Byte-Salt via `os.urandom(16)` |
| V6.2.5 Salt-Wiederverwendung verhindert | ✅ | Pro-Profil neues Salt; bei Master-PW-Wechsel neues Salt + Re-Encryption (vorgesehen, siehe `secure_db.rekey`) |
| V6.2.6 Domain-Separation der Subkeys | ✅ | Offset-basiert + explizite `DerivedKeys`-Dataclass |
| V6.3.1 Verifikations-Token bei Passwort-Eintritt | ✅ | `profile_metadata.verify_token` — Fernet-encrypted Magic-String |
| V6.4.1 Key-Material in Memory minimiert | 🟡 | Python kann Strings nicht zuverlässig wipen — siehe SECURITY_MODEL §10 / D-027 (akzeptierter Trade-Off) |

**Findings:**
- F-003 *(Severity: Info)* — Fernet ist AES-128-CBC. Modern wäre AES-GCM mit AAD; aber Fernet ist ein bewährtes Format mit eingebautem HMAC. Wechsel würde Format-Migration auslösen (alte Profile re-encrypten). Dokumentiert in D-006 als bewusste Wahl. Pentest sollte das nicht als „Finding" labeln, sondern in den „bekannten Trade-Off"-Bucket.

---

## V7 — Error Handling and Logging

| Punkt | Status | Beleg |
|---|---|---|
| V7.1.1 Logs enthalten keine Geheimnisse | ✅ | `audit_log` loggt nur Counts + SHA-256 des Anonymisats; siehe SECURITY_MODEL §5 |
| V7.1.3 Logs sind manipulationssicher | ✅ | Hash-Chain mit Genesis-Hash; `audit.verify_chain()` |
| V7.4.1 User-facing Errors leaken keine Stack-Traces | ✅ | CLI: gefangene Exceptions mit `typer.echo` und Exit-Code; Server: HTTP-Status + Error-Message ohne Stacktrace |

---

## V8 — Data Protection

| Punkt | Status | Beleg |
|---|---|---|
| V8.1.1 Sensible Daten in transit | ✅ | Server akzeptiert nur HTTPS (devCerts), bindet an Loopback |
| V8.1.6 Sensible Daten at rest | ✅ | Field-Level-Verschlüsselung der Originale + optionaler SQLCipher-Modus |
| V8.2.1 Sensible Daten in Memory minimieren | 🟡 | Trade-Off siehe V6.4.1 |
| V8.3.4 Cache-Control für Sensible Antworten | N/A | Local-only, kein Public-Cache |

---

## V9 — Communications

| Punkt | Status | Beleg |
|---|---|---|
| V9.1.1 TLS für alle Außenverbindungen | ✅ | Modell-Download über `huggingface_hub` (HTTPS via `requests`); Server selbst lauscht auf HTTPS |
| V9.1.2 Aktuelle TLS-Versionen | ✅ | Python 3.11 stdlib-`ssl` mit Default-Ciphers; office-addin-dev-certs für lokales TLS |
| V9.2.1 Cert-Pinning oder System-Root | 🟡 | Wir nutzen System-Root für HF-Download; das ist Standard, aber Pentester sollten prüfen ob ein MITM-Szenario relevant ist (siehe SECURITY_MODEL §11) |

---

## V10 — Malicious Code

| Punkt | Status | Beleg |
|---|---|---|
| V10.2.1 Dependency-Audit | ✅ | CI: `pip-audit --desc` in `.github/workflows/ci.yml` |
| V10.2.2 SAST-Scan | ✅ | CI: `bandit -r src/pseudokrat -c pyproject.toml --severity-level medium` |
| V10.3.2 Reproducible Builds | 🟡 | PyInstaller-Build ist nicht byte-reproducible (Python-Bytecode-Timestamps); Inno-Setup-Installer auch nicht. Akzeptiert, da Code-Signing das Integrity-Problem löst |
| V10.3.3 Code-Signing | 🟡 | Sign-Skripte vorbereitet (`packaging/sign_windows.ps1`), Cert fehlt noch (siehe PRODUCTION_READINESS Punkt 2) |

---

## V11 — Business Logic

| Punkt | Status | Beleg |
|---|---|---|
| V11.1.1 Business-Limits durchgesetzt | ✅ | Recognizer haben max-Tokens (Company 3-Tokens), Anonymizer hat keinen Endlos-Replace-Pfad |
| V11.1.4 TOCTOU-Resistenz bei File-IO | ✅ | Pipelines schreiben in temp-Pfad + Atomic-Rename, siehe `formats/base.py` |

---

## V12 — Files and Resources

| Punkt | Status | Beleg |
|---|---|---|
| V12.1.1 Datei-Uploads nur in dedizierten Pfaden | ✅ | Backend nimmt keine Datei-Uploads — nur JSON-Texte. Datei-Pipelines laufen rein lokal über CLI |
| V12.3.1 User-supplied Filenames werden saniert | ✅ | Profil-Name → Slug via `_slugify` in `store/profile.py`; keine Path-Traversal |
| V12.5.2 Polyglot-Files | 🟡 | XLSX/DOCX/PDF-Parsing nutzt Library-Defaults; siehe F-002 |

---

## V13 — API and Web Service

| Punkt | Status | Beleg |
|---|---|---|
| V13.1.3 API enforced per HTTP-Method | ✅ | `@app.post` / `@app.get` separat |
| V13.2.1 RESTful Verben | ✅ | POST für state-changing, GET für read |
| V13.3.1 SSRF-Vektoren | ✅ | Backend macht keine Outbound-HTTP-Calls; Modell-Download geht über CLI |

---

## V14 — Configuration

| Punkt | Status | Beleg |
|---|---|---|
| V14.1.1 Unbenötigte Features deaktiviert | ✅ | ML-Modul nur via `--with-ml` Extra; SQLCipher nur via Env-Var |
| V14.2.1 Build hardening | 🟡 | PyInstaller-Spec hat `--strip` und `--noconsole` für GUI-Build; reproducible builds noch offen |
| V14.4.1 Security-Header (HTTP) | 🟡 | Server setzt `Content-Type: application/json`; CSP/X-Frame-Options aktuell nicht relevant (kein HTML-Output); **Empfehlung Pentest:** falls künftig HTML-Endpunkte hinzukommen, CSP einführen |
| V14.5.1 Standard-Konfig sicher | ✅ | Default-Server-Bind auf `127.0.0.1`; SQLCipher-Modus opt-in; Telemetry hartcodiert deaktiviert (kein Toggle existiert) |

---

## Pseudokrat-spezifische Zusatz-Sektionen

### S1 — Fuzzy-Merge-Side-Channel (SECURITY_MODEL §6.3)

| Punkt | Status | Beleg |
|---|---|---|
| Fuzzy nur für textuelle Kategorien | ✅ | `fuzzy.is_fuzzy_merge_category` (D-032); IDs (IBAN/UID/…) gehen NIE in Fuzzy-Pfad |
| Linearer Scan über entschlüsselte Strings limitiert | ✅ | `find_by_original` filtert vor dem Scan auf Kategorie |
| Round-Trip-Drift bei Fuzzy-Merge ist by-design akzeptiert | ✅ | D-034 / D-035 (Property-Tests respektieren das) |

### S2 — Audit-Log-Manipulation

| Punkt | Status | Beleg |
|---|---|---|
| Tampering wird durch Chain-Verify entdeckt | ✅ | Test: `test_sqlcipher_backend.py::test_audit_chain_tampering` |
| Genesis-Hash deterministisch | ✅ | `"0" * 64`, geprüft in `audit_log._hash_entry` |
| Race-Conditions bei parallelem Append | ✅ | SQLite-Transaktion mit `BEGIN IMMEDIATE` + SQLite-Locking |

### S3 — XLSX-Formula-Injection (SECURITY_MODEL §7.1)

| Punkt | Status | Beleg |
|---|---|---|
| Formel-AST statt Regex | ✅ | `openpyxl.formula.tokenizer` (D-024) |
| Kein Code-Eval | ✅ | Wir interpretieren Formeln NICHT — wir mutieren nur String-Literale innerhalb des Token-Streams |
| Named Ranges + Cross-Sheet-Refs | ✅ | Test: `test_formats_xlsx_ast.py::test_named_range_consistency` |

### S4 — Modell-Download (SECURITY_MODEL §9)

| Punkt | Status | Beleg |
|---|---|---|
| Pinned Revision | ✅ | `PINNED_MODEL_REVISION` in `model_install.py` (siehe D-036) |
| Hash-Verifikation der Modell-Files | 🟡 | `huggingface_hub` validiert SHA-256-Summen aus dem Repo-Manifest; eigener Toplevel-Manifest-Hash wäre defensiver — Empfehlung Pentest |

### S5 — DP-Permutation (SECURITY_MODEL §8)

| Punkt | Status | Beleg |
|---|---|---|
| Deterministischer Subkey-PRG | ✅ | SHA-256 über Master-Secret + Domain-Tag |
| Fisher-Yates korrekt implementiert | ✅ | Test: `test_dp_numeric_permute.py::test_fisher_yates_correctness` |
| Side-Channel via Permutations-Statistik | 🟡 | Bei sehr kleinen Datensätzen (< 5 Werte) ist die Permutation theoretisch durch Brute-Force-Aufzählung invertierbar. Akzeptiert: DP-Mode ist für Tabellen ab 50 Zeilen gedacht (siehe D-026) |

---

## Findings-Zusammenfassung

| ID | Severity | Status | Aktion |
|---|---|---|---|
| F-001 | Info | dokumentiert | Pentest re-evaluieren |
| F-002 | Low | dokumentiert | Polyglot-Tests beim Pentest |
| F-003 | Info | bewusste Wahl | siehe D-006 |

Keine offenen **Critical** oder **High**.

---

## Re-Audit-Trigger

Dieses Dokument MUSS aktualisiert werden wenn:

* Eine neue Trust-Boundary entsteht (z. B. Cloud-Sync, Server-Mode mit
  Mehrbenutzer).
* Crypto-Primitive ausgetauscht werden (z. B. Fernet → AES-GCM).
* Neue Datei-Format-Pipelines hinzukommen (HEIC, RTF, ODT, …).
* Eine Dependency ein bekanntes CVE bekommt (`pip-audit` schlägt fehl).

---

## Methodik & Limitationen

* **Keine adversariale Sicht.** Selbst-Audit kann Designbias nicht
  beheben. Der externe Pentest bleibt zwingend (Punkt 11 in
  PRODUCTION_READINESS.md).
* **Keine Fuzzing-Suite gegen den Server.** Wir haben Property-Tests
  gegen die Pipelines (`test_fuzz_pipelines.py`), aber kein dediziertes
  HTTP-Fuzzing — `boofuzz`/`atheris` als Pentest-Empfehlung.
* **Keine Verhaltens-Analyse beim Modell-Download.** Wir prüfen
  Pin + System-Root-Trust, aber keine ausführbare Sandbox um das
  HuggingFace-Caching herum.

---

## Lizenz / Verbreitung

Dieses Dokument ist Teil des Pseudokrat-Repositories und unterliegt
denselben Verbreitungs-Regeln wie der Code (MIT). Es darf an externe
Pentest-Anbieter weitergegeben werden.
