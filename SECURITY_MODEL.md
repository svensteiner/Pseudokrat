# Pseudokrat — Sicherheitsmodell

Dieses Dokument beschreibt das Vertrauensmodell, die Crypto-Primitiven,
die Trust-Boundaries und die expliziten Non-Goals von Pseudokrat. Es
ist als Briefing-Vorlage für einen **externen Pentest** (Punkt 11 in
[PRODUCTION_READINESS.md](PRODUCTION_READINESS.md)) gedacht und sollte
dem Anbieter VOR Scope-Definition vorgelegt werden.

**Code-Referenz-Stand:** 2026-05-22 (Alpha 0.1.0).
**Sprache:** Deutsch (Code-Kommentare sind Deutsch; API-Identifier englisch).

---

## 1. Produkt- und Vertrauenskontext

Pseudokrat ist eine **lokal-only-Software**, die personenbezogene
Informationen (PII) aus Texten und strukturierten Dateien (TXT, CSV,
DOCX, XLSX, PDF) reversibel pseudonymisiert. Der Hauptzweck: ein
Berufsträger (Steuerberater, Wirtschaftsprüfer, Anwalt, Arzt, HR)
soll Mandantenmaterial in eine Cloud-KI (ChatGPT, Claude, Gemini)
schicken können, **ohne** dass identifizierende Informationen die
lokale Maschine verlassen.

**Trust-Boundary:** Pseudokrat vertraut

* dem **Endgerät** (sauberes Windows/macOS-User-Konto, kein Root-Kit).
* dem **Master-Passwort** (Nutzer wählt + verwahrt; mind. 8 Zeichen,
  siehe `MIN_PASSWORD_LENGTH` in `cli.py`).
* der **Python-Runtime und den signierten Wheels** der Direkt-
  Abhängigkeiten (`cryptography`, `openpyxl`, `pypdf`, `reportlab`,
  `python-docx`, `rapidfuzz`, `structlog`).

Pseudokrat vertraut **nicht**

* dem **Netzwerk** (außer dem expliziten initialen Modell-Download
  über das `huggingface_hub`-Paket, das der Nutzer ausdrücklich
  ausgelöst hat).
* dem **Cloud-KI-Endpunkt**.
* anderen **lokalen Anwendungen** ohne Authorization-Header für den
  HTTP-Server (`server.py`, siehe §4).
* **anderen Nutzer-Konten** auf demselben System.

---

## 2. Crypto-Primitive im Überblick

| Zweck | Algorithmus | Parameter | Quelle |
|---|---|---|---|
| Key-Derivation (Master-Passwort → Subkeys) | PBKDF2-HMAC-SHA512 | 256 000 Iterationen, 16-Byte-Salt, 96-Byte-Output | `secure_db.derive_keys` |
| Field-Level-Encryption (Originaltexte) | Fernet (AES-128-CBC + HMAC-SHA256) | 32-Byte-Schlüssel | `cryptography.fernet.Fernet` |
| Exact-Match-Lookup (normalisierte Form) | HMAC-SHA256 | 32-Byte-Schlüssel | `DerivedKeys.hmac_hex` |
| Optional Page-Level-Encryption | SQLCipher AES-256 | `cipher_page_size=4096`, `kdf_iter=256000`, `cipher_hmac_algorithm=HMAC_SHA512`, `cipher_kdf_algorithm=PBKDF2_HMAC_SHA512`, Page-Key in Hex (KDF übersprungen) | `secure_db._connect` |
| Audit-Log-Hash-Chain | SHA-256 über `"|"`-joined Felder | `prev_hash` von Vorgängerzeile; Genesis `"0"*64` | `audit_log._hash_entry` |
| Server-Bearer-Token | `secrets.token_urlsafe(32)` (256 Bit) | constant-time-Vergleich via `secrets.compare_digest` | `server.TokenStore`, `_require_token` |
| DP-Permutation-Schlüssel (XLSX-Beträge) | SHA-256 über (`master_secret` + Domain-Tag + sheet + col) | 64-Bit Subseed für Python `Random` | `dp/numeric_permute` |

**Key-Hierarchie:** Aus EINEM PBKDF2-Aufruf werden DREI disjunkte
32-Byte-Subkeys gewonnen (Bytes 0-31 → Fernet, 32-63 → HMAC, 64-95 →
SQLCipher). Domain-Separation ist via Offset (PBKDF2 ist KDF-tauglich)
+ explizite Subkey-Typisierung (`DerivedKeys`-Dataclass) sichergestellt.

---

## 3. Datenmodell und Storage-Layer

### 3.1 Profilstruktur

Jedes Mandantenprofil ist EINE Datei `<profile>.sqlite` plus EIN Sidecar
`<profile>.sqlite.salt` (16 Bytes Klartext). Default-Pfad:

* Windows: `%LOCALAPPDATA%\Pseudokrat\profiles\<slug>.sqlite`
* macOS/Linux: `~/.local/share/pseudokrat/profiles/<slug>.sqlite`

Konfigurierbar via `PSEUDOKRAT_DATA_DIR`.

### 3.2 Tabellen

Schema in `secure_db._SCHEMA`:

* `profile_metadata(key, value)` — **Klartext**. Inhalte: `profile_name`,
  `created_utc`, `verification_ct_b64`, `model_version_pinned`,
  `recognizer_version_pinned`, `schema_version`, `encryption_mode`,
  optional `mandanten_nr_pattern`.
* `mappings(placeholder, original_ct, normalized_ct, normalized_hmac,
  pii_category, first_seen_utc, last_used_utc, use_count)` —
  `*_ct`-Spalten Fernet-verschlüsselt, `normalized_hmac` als
  HMAC-SHA256-Hex (keyed, nicht über Passwort umkehrbar), Zeitstempel
  und Counter Klartext.
* `audit_log(...)` siehe §5 (Klartext, weil keine PII enthalten).

### 3.3 Passwortfreie Metadaten — Designwahl D-018/D-023/D-029

`profile_metadata` ist **bewusst** klartextlich, weil die GUI/CLI Profile
auflistet ohne das Master-Passwort des jeweiligen Profils zu kennen.
Felder sind allesamt Non-Secret:

* `profile_name` — vom Nutzer gewählter Anzeigename (z. B. „Mandant
  Hofer"). Wird im Dateisystem als Slug gespiegelt.
* `created_utc` — ISO-Datum.
* `mandanten_nr_pattern` — Regex-Schema, kein Mandantenwert.

**Pentest-Fokus:** Ist diese Annahme tragfähig? Gibt es Felder, die
versehentlich PII enthalten könnten (z. B. `recognizer_version_pinned`
mit eingebettetem Profilnamen)? Side-Channels via Datei-Größe oder
Reihenfolge?

### 3.4 SQLCipher-Modus (opt-in)

Aktivierung: `PSEUDOKRAT_USE_SQLCIPHER=1` vor Profil-Anlage. Existierende
Profile werden via Magic-Byte-Erkennung (`_file_is_sqlcipher`) im
korrekten Modus geöffnet, unabhängig vom Env-Flag. Beim Erstöffnen wird
gegen ein in der DB liegendes `verification_ct_b64` geprüft — falsches
Passwort wirft `InvalidPasswordError`, OHNE einen Crypto-Fehler nach
außen zu propagieren (`InvalidToken` wird in der Cipher-Library
abgefangen und zu `InvalidPasswordError` umgemappt).

**Pentest-Fokus:** Verifikationsschritt-Reihenfolge (SQLCipher-Open
vor Fernet-Verify), Timing-Side-Channel zwischen den beiden Pfaden,
Risiko des Klartext-Salt-Sidecars.

---

## 4. Lokaler HTTP-Server (Office-Add-in-Backend)

Modul: `server.py`. Default `127.0.0.1:31337`, **niemals** auf
externe Interfaces gebunden (keine Konfiguration für `0.0.0.0`).

### 4.1 Authentifizierung

`secrets.token_urlsafe(32)` (≈ 256 Bit) wird beim ersten Start in
`%LOCALAPPDATA%/Pseudokrat/server_token.txt` geschrieben (User-Read-
only impliziert, weil im User-Profil). Jeder Request muss
`Authorization: Bearer <token>` mitliefern. Vergleich via
`secrets.compare_digest` (constant-time).

### 4.2 CORS

Spiegel-Origin nur, wenn sie auf einem der vier hartkodierten
Präfixe basiert (`https://127.0.0.1`, `https://localhost`,
`https://excel.officeapps.live.com`, `https://outlook.office.com`).
Andere Origins bekommen den CORS-Header gar nicht — Browser blocken
also Cross-Origin-Zugriff. `OPTIONS` antwortet mit `204` ohne weitere
Auth-Anforderung (Standard für CORS-Preflight).

### 4.3 Endpunkte

* `GET /health` — Versionsnummer + Liste der Profilnamen. **Kein Auth.**
* `POST /v1/anonymize`, `POST /v1/deanonymize` — `{ "texts": [...] }`.

`ServerState` öffnet pro Request frische `MappingStore`/`AuditLog`-
Session, schließt sie im `finally`. Profile/Passwort wird beim Start
des Servers übergeben (CLI `pseudokrat server --profile X --password
<...>`), **nicht** pro Request — Add-in kennt das Master-Passwort
deshalb nie.

### 4.4 Bekannte Lücken / Pentest-Fokus

* `/health` listet Profilnamen ohne Auth — bewusst, weil das Add-in vor
  dem ersten Token-Read prüft, ob der Server überhaupt läuft. Profilnamen
  sind klassifiziert als Non-PII (§3.3). Bestätigen?
* Kein HTTPS — wir binden an `127.0.0.1` und vertrauen der Loopback-
  Boundary. Office-Add-ins verlangen HTTPS, das wird per
  `office-addin-dev-certs` in Phase 5 ergänzt. **Frage an Audit:**
  Loopback-only ausreichend gegen lokale Malware mit Userspace-
  Privilegien?
* Keine Replay-Protection (keine Nonces, kein Timestamp). Token ist
  langlebig; Rotation manuell. **Akzeptierter Trade-off** für ein
  lokales Single-User-Tool — bestätigen oder als Finding aufnehmen.
* Kein Rate-Limit — bewusst, weil lokal-only.

---

## 5. Audit-Log

Modul: `store/audit_log.py`. Tabelle `audit_log`, append-only, Spalten
allesamt Klartext.

### 5.1 Was geloggt wird

Pro `anonymize`/`deanonymize`-Operation EIN Eintrag mit:

* ISO-Timestamp (UTC)
* Operation (`"anonymize"` / `"deanonymize"`)
* `entity_counts` als JSON-Objekt (`{"PERSON": 3, "IBAN": 1}`)
* `anonymized_text_sha256` — **Hash des Anonymisats**, niemals des Originals
* `model_version`, `recognizer_version`
* `prev_hash`, `this_hash` (Hash-Chain)

### 5.2 Hash-Chain

`this_hash = SHA256(timestamp | operation | entity_counts_json |
anonymized_text_sha256 | model_version | recognizer_version | prev_hash)`.
Erster Eintrag verweist auf `GENESIS_HASH = "0"*64`. `verify_chain()`
rekonstruiert alle Hashes und detektiert jede Mutation (Insert, Update,
Delete einzelner Zeilen, Re-Order).

### 5.3 Pentest-Fokus

* **Tampering-Detection:** Ist die Kette gegen das nachträgliche
  Einfügen einer Zeile am Ende geschützt? (Ja, weil neue Zeile auf
  `last_hash` zeigen müsste und damit `prev_hash` der ECHT folgenden
  Zeile invalidiert würde — solange ECHT folgende Zeilen existieren.
  Bei „Append vor Genesis-Loop-Detector" siehe potentielle Lücke.)
* **Race-Conditions:** SQLite ist im Default-Mode serialisiert; gibt
  es Multi-Connection-Szenarien (z. B. Server + GUI parallel auf dem
  gleichen Profil), die zwei `_last_hash`-Reads → zwei `append`-Writes
  in inkompatibler Reihenfolge erzeugen können?
* **PII-Leck im Log:** Wir hashen das Anonymisat. Korrekt? Würde der
  Hash des Originals (z. B. via reproduzierbaren Recognizer-Output)
  Re-Identification ermöglichen? Wir sind hier konservativ.

---

## 6. Mapping-Store-Geheimnisse

Modul: `store/mapping_store.py`.

### 6.1 Was verschlüsselt ist

* `original_ct` — Fernet-verschlüsselter Originaltext.
* `normalized_ct` — Fernet-verschlüsselte normalisierte Form (lowercase,
  Umlauts gestrippt).

### 6.2 Was Klartext bleibt

* `placeholder` (`<PERSON_001>` etc.) — vergeben über `_next_placeholder`
  als sequentielle Nummer pro Kategorie. **Side-Channel:** Anzahl
  Platzhalter pro Kategorie ist sichtbar in der Datei → leakt
  „dieser Mandant hat ~50 Firmen, ~12 Personen genannt". Akzeptiert,
  weil ohne Originaltext keine Re-Identification möglich.
* `normalized_hmac` — keyed HMAC. Erlaubt Pseudokrat, neue Treffer in
  konstanter Zeit zu finden, OHNE alle Zeilen entschlüsseln zu müssen.
  Ohne den HMAC-Key kann ein Angreifer keine Original-Strings raten
  (HMAC ≠ unkeyed Hash).
* `pii_category`, `first_seen_utc`, `last_used_utc`, `use_count`.

### 6.3 Fuzzy-Match-Side-Channel

`find_by_original` macht beim Exact-Match-Miss ein FULL TABLE SCAN
über alle Mappings derselben Kategorie und entschlüsselt jede
`normalized_ct`-Spalte, um `should_merge`-Levenshtein zu rechnen. Das
ist O(n) pro Lookup, aber NUR nach Cache-Miss.

**Pentest-Fokus:**

* Timing-Attack: Variiert die Antwortzeit erkennbar mit Anzahl
  Mappings im Profil? Plausibel ja, aber Pseudokrat liefert das
  Ergebnis nicht über das Netzwerk; nur ein lokaler Beobachter (der
  schon Userspace-Privilegien hat) könnte das ausnutzen.
* Mitschneider eines Lookups könnte Fernet-Decrypts beobachten →
  Original-Plaintexts im Speicher; Memory-Hygiene ist unten erfasst.

---

## 7. Datei-Layer (XLSX, PDF, DOCX, CSV, TXT)

Module: `formats/*.py`.

### 7.1 XLSX

`openpyxl` parst nur Cell-Werte und Formel-Strings. Formeln werden via
`openpyxl.formula.tokenizer.Tokenizer` zerlegt, **nur** Tokens vom
Subtyp `TEXT` werden transformiert. **Keine** Formel-Evaluation. Named
Ranges werden in `workbook.defined_names` durchgegangen — Range-Namen
unverändert, String-Literale darin transformiert.

**Pentest-Fokus:**

* Formula-Injection: Können wir per Pseudonym (`<COMPANY_001>`) eine
  Formel manipulieren, die der KI-Empfänger später öffnet? Pseudonyme
  enthalten nur `<`, `>`, `_` und alphanumerische Zeichen → keine
  Excel-Special-Chars wie `=`, `&`, `+`.
* Sheet-Injection: Sheet-Namen werden NICHT transformiert. Reicht das?
* OPC-XML-Bombe in Eingabe-XLSX: openpyxl hat Limits, aber kein
  explizites defusedxml. **Empfohlene Mitigation:** defusedxml-Layer
  evaluieren.

### 7.2 PDF

`pypdf.PdfReader.pages[i].extract_text()` für jede Seite, Transform
auf den Text, dann reportlab schreibt eine **neue** Text-PDF. Layout
geht verloren — bewusst (siehe D-020).

**Pentest-Fokus:**

* PDF-Bombe / encrypted PDFs in Eingabe.
* Markdown/HTML in extrahiertem Text → wir leiten ihn direkt durch den
  Recognizer-Pfad (Plaintext-Behandlung); reportlab schreibt ihn als
  Text-Run, keine Style-Eval.

### 7.3 DOCX

`python-docx` iteriert Paragraphen + Tabellen-Zellen + Header/Footer.
Beim ersten Run mit Pseudonym wird der gesamte Paragraph-Text in den
ersten Run geschrieben, weitere Runs entleert (D-010). Inline-Formate
mitten im Wort gehen verloren.

### 7.4 CSV

Dialekt-Sniff via `csv.Sniffer`. UTF-8 BOM erkannt und erhalten.

---

## 8. DP-Permutation (XLSX-Beträge)

Modul: `dp/numeric_permute.py`. Opt-in über `--dp-amounts`.

* Schlüssel via `permutation_key_from_secret(master_secret)`
  (SHA-256 mit Domain-Tag `b"pseudokrat-dp-permute-v1"` — disjunkt
  von Fernet/HMAC/SQLCipher).
* Pro Spalte deterministischer 64-Bit-Seed aus `(sheet_name,
  column_letter)`.
* Fisher-Yates-Shuffle, None-Zellen bleiben am Platz.
* Sum-/Mean-/Min-/Max-preserving, Median preserving, Std-preserving.

**Pentest-Fokus:**

* DP-Garantie: Was leakt eine permutierte Spalte über die
  Original-Zuordnung? Wir wissen die Multimenge der Werte ist 1:1
  identisch — formaler ε-DP-Guarantee ist **nicht** gegeben; das ist
  als Engineering-Trade-off dokumentiert.
* Subkey-Domain-Separation gegen Fernet-Key-Leak: Tag-String reicht?
* Reproduzierbarkeit als Audit-Eigenschaft (selber Input + selbes
  Profil → selber Output) ist erwünscht; bestätigen, dass das kein
  Re-Identification-Vektor wird.

---

## 9. Modell-Layer (optional)

Modul: `pii/privacy_filter.py`, `pii/model_install.py`. Default OFF
(`PSEUDOKRAT_DISABLE_ML=1` oder einfach `[ml]`-Extra nicht installieren).
Wenn aktiv: HuggingFace-Modell `openai/privacy-filter` (oder via
`PSEUDOKRAT_MODEL_ID` überschrieben), lokal gecached unter
`%LOCALAPPDATA%/Pseudokrat/models/`.

* **Modell-Revision** in `pii/model_install.py:90` aktuell `"main"`
  — TODO vor 1.0: konkreten Git-SHA pinnen, damit Supply-Chain-Drift
  über Modell-Updates ausgeschlossen ist.
* Inference reines `torch.inference_mode`, kein Netzwerk-Call.

**Pentest-Fokus:**

* Supply-Chain: Was prüft `huggingface_hub` an Modell-Integrität?
  SHA-Pinning, Signaturverifikation?
* Adversarial-Input: Text der das Modell zu False-Negatives zwingt
  (PII übersehen) — Risiko-Klasse, aber kein Crypto-Bruch.

---

## 10. Memory-Hygiene

Aktuell:

* `MappingStore.find_by_original` entschlüsselt `normalized_ct` aller
  Kandidaten in eine lokale Variable, kein explizites `del` — Python
  GC räumt nach Scope-Verlassen.
* Master-Passwort wandert als `str` durch CLI/GUI/Controller/`MappingStore`
  bis `derive_keys`, dort wird das `bytes`-Material an `cryptography`
  übergeben. Kein explizites Zeroing.
* `cryptography.Fernet` hält keinen langlebigen Key-Cache; pro
  Operation neuer Roundtrip durch `_signing_key`/`_encryption_key`.

**Pentest-Fokus:** Welche Strings/Buffer bleiben nach Operation noch
im Heap? Lohnt eine `securemem`-Library für Master-Passwort und
Originaltext?

---

## 11. Telemetry, Netzwerk, Updates

**Explizit ausgeschlossen:**

* Kein Telemetry-Frame, kein „phone home" (siehe §10 Megaprompt).
* Keine Update-Checks ohne Nutzer-Bestätigung (Update-Pfad in Phase 6).
* Keine Cloud-Komponente.

**Erlaubte Netzwerk-Pfade:**

* `huggingface_hub.snapshot_download` bei expliziter Modell-Installation
  (`pseudokrat model download`).
* `pseudokrat server` bindet `127.0.0.1` (Loopback only).

---

## 12. Bekannte Trade-Offs (vom Pentest NICHT zu „Finding" machen)

Diese sind Engineering-Entscheidungen, dokumentiert in
[DECISIONS.md](DECISIONS.md):

* `profile_metadata` Klartext (D-018, D-023, D-029) — siehe §3.3.
* Salt-Sidecar Klartext (D-031) — Salt ist nicht geheim.
* SQLCipher ist opt-in, nicht default (D-031) — siehe §3.4.
* Fernet (AES-128-CBC + HMAC-SHA256) statt AES-256-GCM für
  Field-Level — Fernet hat IV-Disziplin schon eingebaut; AES-256
  wäre over-engineered (PBKDF2 256k stärker als 128-Bit-Brute-Force-
  Marge).
* DOCX-Run-Merging zerstört Inline-Formate (D-010).
* PDF-Layout geht verloren (D-020).
* Kein globaler Hotkey-Listener im Hauptprozess (D-024) — CLI-
  Subbefehl + OS-Hotkey-Tool.

---

## 13. Empfohlener Pentest-Scope

Aus PRODUCTION_READINESS.md §„Punkt 11" plus diesem Sicherheitsmodell:

1. **Crypto-Review** — `secure_db.py`, `mapping_store.py`,
   `audit_log.py`, `dp/numeric_permute.py`.
2. **File-Layer-Review** — `formats/xlsx_handler.py` (defusedxml-Frage,
   Formel-Injection), `formats/pdf_handler.py` (Bomb-Resistenz),
   `formats/docx_handler.py` (Run-Merging-Korrektheit).
3. **HTTP-Backend-Review** — `server.py` (Token-Vergleich, CORS,
   Replay, Bind-Adresse).
4. **Memory-Hygiene** — Welche Klartext-Buffer sind länger als nötig
   im Heap?
5. **Audit-Log-Hash-Chain** — Manipulationssicherheit, Race-Conditions
   bei Multi-Connection.
6. **Modell-Supply-Chain** — Modell-Revision pinning, Signaturen.

**Out of Scope:**

* Web-/Cloud-Komponente (gibt es nicht).
* Authentifizierung außerhalb der lokalen Maschine (gibt es nicht).
* DSGVO-Compliance-Aussage als solche (siehe Punkt 13 in
  PRODUCTION_READINESS.md, separater Anwalts-Pfad).

---

## 14. Pflege dieses Dokuments

Nach jedem Pentest-Re-Audit oder größeren Architektur-Change:

1. Diese Datei aktualisieren.
2. Eintrag in [DECISIONS.md](DECISIONS.md) (neue D-Nummer) anlegen.
3. [CHANGELOG.md](CHANGELOG.md) „Sicherheit"-Eintrag unter
   `[Unreleased]` schreiben.
4. [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) Punkt 11 mit
   Datum + Anbieter + Findings-Severity-Histogramm updaten.

---

*Autor: Pseudokrat-Build-Loop (autonom, 2026-05-22).
Review-Status: noch nicht von externem Auditor geprüft.*
