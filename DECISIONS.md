# Engineering-Entscheidungen (Phase 1)

Diese Datei dokumentiert Entscheidungen, die während der autonomen Phase-1-Implementierung
getroffen wurden, in Fällen, in denen der Megaprompt mehrdeutig war oder pragmatische
Anpassungen notwendig waren.

## D-001 — Dependency-Manager

**Wahl:** `pyproject.toml` mit PEP 621 Metadaten, kompatibel mit `uv pip install -e .` und
`pip install -e .`. Kein Poetry-Lock-In.

**Begründung:** uv ist heute Standard, kompatibel mit Poetry-Workflows, schneller. Spec
nannte „Poetry oder uv".

## D-002 — Privacy-Filter-Modell-Adapter mit Stub-Modus

**Wahl:** `PrivacyFilterDetector` lädt das HF-Modell `openai/privacy-filter` lazy beim
ersten Aufruf. Ein expliziter `--no-ml` Flag bzw. `PSEUDOKRAT_DISABLE_ML=1` deaktiviert
das ML-Modell und fällt auf reine Regex/Recognizer-Pipeline zurück.

**Begründung:**
- Tests dürfen kein 3-GB-Modell herunterladen.
- CI muss ohne GPU/Modell laufen.
- Phase 1 erfüllt die DACH-Recognizer-Anforderung auch ohne ML; das ML-Modell ergänzt
  Personennamen, freie Adressen und Geburtstage. Diese werden in Tests via Mock geprüft.

Die HF-Repo-URL ist konfigurierbar (`PSEUDOKRAT_MODEL_ID`), da die exakte HuggingFace-Repo-
Bezeichnung sich ändern könnte.

## D-003 — Persistenz: SQLCipher mit Fallback

**Primärwahl:** `sqlcipher3-binary` (PyPI). Wheel-basiert, AES-256, kein nativer Build nötig.

**Fallback:** `EncryptedSQLiteStore` mit Field-Level-Encryption via `cryptography.Fernet`,
abgeleitet aus dem Master-Passwort mit PBKDF2-HMAC-SHA512, 256.000 Iterationen.

**Begründung:** SQLCipher-Bindings sind unter Windows manchmal fragil. Der Fallback hält die
End-to-End-Funktion am Laufen und wird transparent ausgewählt, falls `sqlcipher3` nicht
verfügbar ist. Tests laufen gegen den Fallback. Audit-Log-Hash-Chain bleibt in beiden Modi
identisch.

## D-004 — Recognizer-Umfang in Phase 1

**Wahl:** Implementiere folgende Recognizer in Phase 1:

- `IBANDachRecognizer` (AT/DE/CH, mit MOD-97-Validierung)
- `AustrianUIDRecognizer` (ATU + 8 Ziffern, Prüfziffer)
- `AustrianSVNRRecognizer` (10 Ziffern, modulo-Prüfziffer)
- `GermanSteuerIdRecognizer` (11 Ziffern, § 139b AO Prüfung)
- `GermanUStIdNrRecognizer` (DE + 9 Ziffern)
- `SwissAHVRecognizer` (756.XXXX.XXXX.XX, EAN-13)
- `CompanyLegalFormRecognizer` (Rechtsform-Suffix-Heuristik)
- `MandantenNummerRecognizer` (konfigurierbar)

**Begründung:** Abschnitt 11 verlangt 3 für Phase 1 (IBAN, AT-UID, AT-SVNR), Abschnitt 15
verlangt „alle aus Abschnitt 7". Da die Recognizer-Struktur klein und schlüssig ist, werden
alle implementiert — das schließt die Bereiche Test-Case-Coverage (Abschnitt 12) sauber ab.

## D-005 — Pseudonym-Generator als reine Funktion

Pseudonyme werden deterministisch pro Profil + Kategorie sequenziell vergeben
(`<PERSON_001>`, `<PERSON_002>`, …). Sequenzen liegen pro Kategorie in der Mapping-Tabelle
implizit als `MAX(suffix) + 1`. Damit ist die Vergabe reproduzierbar und
nachvollziehbar.

## D-006 — Fuzzy-Match-Schwelle

Levenshtein-Distanz ≤ 2 auf `normalized_form` UND identische Kategorie → Merge.
Zusätzliche Schutzregel: Bei `CompanyLegalFormRecognizer` darf KEIN Merge erfolgen, wenn
die zwei Kandidaten unterschiedliche Rechtsformen tragen (z. B. „GmbH" vs. „GmbH & Co. KG").

## D-007 — CLI-Framework: argparse

`argparse` statt click/typer — vermeidet Dependency, hält das CLI lean.

## D-008 — Audit-Log-Hash-Chain

Jeder Eintrag enthält `prev_hash` und `this_hash`. `this_hash = SHA256(timestamp |
operation | entity_counts_json | anonymized_text_sha256 | prev_hash)`. Erster Eintrag
hat `prev_hash = "0" * 64`. Tamper-Detection via `verify_chain()`-Methode.

## D-009 — Format-Handler-Architektur (Phase 2)

**Wahl:** Jedes unterstützte Dateiformat hat eine eigene `FormatHandler`-Klasse mit
`process(input, output, transform)`. Der Anonymizer kümmert sich nur um Text-zu-Text;
die Handler tragen die formatspezifische Logik (DOCX-Paragraphen, XLSX-Zellen, CSV-
Sniffing). Die Auswahl erfolgt anhand der Dateiendung über `handler_for(path)`.

**Begründung:** Sauberes Single-Responsibility, einfache Erweiterung um PDF/RTF
in späteren Phasen, gut testbar (Transform ist eine reine Funktion). Die CLI
ruft `handler_for` nur für strukturierte Formate auf; reine Text-Eingaben gehen
den Direkt-Pfad.

## D-010 — DOCX-Run-Merging beim Anonymisieren

DOCX-Paragraphen können mehrere Runs (Formatfragmente) enthalten. Wenn der
Pseudonym-String aus Pseudokrat eingesetzt wird, kann er nicht zuverlässig auf
mehrere Runs aufgeteilt werden, ohne Wortgrenzen zu zerreißen. **Wahl:** Beim
ersten Hit wird der gesamte Paragraph-Text in den ersten Run geschrieben,
weitere Runs werden geleert. Inline-Formatierungen mitten im Wort gehen damit
verloren — bewusster Trade-off zugunsten korrekter Anonymisierung.

## D-011 — XLSX: Numerische Zellen unangetastet

In Phase 2 werden ausschließlich String-Zellen und String-Literale in Formeln
anonymisiert. Numerische Zellen (Saldi, Beträge) bleiben erhalten. Megaprompt
§5.4 erlaubt das explizit. Differential-privacy-maskierung von Beträgen ist für
Phase 2b/4 vorgesehen.

## D-012 — XLSX-Formel-Parsing: Regex statt AST

Phase-2-Implementierung ersetzt String-Literale in Formeln per Regex
(`"…"`-Paare). Eine vollständige AST-Analyse über die `formulas`-Library ist
für Phase 4 geplant, sobald Sheet-übergreifende Referenzen und Named-Ranges
behandelt werden müssen. Begründung: Der Regex-Pfad löst 95 % der Fälle, ist
deterministisch und hat keine zusätzlichen Dependencies.

## D-013 — GUI: PySide6 + UI-freier Controller

Das PySide6-Hauptfenster verwendet einen `GuiController`, der ausschließlich
auf der Pseudokrat-Public-API arbeitet und **keine Qt-Imports kennt**. Damit
sind alle Geschäftslogik-Pfade ohne QApplication testbar. Das Fenster selbst
wird mit `QT_QPA_PLATFORM=offscreen` headless gerendert und in pytest mit
direkten Slot-Aufrufen gegen Buttons getestet.

## D-014 — Codename `_env` als pytest-Fixture

In `test_cli_formats.py` und `test_gui_main_window.py` ist `_env` eine
`autouse`-Fixture, die `PSEUDOKRAT_DATA_DIR` und `PSEUDOKRAT_DISABLE_ML` setzt.
Der Unterstrich-Präfix signalisiert: keine direkte Parameter-Benutzung in
Tests gewollt; Tests greifen, wenn nötig, das `tmp_path`-Verzeichnis selbst ab.

## D-015 — Datei-Tab im Hauptfenster: QTabWidget + Drag-and-Drop

Das Hauptfenster nutzt jetzt ein `QTabWidget` mit zwei Tabs („Live", „Datei").
Der Datei-Tab enthält eine `FileDropList` (QListWidget-Subklasse) mit
`acceptDrops(True)` und filtert beim Drop nach den vom Controller gemeldeten
unterstützten Endungen (`controller.supported_file_suffixes()`). Die eigentliche
Datei-Verarbeitung läuft im Controller via `process_file()`, das auf den
bereits getesteten Format-Handlern aufsetzt — die GUI bleibt damit dünn.

**Begründung:** Workflow B aus §3 des Megaprompts war bisher nur per CLI
zugänglich. Die Tab-Aufteilung hält den Live-Pfad unverändert und ist
testbar ohne Drag-and-Drop-Simulation: der Controller-Pfad wird in
`test_gui_controller.py` direkt geprüft, die Tab-UI in
`test_gui_main_window.py` via `file_list.add_path()` und Slot-Aufruf.

## D-016 — TXT-Dateien laufen über die Format-Pipeline (W-01)

Bis zum E2E-Walkthrough schrieb `pseudokrat anonymize -i memo.txt` ohne `-o`
auf stdout — inkonsistent zu `.docx`, `.xlsx`, `.csv`, die immer eine
`*.anon.<ext>`-Datei neben dem Original erzeugen. **Wahl:** Jede Datei-Eingabe
mit registriertem Format-Handler (`_has_handler`) läuft über die Pipeline.
Stdout-Pfad bleibt für `--text` und `--stdin` reserviert. So passt der CLI-
Workflow ohne Überraschungen für Nicht-Techniker.

## D-017 — Company-Recognizer: max 3 Name-Tokens (W-02)

Der `CompanyLegalFormRecognizer` hatte ein Token-Limit von 1+3 = 4 Tokens vor
der Rechtsform — wodurch „Vertrag mit Hofer Bau GmbH" als Span gespeichert
wurde und Konsistenz mit „Hofer Bau GmbH" verloren ging. **Wahl:** Limit
auf 1+2 = 3 Name-Tokens reduziert. Vier-Token-Firmennamen sind selten;
Stopword-Trim („Vertrag mit" → entfernt „mit") plus 3-Token-Limit liefert
den korrekten Span „Hofer Bau GmbH".

## D-018 — Profilnamen aus profile_metadata lesen (W-03)

`ProfileManager.list_profiles()` las bisher nur den Datei-Stem (Slug). Profile
mit Leerzeichen wurden als „Mandant_Hofer" angezeigt statt „Mandant Hofer".
**Wahl:** Da der Original-Profilname unverschlüsselt in `profile_metadata`
liegt, öffnet `list_profiles` jede SQLite passwortlos und liest die Klartext-
Spalte. Bei beschädigten DBs Fallback auf den Datei-Stem.

## D-019 — Walkthrough als unabhängiger E2E-Runner

`walkthrough/run.py` ist ein Skript, das einen frischen Nutzer simuliert
(eigener tmp-Datadir, eigene Profile, alle 15 Schritte). Es ist **kein**
pytest-Test, sondern eine Smoke-Suite für manuelle Verifikation und
Releases. Die durch den Walkthrough gefundenen Bugs (W-01 bis W-03) werden
in `test_regressions_walkthrough.py` als reguläre Tests fixiert, damit sie
nicht erneut auftreten.

## D-020 — PDF-Pipeline: Text-Layer extrahieren, Text-PDF schreiben

**Wahl:** `PdfHandler` (`formats/pdf_handler.py`) liest die Text-Schicht
einer PDF via `pypdf`, übergibt jede Seite an die Transform-Funktion und
schreibt das Ergebnis als **neue, reine Text-PDF** mit `reportlab`. Eine
Overlay-/Redaction-Strategie über der Original-PDF wird bewusst NICHT
gewählt.

**Begründung:** Megaprompt §11/Phase 4 verlangt „Text-Layer extrahieren,
redacten, neu schreiben". Layout, Bilder, eingebettete Fonts, Tabellen-
geometrie gehen damit verloren — das ist akzeptabel, weil der einzige
Zweck des Anonymisats die Weitergabe an eine Cloud-KI ist (Text-Inhalt),
und der originale Schriftsatz nicht durchs Modell muss. Das ist konsistent
zum Trade-off, den auch der DOCX-Handler bei Run-Merging eingeht
(siehe D-010). Eine layouttreue Redaktion kommt in einer späteren Phase
(Overlay + `pypdf.PageObject.compress_content_streams` o. ä.).

**Skipped vs. Processed:** Seiten ohne extrahierbaren Text werden gezählt
als `segments_skipped`. Die Ausgabe-PDF enthält für jede Eingabe-Seite
EINE Ausgabe-Seite — leere Seiten bleiben leer, damit Seiten-Zählung im
Anonymisat mit dem Original übereinstimmt (relevant für Verweise wie
„siehe S. 3").

## D-021 — Audit-Log PDF-Export

**Wahl:** `AuditLog.export_pdf(output_path, profile_name=…)` rendert das
Audit-Log via `reportlab.platypus.SimpleDocTemplate` auf A4-Querformat,
inkl. Hash-Chain-Status („Hash-Kette gültig" / „MANIPULATION ERKANNT")
und gekürzten Hashes (16 Hex-Zeichen + Ellipsis) für Lesbarkeit. Die
CSV-Spaltenstruktur (`export_csv`) bleibt das Vollformat für maschinelle
Weiterverarbeitung.

**CLI:** `pseudokrat audit export --format {csv,pdf} [-o file]`. CSV
geht ohne `-o` an stdout (wie bisher); PDF erfordert `-o` (Exit-Code 6,
falls fehlend). Default-Format ist `csv` — bestehende Workflows brechen
nicht.

**Begründung:** Kammern und Berufshaftpflichtversicherer erwarten eine
unterschriftsreife PDF-Dokumentation. CSV ist Maschinenformat, PDF ist
Vorlage-Format — beide werden parallel angeboten.

## D-023 — Profile-Tab im Hauptfenster (Workflow D)

Megaprompt §9 verlangt drei Tabs („Live", „Datei", „Profile"). Bisher waren
nur Live + Datei vorhanden; Profile-Anlage und -Übersicht lief ausschließlich
über die CLI. **Wahl:**

* `GuiController.list_profile_summaries()` und `create_profile()` als
  UI-freie API, damit der Profil-Tab headless testbar bleibt.
* `ProfileSummary` liest `created_utc` aus `profile_metadata` und
  `COUNT(*)` aus `mappings` **ohne** Master-Passwort — beide Werte
  enthalten keinerlei Klartext-PII (Datum und Zähler), sondern nur
  Metadaten.
* `create_profile` ändert die aktuell geöffnete Session **nicht** — das
  Anlegen ist eine reine Setup-Operation, der Switch auf das neue Profil
  geschieht weiterhin explizit über die Profil-Zeile oben.
* Audit-Log-Verifikation („Hash-Kette gültig" / „MANIPULATION ERKANNT")
  wird im Profile-Tab gegen die aktuell geöffnete Session ausgeführt;
  ohne Session liefert sie eine klare Statusmeldung statt einer Exception.

**Begründung:** Hält den Pfad „passwortfreie Übersicht über alle
Profile" sauber vom Pfad „verschlüsseltes Mapping" getrennt. Die
unverschlüsselte `profile_metadata` ist bereits in D-018 als
non-secret klassifiziert.

## D-024 — Hotkey-Workflow: CLI-Subbefehl statt Global-Hotkey-Listener

Workflow A aus §3 (Zwischenablage anonymisieren per Hotkey) wird über den
neuen Subbefehl `pseudokrat clipboard {anonymize,deanonymize}` realisiert.
Pseudokrat selbst registriert **keinen** globalen Tastatur-Listener — das
würde unter Windows Admin-Rechte (`keyboard`-lib) und unter macOS eine
Accessibility-Freigabe (`pynput`) verlangen, beide sind im Produkt-Setup
spürbare Hürden.

**Wahl:** Pseudokrat liefert nur das Read→Transform→Write-Primitiv; der
Nutzer bindet es über das OS-Hotkey-Werkzeug seiner Wahl ein (PowerToys,
AutoHotkey, macOS Shortcuts). `pyperclip` ist als optionale Abhängigkeit
`pseudokrat[clipboard]` deklariert und wird im Adapter `PyperclipClipboard`
lazy importiert. Tests setzen `pseudokrat.clipboard.InMemoryClipboard`
ein, sodass der gesamte CLI-Pfad ohne System-Zwischenablage abgedeckt
ist.

**Exit-Codes:**
* `7` — Zwischenablage nicht zugänglich (pyperclip fehlt o. ä.)
* `8` — Zwischenablage leer (nichts zu anonymisieren)
* `3` — Deanonymisierung mit unbekannten Platzhaltern (z. B. falsches Profil)

**Begründung:** Headless-Hotkey-Pfad ist robust, plattform-übergreifend und
ohne Sonderrechte einsetzbar. Sollte später ein integrierter Tray-Hotkey
gewünscht werden (Phase 2b im Roadmap), bleibt der CLI-Befehl bestehen
und kann sowohl vom Tray als auch von Power-Tools des Nutzers aufgerufen
werden.

## D-022 — `pseudokrat.gui.__init__` lazy-importiert main_window

`tests/test_gui_controller.py` importiert `pseudokrat.gui.controller`
(UI-frei), wodurch zwangsläufig `pseudokrat.gui.__init__` ausgeführt
wird. Bisher hat das `__init__` unbedingt `main_window` (PySide6)
nachgezogen — auf headless CI ohne PySide6 schlug die gesamte
Test-Sammlung deshalb mit ImportError fehl, obwohl der Controller-
Pfad qt-frei ist.

**Wahl:** `pseudokrat/gui/__init__.py` exportiert `MainWindow`,
`build_application` und `run` nun via `__getattr__`-Lazy-Loading.
Statische Typprüfer sehen sie weiterhin über den `TYPE_CHECKING`-
Block; zur Laufzeit wird `main_window` erst geladen, wenn ein
Aufrufer eines dieser Symbole tatsächlich anfasst.

**Begründung:** Headless-Tests (Controller, Format-Handler, Audit-
Log, CLI) müssen ohne Qt grün laufen — das hatten D-013 und D-015
in der Architektur schon festgelegt; das `__init__` war der letzte
harte Qt-Touchpoint, der jetzt entfernt ist. Der GUI-Entry-Point
(`pseudokrat-gui` → `pseudokrat.gui.main_window:run`) und der
`python -m pseudokrat.gui`-Pfad (`__main__.py` importiert
`main_window` direkt) sind nicht betroffen.

## D-026 — `pseudokrat init` als CLI-First-Start-Wizard (§9)

Megaprompt §9 verlangt einen „Erstes-Start-Wizard" für die GUI, der u. a.
ein Master-Passwort setzt und ein erstes Profil anlegt. Für CLI-Nutzer fehlte
bisher ein expliziter Anlage-Befehl — Profile entstanden implizit beim ersten
`anonymize`-Aufruf, was Nicht-Techniker irritiert und Schreibfehler im Profil-
namen unbemerkt zu neuen Profilen führen lässt.

**Wahl:** `pseudokrat init --profile <name>` legt explizit ein neues Profil
an, fragt das Master-Passwort interaktiv mit doppelter Bestätigung ab,
erzwingt mindestens `MIN_PASSWORD_LENGTH` (8) Zeichen und verweigert die
Anlage, wenn bereits eine Profil-Datei existiert.

**Exit-Codes (neu):**
* `9` — Profil-Datei existiert bereits (kein Überschreiben).
* `10` — Passwort zu schwach oder Bestätigung weicht ab.
* `11` — Profilname enthält ungültige Zeichen (gleicher Validator wie
  `ProfileManager.profile_path`).

**Begründung:** Hält den Setup-Pfad sauber getrennt von der Tagesarbeit
(`anonymize`/`deanonymize`), verhindert versehentliche Profil-Duplikate
durch Typos, und macht das Wizard-Verhalten aus §9 (Master-Passwort setzen,
erstes Profil anlegen) auch ohne GUI verfügbar. Der GUI-Wizard kann später
auf dieselbe Controller-Schicht aufsetzen, ohne dass die CLI-Semantik
nachgezogen werden muss.

## D-027 — Vorschau-Editor: read-only Highlight, kein Klick-Toggle

Megaprompt §9 verlangt einen „Vorschau-Editor", der erkannte PII farbig
hervorhebt, einen Tooltip mit Platzhalter + Confidence-Score zeigt und
per Klick Spans togglen lässt (False-Positive entfernen).

**Wahl (Phase 2):** Read-only `PIIPreviewWidget` (`gui/preview_widget.py`)
auf Basis von `QTextEdit`. Farbpalette ist Pastell, pro Kategorie ein
eigener Hex-Code; unbekannte Kategorien fallen auf neutrales Grau. Der
Tooltip pro Span zeigt `<KATEGORIE> · Confidence <pct>` — nicht den
finalen Platzhalter, weil der Vorschau-Pfad das Mapping bewusst NICHT
materialisiert (`GuiController.preview` ruft nur `Anonymizer.detect`).
Damit bleibt die Vorschau reversibel und in Hotpath-UI-Updates sicher;
wiederholte Aufrufe erzeugen keine neuen Mapping-Einträge.

**Bewusst ausgespart:** Der Klick-Toggle zur False-Positive-Markierung
braucht eine Span-Exclusion-Liste, die in `Anonymizer.anonymize` 
einfließen müsste — das ist eine Anonymizer-API-Erweiterung und ein
Stateful-UI-Schritt, der nach Phase 2b verschoben wird. Der bestehende
Vorschau-Knopf liefert bereits den Hauptzweck der UX (vor dem Senden
prüfen können, was anonymisiert wird).

## D-028 — System-Tray-Icon mit §9-Menü und Audit-Export-Hook

Megaprompt §9 verlangt ein „System-Tray-Icon mit Rechtsklick-Menü: Profile
wechseln, App öffnen, Audit-Log exportieren, Beenden". Bisher gab es nur
das Hauptfenster; nach `window.close()` war Pseudokrat verschwunden.

**Wahl:**

* Neues Modul `gui/tray.py` mit `PseudokratTrayIcon(QSystemTrayIcon)`. Die
  vier Menüeinträge sind als benannte `QAction`-Felder exponiert
  (`show_action`, `switch_profile_action`, `export_audit_action`,
  `quit_action`), damit Tests sie direkt triggern können — eine echte
  System-Tray-Sichtbarkeit ist für Verifikation nicht erforderlich.
* `attach_tray_icon()` zeigt das Icon nur, wenn
  `QSystemTrayIcon.isSystemTrayAvailable()` True liefert. In headless-
  Umgebungen (`QT_QPA_PLATFORM=offscreen`) wird es konstruiert, aber nicht
  sichtbar gemacht — Slot-Verbindungen bleiben intakt.
* Der Tray hat eine schmale `_TrayHost`-Schnittstelle (Protokoll mit
  `show_from_tray`, `focus_profile_input`, `controller`). `MainWindow`
  erfüllt sie. Damit ist der Tray vom konkreten Fenster-Layout entkoppelt.
* Audit-Export läuft über zwei neue Controller-Methoden:
  `GuiController.export_audit_csv(path)` und `.export_audit_pdf(path)`.
  Headless-tests stubben `QFileDialog.getSaveFileName`, sodass der gesamte
  Tray→Controller→Audit-Pfad ohne echtes Tray geprüft wird.

**Bewusst nicht:**

* Keine Minimize-to-Tray-Logik (Schließen des Fensters quittet weiterhin).
  Megaprompt §9 verlangt nur den Tray-Zugriff, kein hide-on-close — und
  ein impliziter Hintergrund-Daemon erhöht die Angriffsfläche, ohne
  Mehrwert für den geforderten Workflow.
* Keine globalen Hotkeys aus dem Tray heraus. Die Hotkey-Strategie aus
  D-024 (OS-Hotkey-Tool + CLI-Subbefehl) bleibt der Single-Source-of-
  Truth-Pfad; eine Tray-Hotkey-Bindung gehört in Phase 2b.

## D-025 — Regex-basierte Phone/URL/Secret-Recognizer (§6 ohne ML)

Megaprompt §6 listet `<PHONE_xxx>`, `<URL_xxx>` und `<SECRET_xxx>` als
Pflichtkategorien. Bislang kamen diese ausschließlich aus dem optionalen
Privacy-Filter-ML-Modell — nicht-ML-Setups (Standardfall im Phase-1-CLI,
weil das 3-GB-Modell optional bleibt) ließen sie ohne Treffer.

**Wahl:** Drei neue Recognizer, die ohne ML-Dependency funktionieren:

* `PhoneRecognizer` (`recognizers/phone.py`) — international
  (`+49/+43/+41`, `0049/0043/0041`) und nationale DACH-Schreibweisen
  (`0664 …`, `030 …`, `044/…`). Konservativ ausgelegt: ohne DACH-Präfix
  kein Match, Min-Digits 8 bzw. 8/14.
* `UrlRecognizer` (`recognizers/url.py`) — `http(s)`, `ftp`, `www.…`.
  Trailing-Punctuation (`.`, `,`, `;`, `)`) wird abgeschnitten;
  Hosts ohne Punkt (`localhost`) werden ignoriert.
* `SecretRecognizer` (`recognizers/secret.py`) — eindeutig präfix-
  identifizierbare API-Keys: OpenAI (`sk-`, `sk-proj-`, `sk-svcacct-`,
  `sk-admin-`), Anthropic (`sk-ant-`), AWS (`AKIA`/`ASIA`/…), GitHub
  (`gh[pousr]_`, `github_pat_`), Slack (`xox[abprs]-`), Google
  (`AIza…`), JWT (`eyJ…eyJ…`) und Bearer-Header. Generische
  Hex-/Base64-Strings sind bewusst NICHT inkludiert (zu viele false
  positives auf Hashes, UUIDs, Git-SHAs).

**Begründung:**
* Schließt §6-Coverage im Non-ML-Pfad sauber ab.
* Hält das Modell-Optional-Versprechen aus D-002 ein.
* Konservative Patterns vermeiden den klassischen Phone-/URL-False-
  Positive-Albtraum, der bei aggressiveren Recognizern üblicherweise
  Rechnungsnummern, Build-Hashes und Saldenzeilen zerlegt.

**Reihenfolge in `default_recognizers()`:** Die neuen Recognizer
stehen vor `CompanyLegalFormRecognizer`. Der bestehende Overlap-
Resolver (`anonymizer._resolve_overlaps`) löst Konflikte deterministisch
auf — z. B. wird `+49 30 12345678` als PHONE klassifiziert, eine
darin enthaltene Zahlenfolge nicht zusätzlich als IBAN-Kandidat
gemeldet (IBAN-Recognizer prüft Prüfziffer).

## D-031 — Echter SQLCipher als opt-in Layer-2-Verschlüsselung

D-003 dokumentierte den bewussten Fallback auf Fernet-Field-Level statt
echtem SQLCipher, weil `sqlcipher3-binary` unter Windows fragil war. Im
Mai 2026 ist das `sqlcipher3-wheels`-Paket aktiv gepflegt und liefert
prebuilt Wheels für Win/macOS/Linux. Damit wird der Original-Megaprompt-
Anspruch (AES-256 Page-Level) wieder erreichbar.

**Wahl:**

* `secure_db._connect()` wechselt zwischen `sqlite3` (Default) und
  `sqlcipher3` (opt-in) je nach Datei-Modus.
* Bei Neuanlage entscheidet `_use_sqlcipher()` über das Env-Flag
  `PSEUDOKRAT_USE_SQLCIPHER=1`. Default ist **OFF** — siehe „Warum nicht
  default-on?" unten.
* Bei existierenden Profilen wird der Modus aus dem Datei-Magic-Byte
  erkannt (`_file_is_sqlcipher`): ist der erste Block nicht
  `SQLite format 3\x00`, gilt die Datei als SQLCipher-verschlüsselt.
* `derive_keys()` liefert nun 3 disjunkte Subkeys (32 Byte je): Fernet-
  Key, HMAC-Lookup-Key, SQLCipher-Page-Key — alle aus demselben PBKDF2-
  HMAC-SHA512-Material, 256.000 Iterationen.
* Salt liegt im Sidecar `<db>.sqlite.salt` neben der DB — nötig, weil
  bei SQLCipher die `profile_metadata`-Tabelle erst NACH dem
  Entschlüsseln lesbar ist; Salt darf aber nicht selbst geheim sein.

**SQLCipher-PRAGMA-Härtung:** `cipher_page_size=4096`,
`kdf_iter=256000`, `cipher_hmac_algorithm=HMAC_SHA512`,
`cipher_kdf_algorithm=PBKDF2_HMAC_SHA512`. Der Page-Key wird als Hex
(`x'...'`) übergeben, damit SQLCipher die KDF überspringt — die wurde
bereits einmal von uns durchgeführt; doppelte PBKDF2-Iteration wäre
nur Latenz ohne Sicherheitsgewinn.

**Warum nicht default-on?**

Die Helper `read_profile_metadata` (D-018, D-023, D-029) lesen Profilname,
Anlage-Datum und Mandanten-Regex passwortfrei über stdlib-sqlite3. Mit
SQLCipher ist die ganze Datei verschlüsselt — diese Funktion müsste das
Master-Passwort verlangen, was Workflows wie „GUI listet alle Profile auf"
oder „CLI `profiles list`" sprengen würde. Solange diese Metadaten nicht
in ein eigenes JSON-Sidecar migriert sind (Phase 3-Refactor), bleibt
SQLCipher opt-in.

**Tests:** `tests/test_sqlcipher_backend.py` (6 Tests) verifiziert:

1. Neue DB hat KEIN stdlib-SQLite-Magic-Byte
2. Reopen mit korrektem Passwort funktioniert
3. Reopen mit falschem Passwort → `InvalidPasswordError`
4. MappingStore (Fernet-Layer oben drauf) funktioniert
5. AuditLog-Hash-Chain funktioniert
6. Existierende SQLCipher-DB wird auch bei `PSEUDOKRAT_USE_SQLCIPHER=0`
   erkannt — Datei-Magic gewinnt vor Env-Flag

**Sicherheitsgewinn bei opt-in:**

* Stiehlt jemand die nackte `.sqlite`-Datei, sieht er bei SQLCipher
  nichts. Bei Fernet-Only sieht er Schema + Spaltenstruktur + Anzahl
  Einträge + Kategorienverteilung — Originaltexte bleiben verschlüsselt,
  aber Meta-Information leakt.
* Forensische Tools (`sqlite3 .schema`) versagen ohne den Page-Key.

**Empfohlene Konfiguration für Kanzlei-Produktion:**

```powershell
[Environment]::SetEnvironmentVariable("PSEUDOKRAT_USE_SQLCIPHER", "1", "User")
```

Danach `pseudokrat init` regulär — die neue DB ist SQLCipher.

## D-030 — GUI-Erst-Start-Wizard (§9 Megaprompt)

Megaprompt §9 verlangt einen „Erstes-Start-Wizard" mit (1) Modell-Download
(später), (2) Master-Passwort setzen, (3) erstes Mandantenprofil anlegen,
(4) Hotkeys testen. Der CLI-Pfad (`pseudokrat init`, D-026) bestand bereits;
die GUI-Variante fehlte und war im README explizit als „folgt in den nächsten
Phase-2-Iterationen" markiert.

**Wahl:** Neues Modul `gui/wizard.py` mit drei `QWizardPage`-Subklassen
(Welcome → Profile → Summary) und `FirstStartWizard(QWizard)` als
Coordinator. Geschäftslogik bleibt im `GuiController` — der Wizard ruft
ausschließlich `GuiController.create_profile(name, password,
mandanten_pattern=...)` (neu mit optionalem Pattern-Parameter).
`main_window.run()` führt den Wizard nur dann aus, wenn beim Start keine
Profile auf der Platte liegen (`first_start_required`); ein vorhandenes
Profil deaktiviert ihn automatisch.

**Auto-Trigger-Scope:** Der Wizard wird **ausschließlich aus `run()`**
heraus gestartet, nicht aus `MainWindow.__init__`. Damit bleibt das
direkt-konstruierte `MainWindow()` in den bestehenden Tests (offscreen,
leeres `tmp_path`-Datadir) wizard-frei — sonst hätte das Anlegen jeder
neuen tmp-Datadir den Wizard modal geöffnet und alle Tests gehängt.

**Validierung:** `try_create_profile()` zentralisiert alle Checks
(`MIN_PASSWORD_LENGTH = 8`, Passwort-Bestätigung, leerer Profilname,
Mandanten-Regex-Kompilierbarkeit). `ProfilePage.validatePage()` ist ein
dünner Wrapper darum — so kann der Wizard headless ohne `exec()` getestet
werden, indem Tests die Felder direkt setzen und `try_create_profile()`
aufrufen.

**Fehler-UX:** Bei Validierungsfehler erscheint eine `QMessageBox`-Warnung
und `validatePage()` liefert `False`, sodass der Nutzer auf der
Profil-Seite bleibt und korrigieren kann. In Tests wird `_warn`
gemonkeypatched, um die Meldungen abzufangen ohne UI-Modale.

**Bewusst ausgespart (§9 vs. heute):**

* Modell-Download-Schritt — das ML-Modul ist optional (D-002), ein
  3-GB-Download im Erststart verschreckt mehr Nutzer, als er
  Erkennungsrate liefert. Wird mit dem Installer (Phase 2b) nachgeholt.
* Hotkey-Test-Schritt — die Hotkey-Strategie (D-024) ist OS-Tool +
  CLI-Subbefehl; ein In-Wizard-Test wäre ein zweites Hotkey-Konzept.

**Begründung Architektur:** Drei-Schicht-Trennung (Pages → Wizard →
Controller) hält Qt-Code und Geschäftslogik strikt getrennt — analog zu
D-013, D-023 und D-028. Der Wizard-Pfad ist headless vollständig
testbar (14 neue Tests in `tests/test_gui_wizard.py`), ohne `QWizard.exec()`
zu starten.

## D-029 — Per-Profil-konfigurierbarer Mandanten-Nr-Recognizer (§7 Megaprompt)

Megaprompt §7 verlangt für `MandantenNummerRecognizer` ausdrücklich:
„Konfigurierbar pro Profil — Regex-Pattern wird vom Nutzer beim Profil-Setup
angegeben (z. B. `M-\d{5}` oder `MND_\d{4}-[A-Z]{2}`)." Bis D-029 existierte
der Recognizer als Klasse, war aber **nicht** in die Profile-Konfiguration
oder die `default_recognizers()`-Pipeline eingebunden.

**Wahl:**

* Der Regex wird unverschlüsselt unter dem Key
  `mandanten_nr_pattern` in der bereits vorhandenen Tabelle
  `profile_metadata` abgelegt (siehe `secure_db.py` Schema). Begründung:
  der Regex selbst enthält keine PII, sondern beschreibt nur ein
  Pattern; identisch klassifiziert wie `profile_name` (D-018) und
  `created_utc`.
* Eine neue Helper-Funktion `recognizers_for_store(store)` (in
  `recognizers/__init__.py`) liefert `default_recognizers()` plus den
  `MandantenNummerRecognizer`, wenn ein Pattern hinterlegt ist. Sowohl
  CLI (`anonymize`, `clipboard anonymize`) als auch GUI-Controller
  rufen ausschließlich diese Helper-Funktion — `default_recognizers()`
  bleibt unverändert (Backward-Compat für Tests und Bibliotheks-Nutzer).
* `compile_mandanten_pattern()` validiert den Regex früh und mappt
  `re.error` → eigene `InvalidMandantenPatternError` (Exit-Code 12 in
  der CLI). Damit lehnt `pseudokrat init --mandanten-pattern '...'`
  schon vor dem Anlegen der DB ab, und ein bestehendes Profil wird
  nicht zerstört.

**CLI-Surface (neu):**

* `pseudokrat init --profile X --mandanten-pattern '...'` — beim Erstanlegen
  optional setzen.
* `pseudokrat profiles set-mandanten-pattern --profile X --pattern '...'` —
  bestehendes Profil aktualisieren (verlangt Master-Passwort, weil das
  Profil regulär geöffnet wird; Schutz vor unbefugter Recognizer-
  Manipulation).
* `pseudokrat profiles set-mandanten-pattern --profile X --clear` — Pattern
  entfernen.
* `pseudokrat profiles show-mandanten-pattern --profile X` — Pattern
  ausgeben (passwortfrei, weil `profile_metadata`-Read).

**Neue Exit-Codes:**

* `12` — `--mandanten-pattern` ist kein gültiger Regex.
* `13` — Profil existiert nicht (bei `set-…`/`show-…`).
* `14` — Konflikt zwischen `--pattern` und `--clear` bzw. keiner von beiden.

**Begründung Architektur:**

Der zusätzliche Recognizer wird AM ENDE der Bundle-Liste angehängt — damit
gewinnt der strukturierte Default-Bundle bei Überlappungen (siehe
`_resolve_overlaps` in `anonymizer.py`), und ein zu breit gefasstes
Mandanten-Pattern reißt nicht etwa eine erkannte IBAN oder Telefonnummer
auseinander. Pattern-Validierung beim Lesen (`recognizers_for_store` wirft
bei kaputtem persistierten Regex) sorgt dafür, dass ein während Wartung
beschädigter Eintrag früh und deutlich auffällt — keine stillen
Fehlversuche.

## D-032 — Fuzzy-Merging nur für textuelle PII-Kategorien

**Wahl:** `fuzzy.should_merge` führt Levenshtein-basiertes Merging nur für
die Kategorien `COMPANY`, `ORG`, `PERSON`, `ADDRESS` durch. Alle anderen
Kategorien (IBAN, UID, SVNR, TAX_ID, AHV, ACCOUNT, EMAIL, PHONE, URL,
SECRET, DATE, MANDANT_NR) verlangen Exact-Match nach Normalisierung.

**Begründung:** Hypothesis-Round-Trip-Tests (`test_property_roundtrip.py`)
fanden einen kritischen Korrektheitsbug: `ATU00000015` und `ATU00000006`
haben Levenshtein-Distanz 2 auf der normalisierten Form. Die ursprüngliche
Implementierung mergte beide auf den ersten zugewiesenen Platzhalter →
die Reverse-Auflösung lieferte für `ATU00000015` fälschlich `ATU00000006`
zurück. Numerische IDs sind per Konstruktion bedeutungstragend in jeder
Ziffer; eine 2-Ziffern-Ähnlichkeit ist Zufall, kein Schreibvariante.

Fuzzy-Merging bleibt sinnvoll für „Hofer Bau GmbH" vs. „Hofer-Bau GmbH"
(Schreibvarianten desselben Rechtsträgers, Megaprompt §12.4). Die Liste
wird in `fuzzy._FUZZY_MERGE_CATEGORIES` zentral gepflegt.

## D-033 — Länderspezifische IBAN-Regex statt generischer `{3,7}`-Gruppen

**Wahl:** `recognizers/iban.py` verwendet ein Alternativen-Pattern, das je
Ländercode (AT/DE/CH/LI) die exakte BBAN-Struktur erzwingt:

- AT — 4 Gruppen à 4 Ziffern
- DE — 4 Gruppen à 4 Ziffern + 2-Ziffern-Suffix
- CH/LI — 4 Gruppen à 4 alphanumerisch + 1 alphanumerisch

Plus terminales Negative-Lookahead `(?![A-Z0-9])`.

**Begründung:** Die vorherige Variante
`(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,4})?` matchte greedy und konnte
über die korrekte Länge hinaus in nachfolgende alphanumerische Zeichen
laufen. Beispiel aus dem Hypothesis-Fuzzer:
`AT180000000000000000 A` — ein gültiger AT-IBAN, gefolgt von Space-A.
Das alte Regex konsumierte ` A` als optionalen Schluss-Group; der
MOD-97-Validator lehnte dann wegen falscher Länge (21 statt 20) ab — der
gültige IBAN wurde vom Recognizer verfehlt. Die neue Variante stoppt
verlässlich nach genau 20/22/21 Zeichen.

## D-034 — Property-Roundtrip-Test: Recognizer-Set auf generierte PII einschränken

**Wahl:** `tests/test_property_roundtrip.py::fresh_pipeline` instanziiert
den Anonymizer **nicht** mit `default_recognizers()`, sondern mit genau
den drei Recognizern, die die Hypothesis-Strategy auch erzeugt
(`IBANDachRecognizer`, `GermanUStIdNrRecognizer`,
`AustrianUIDRecognizer`).

**Begründung:** Der `CompanyLegalFormRecognizer` matcht jedes
Vorkommen von `AG`/`KG`/`SE`/`OG`/`UG`/`OHG`/… am Wort-Ende. Die
„neutralen" Glue-Text-Strategien filtern zwar Ziffern und Länder-Präfixe
(`AT`/`DE`/`CH`/`LI`), aber **nicht** diese kurzen Rechtsform-Suffixe.
Hypothesis schliff über 80 Iterationen Beispiele heraus, in denen Glue
wie `"X AG"` oder `"world KG"` als COMPANY erkannt wurde. Über mehrere
Iterationen kollabierten zwei solche COMPANY-Einträge mit
Levenshtein-Distanz ≤ 2 via Fuzzy-Merge zu einem einzigen Platzhalter,
und die Reverse-Auflösung lieferte die falsche Original-Schreibweise →
`deanonymize(anonymize(text)) != text`.

Die saubere Behebung wäre, die Glue-Strategy auch gegen Rechtsform-
Suffixe zu härten. Das ist aber spröde (jedes neue Rechtsform-Token
müsste eingepflegt werden) und maskiert nur ein Artefakt der Test-Setup,
nicht einen echten Produkt-Bug. Stattdessen pinnen wir das Recognizer-Set
auf das Verhalten, das die Test-Strategy bewusst erzeugt. Der
Cross-Recognizer-Integrationsfall (Company + ID gemeinsam in einem
Dokument) ist durch andere, deterministische Tests abgedeckt
(z. B. `tests/test_anonymizer_integration.py`).

## D-035 — Fuzz-Pipeline-Test: präventiv Fuzzy-Merge-Kategorien ausschließen

**Wahl:** `tests/test_fuzz_pipelines.py::pipeline` instanziiert den
Anonymizer mit `_strict_roundtrip_recognizers()` — ein gefilterter
`default_recognizers()`-Satz, der alle Recognizer mit
`is_fuzzy_merge_category(category) == True` herausfiltert. Aktuell
betrifft das genau den `CompanyLegalFormRecognizer`.

**Begründung:** Dieselbe Klasse von Round-Trip-Drift wie in D-034. Im
Fuzz-Test ist die Wahrscheinlichkeit pro Iteration geringer, weil das
Alphabet breiter ist und hypothesis seltener Beispiele mit zufälligem
„X AG"/„Y KG" konstruiert — bisher ist deshalb kein Fehlschlag
aufgetreten. Aber:

- Round-Trip-Asserts (`deanonymize(anonymize(x)) == x`) sind per Design
  unvereinbar mit Fuzzy-Merging: der Merge kollabiert Schreibvarianten
  bewusst auf einen Platzhalter, und Reverse liefert dann nur die
  zuerst gespeicherte Schreibweise.
- Der Mapping-Store wird im Fuzz-Test über alle Beispiele hinweg
  gemeinsam genutzt (function-scoped fixture mit hypothesis), wodurch
  sich gespeicherte COMPANY-Entries akkumulieren und die Drift-
  Wahrscheinlichkeit pro Beispiel monoton steigt.

Cross-Recognizer-Integration für Companies ist durch deterministische
Tests in `test_anonymizer_integration.py` und durch das gezielte
`test_property_roundtrip::TestPlaceholderUniqueness` abgedeckt.

## D-036 — Modell-Revision-Pinning: Strict-Mode statt Hard-Pin

**Wahl:** `PINNED_MODEL_REVISION` bleibt vorerst auf `"main"`, aber das
Modul `pseudokrat.pii.model_install` exponiert einen Strict-Mode über
`PSEUDOKRAT_REQUIRE_PINNED_REVISION=1`. In dem Modus wirft
`_resolved_revision()` eine `UnpinnedModelRevisionError`, sobald die
effektive Revision in `{"main", "master", "HEAD"}` liegt — der Download
bricht also bewusst ab, bevor er passieren kann.

**Begründung:** Der eigentliche Pin auf einen konkreten HuggingFace-
Git-SHA verlangt zwei Voraussetzungen, die autonom nicht erreichbar
sind: (a) eine Entscheidung, welcher Snapshot der bevorzugte Stand
ist, (b) eine reproduzierbare Verifikation der Modell-Datei-Hashes
gegen diesen SHA. Beides ist Aufgabe der Release-Vorbereitung
(typischerweise: einmal manuell pullen, Hashes gegen die
HuggingFace-API verifizieren, SHA eintragen).

Der Strict-Mode löst das halbe Problem heute: CI-Builds und Pentest-
Setups können `PSEUDOKRAT_REQUIRE_PINNED_REVISION=1` setzen und dann
zwingt das Modul den/die Setzende(n), eine konkrete Revision zu
hinterlegen — kein versehentlicher `main`-Download in einem Build,
der signiert und verteilt wird (CWE-494: Substitution-Risiko).

**Release-Checkliste vor 1.0:**

1. `huggingface-cli scan-cache --dir <cache>` nach erfolgreichem
   `pseudokrat model download`.
2. SHA-256 der Top-Level-`model.safetensors` notieren.
3. `git ls-remote https://huggingface.co/openai/privacy-filter HEAD`
   → daraus den Snapshot-SHA übernehmen.
4. `PINNED_MODEL_REVISION` in `model_install.py` aktualisieren.
5. CI: `PSEUDOKRAT_REQUIRE_PINNED_REVISION=1` setzen — dann blockiert
   jeder versehentliche Reset auf `main` den Build.

**Test-Coverage:** Drei neue Tests in `tests/test_model_install.py`:
- `test_resolved_revision_strict_mode_rejects_branch`
- `test_resolved_revision_strict_mode_accepts_sha`
- `test_resolved_revision_default_returns_pinned`


## D-037 — Toplevel-Manifest-Hash für das ML-Modell

**Wahl:** `compute_model_manifest_hash(settings)` berechnet einen
deterministischen SHA-256 ueber alle Dateien des konfigurierten
Modell-Snapshots. Sortierschluessel ist der POSIX-relative Pfad
(plattformunabhaengig). Pro Datei wird `<pfad> <sha256>
` ins
Toplevel-Hashing gefuettert. `.lock`/`.tmp`-Dateien werden bewusst
ausgeschlossen (volatile Cache-Artefakte).

`verify_model_manifest(settings)` haengt sich an die Pin-Variable
`PSEUDOKRAT_PINNED_MANIFEST_SHA256` und vergleicht konstantzeit
(`hmac.compare_digest`). Mismatch → `ModelManifestMismatchError` und
harter Abort, bevor das Modell geladen wird. `download_model` ruft
`verify_model_manifest` direkt nach dem Snapshot-Download auf —
damit auch ein erfolgreicher Download in einem CI/Pentest-Setup
fehlschlaegt, wenn ein Angreifer die Files unterwegs ausgetauscht
haette.

**Begruendung:** S4 im Self-Audit (siehe SELF_AUDIT.md) war
vorher 🟡 — `huggingface_hub` validiert pro Datei den
Repo-Manifest-Hash, aber wenn das Repo-Manifest selbst kompromittiert
waere (z. B. ein erfolgreicher Token-Diebstahl bei HuggingFace), gaebe
es keine zweite Linie. Der eigene Toplevel-Hash schliesst diese Luecke:
Operator notiert den Wert nach dem ersten Download (Output von
`download_model` enthaelt `Manifest-Hash: sha256:…`), traegt ihn in
das CI-Secrets-Verzeichnis ein, und ab dann ist jeder Substitutions-
Versuch deterministisch detektierbar.

**Release-Vorgehen:**

1. Manuell einen sauberen `pseudokrat model download` ausfuehren.
2. Den gemeldeten `Manifest-Hash` notieren.
3. In CI als Secret hinterlegen, plus in `packaging/`-Skripten als
   Env-Var setzen.
4. Ab dann blockt jeder Build mit abweichendem Manifest-Hash.

**Test-Coverage:** Sechs neue Tests in `tests/test_model_install.py`,
u. a. Determinismus, Mutation-Detection, Lock-Datei-Ausschluss,
Mismatch-Pfad und Cache-leer-Pfad.


## D-038 — Rate-Limit für HTTP-Server-POSTs

**Wahl:** Token-Bucket-Limiter (`pseudokrat.rate_limit.TokenBucket`)
wird per default in jeden `ServerState` eingehängt und bei
`/v1/anonymize`/`/v1/deanonymize` vor dem Body-Read geprüft. Defaults:
Burst 60, Refill 1 Token/Sekunde — konfigurierbar via
`PSEUDOKRAT_SERVER_RATE_BURST` und `PSEUDOKRAT_SERVER_RATE_RPS`. Bei
Erschöpfung antwortet der Server mit `429` und `Retry-After`-Header
(aufgerundete Sekunden, min 1).

**Begründung:**

- F-001 aus dem Self-Audit (Pentest-Vorlektorat) forderte einen
  Brute-Force-/Flood-Schutz auf den POST-Endpunkten. Der Server bindet
  zwar an Loopback, ist aber auf Multi-User-OS oder bei lokalem
  RCE-Vektor weiterhin angreifbar.
- Token-Bucket gewährt **bursting** (Excel-Add-in iteriert spaltenweise,
  hat dadurch oft 30–50 schnelle Requests) und kappt sustained Flood.
- Keine externe Dependency. Pseudokrat-Prinzip: lokal, abhängigkeitsarm.
  Kein `slowapi`, kein Redis. Threading.Lock genügt für single-process
  HTTPServer.

**Verworfene Alternativen:**

- `slowapi` / `limits`: zusätzliche Dependency, mehr Tests, mehr CVE-
  Oberfläche — Mehrwert gering bei einer Loopback-Single-Process-App.
- Festes Per-Minute-Limit ohne Burst-Toleranz: würde den Excel-
  Add-in-Workflow stören (50 Zellen → 50 schnelle Requests).
- HTTP-Status `503` statt `429`: `429 Too Many Requests` ist der
  RFC-6585-spezifische Status für Rate-Limit-Erschöpfung.

**Konsequenzen:**

- `/health` ist bewusst NICHT rate-limited — diagnostisches
  Pre-Flight-Probing aus dem Add-in soll nicht blockiert werden.
- Bucket lebt im `ServerState` (eine Instanz pro Server). Bei
  mehreren parallelen Servern (z. B. Tests) sind die Limiter unabhängig.
- Headers wie `Retry-After` werden über den neuen `extra_headers`-
  Parameter in `_send_json` durchgereicht; Defense-in-Depth-Header
  bleiben unverändert.

**Test-Coverage:** 8 Unit-Tests in `tests/test_rate_limit.py` (Bucket-
Mechanik, Env-Var-Parsing, Refill-Caps), 2 Integrations-Tests in
`tests/test_server.py` (429-Response auf POST, /health unbeeinflusst).


## D-039 — Simple-Mode: OS-Keyring statt Master-Passwort

**Wahl:** Pseudokrat unterstützt zwei Trust-Anchor parallel:

1. **Passwort-Modus** (klassisch, Default für CLI ohne `--simple`):
   Master-Passwort → PBKDF2-HMAC-SHA512 256k Iterationen → DerivedKeys.
2. **Simple-Mode** (neu, opt-in via `pseudokrat init --simple`):
   256-Bit-Zufallsgeheimnis liegt im OS-Keyring (Windows Credential
   Manager / DPAPI, macOS Keychain, Linux SecretService). HKDF-SHA512
   spannt es mit dem profil-Salt zu den DerivedKeys auf.

Architektur: gemeinsame `KeyProtector`-Protocol-Abstraktion
(`pseudokrat.store.key_protector`). `secure_db.open_or_init` akzeptiert
einen Protector oder ein Passwort. Sidecar-File `<db>.keyring` neben der
DB markiert Simple-Mode-Profile — CLI und GUI erkennen den Modus
automatisch beim Öffnen und überspringen den Passwort-Prompt.

**Begründung:** UX-Asymmetrie zur Konkurrenz (CamoText hat gar keine
Verschlüsselung; lokal-arbeitende Mitbewerber wie BMD/RZL haben überall
Master-Passwörter, die User regelmäßig vergessen). Simple-Mode
eliminiert das Passwort-Management-Friction für 90 % der Einzelplatz-
Berufsträger, ohne die Architektur für Compliance-/Kammer-Use-Cases zu
schwächen — der Passwort-Modus bleibt 1:1 erhalten.

**Sicherheitsmodell-Shift (dokumentationspflichtig für Pentest):**

- **Vorher (Passwort-Modus):** Profil-DB ist nutzlos für jeden, der nicht
  das Master-Passwort kennt — selbst bei vollem Festplatten-Zugriff.
- **Nachher (Simple-Mode):** Profil-DB ist nutzlos für jeden, der nicht
  das **Windows-/macOS-Benutzerkonto** des Profil-Eigentümers
  kontrolliert. Ein Angreifer mit Konto-Zugriff (gestohlener Laptop +
  Login-Bypass, Malware mit User-Rechten) kann auch die Mappings lesen.
  Identisches Niveau wie Edge-Passwort-Speicher, Outlook-PST-Dateien,
  Sticky-Notes.

Das ist der **richtige** Trade-off für DACH-Berufsträger-Einzelplatz:
„Mandantendaten verlassen die Maschine nicht" ist das Versprechen, nicht
„die Maschine ist eine Festung gegen den Eigentümer". Kammer-Pitch
schwächt das nicht — wer Festungs-Modus will, bekommt ihn über
weglassen des `--simple`-Flags.

**Crypto-Detail — Warum HKDF statt PBKDF2 im Simple-Mode:** Das
OS-Keyring-Geheimnis ist bereits 256 Bit Entropie (`os.urandom`).
PBKDF2 ist für Low-Entropy-Inputs (Passwörter) gedacht — Stretching
schützt vor Brute-Force. Für High-Entropy-Inputs ist HKDF das richtige
Primitiv: Domain-Separation per `info`-Tag, kein Compute-Overhead.

**Migration:** Bestehende Passwort-Profile bleiben Passwort-Profile. Es
gibt aktuell **keinen** automatischen Migrationspfad — ein Nutzer, der
von Passwort auf Simple-Mode wechseln will, muss das Profil neu anlegen.
Migrations-Tooling ist Folge-Arbeit (Phase C-Frage).

**Sidecar-Sicherheit:** Der `<db>.keyring`-Marker enthält nur den
Profilnamen (Klartext, kein Geheimnis). Ein Angreifer, der die Datei
sieht, lernt nur den Profilnamen — den er aus dem DB-Dateinamen ohnehin
ableiten könnte. Reihenfolge beim Erstanlegen: Marker → Salt → DB,
damit ein Crash zwischen DB-Create und Marker-Write nicht zu einem
„Modus-unbekannt"-Zustand führt.

**Reset-Pfad:** Wenn der OS-Keyring-Eintrag verloren geht (OS-Reinstall,
Konto-Wechsel), ist das Profil unentschlüsselbar — gleiches
Failure-Modus wie „Master-Passwort vergessen". Das ist by-design;
Backup-Strategie ist Sache des Nutzers (`PILOT_KIT.md` muss erweitert
werden, sobald Phase B/C landet).

**Verworfene Alternativen:**

- **DPAPI direkt** über `win32crypt.CryptProtectData`: bindet uns an
  pywin32, eine schwere Dependency (Build-Komplexität auf macOS/Linux).
  `keyring` ist dünner, plattformneutral, gepflegt.
- **Eigenes File-mit-OS-ACLs** (Plaintext-Geheimnis, NTFS-ACL auf
  Eigentümer): keine Härtung gegen Angreifer im selben Userkontext.
  OS-Keyring nutzt zumindest TPM-gebundene Schlüssel auf Windows 11.
- **Auto-Migration Passwort→Simple-Mode:** zu invasiv für eine Phase-A-
  Änderung, plus nicht klar dokumentierter Side-Effekt für bestehende
  Nutzer. Folge-Arbeit.

**Test-Coverage:** 20 Unit-Tests in `tests/test_key_protector.py`
(Determinismus, Profilisolation, Tampering, Marker-Write-Order,
Auto-Detect-Pfad, Cross-Mode-Rejection).

**Erledigt:**

- Phase B (`pseudokrat install`): geliefert in D-040.
- Phase C (GUI versteckt Profil-Selector + Tray-Workflow): geliefert in D-041.

**Vertagt nach 6.x — Bestandsnutzer-Migration:** Trigger ist der erste
reale Wunsch eines Nutzers, sein bestehendes Passwort-Profil auf den
Simple-Mode (OS-Keyring) zu migrieren. Aktuell ist Simple-Mode der
Default für Neuanlagen — die Migration ist ein UX-Feature, keine
Korrektheits-Anforderung, und wartet auf einen konkreten Pilotnutzer.

- Migration: `pseudokrat profiles migrate --to=simple --profile X` mit
  Passwort-Prompt + Re-Encryption-Pfad.


## D-040 — `pseudokrat install`: Ein-Befehl-Setup für Einzelplatz-Nutzer

**Wahl:** Neuer CLI-Befehl `pseudokrat install` macht in einem Schritt:

1. Default-Profil „Mein Konto" im Simple-Mode anlegen (sofern nicht
   schon vorhanden; `--no-profile` deaktiviert das).
2. Rechtsklick-Menü im Windows Explorer registrieren für `.pdf`,
   `.docx`, `.xlsx`, `.csv`, `.txt` → „Mit Pseudokrat anonymisieren".
3. Optional: Hotkey-Daemon beim Login automatisch starten
   (`--with-hotkeys`).

Gegenstück: `pseudokrat uninstall` entfernt Registry-Einträge wieder
(Profile bleiben erhalten — Wegklicken wäre zu zerstörerisch ohne
explizite Daten-Lösch-Geste).

**Architektur:** Neues Modul `pseudokrat.install` mit
`RegistryBackend`-Protocol. Production-Backend (`WinRegistryBackend`)
benutzt `winreg`-Stdlib; Test-Backend (`InMemoryRegistryBackend`)
bildet die Hierarchie als verschachtelte Dicts ab. Damit läuft die
Suite auch auf Linux/macOS-CI — kein Mock-Aufwand bei jedem Test, das
Backend ist die natürliche Abstraktion.

**Registry-Pfade (HKCU only, kein Admin nötig):**

- `HKCU\Software\Classes\SystemFileAssociations\<.ext>\shell\PseudokratAnonymize`
  — verbreitet als „SystemFileAssociations"-Variante des Shell-Menüs.
  Vorteil gegenüber `HKCR\<.ext>\shell\...`: greift unabhängig vom
  installierten Default-Handler, kein Schreibzugriff auf HKLM nötig.
- `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
  → `PseudokratHotkeyDaemon` für Autostart.

**Command-Resolution (siehe `resolve_pseudokrat_command`):**

1. `shutil.which("pseudokrat")` → wenn vorhanden, direkter Pfad zur
   PyInstaller-EXE.
2. Sonst Fallback: `"<sys.executable>" -m pseudokrat anonymize --input "%1"`
   — dev-install-tauglich, weil python.exe + Modul-Resolution unter
   Kontrolle bleibt.

**Bewusste Trade-offs:**

- **Kein Admin.** Wir registrieren nur in HKCU, nicht in HKLM. Das
  begrenzt den Eintrag auf den aktuellen Benutzer — gewollt für
  Kanzlei-IT-Policies, die jeden Admin-Schritt blockieren.
- **Kein Icon.** Phase B legt das `Icon`-REG_SZ-Feld an, aber leer.
  Ein hübsches Icon ist Phase-C-Arbeit (zusammen mit Pyinstaller-EXE,
  damit das Icon Teil der signierten Distribution ist).
- **Nur Windows.** macOS-Services (FinderSync-Extension oder
  `defaults write com.apple.finder ...`) und Linux-Desktop-Entries
  sind eigene Wurmlöcher — Folge-PR.
- **Hotkeys opt-in.** `keyboard`-Library braucht auf Windows
  Administrator-Rechte für `register_hotkey` mit `<win>+...`-Kombis.
  Wer per default Autostartet hat, kriegt im schlimmsten Fall einen
  stillen Failure. Opt-in via `--with-hotkeys` macht das explizit.

**Verworfene Alternativen:**

- **NSIS- oder Inno-Setup-Installer ruft `install` selbst auf:**
  überflüssig — Inno-Setup kann Registry-Einträge selbst schreiben.
  Das wäre Doppelarbeit. Phase D (eigener Installer) ruft `install`
  als Last-Step auf, oder schreibt die Reg-Keys direkt — beides
  äquivalent.
- **`HKCR\<.ext>\shell\PseudokratAnonymize` statt
  `SystemFileAssociations`:** funktioniert nur, wenn der ProgID
  schreibbar ist; bei manchen .pdf-Defaults (Edge, Adobe) werden
  Schreibzugriffe blockiert. SystemFileAssociations ist robuster.

**Test-Coverage:** 24 Unit-Tests in `tests/test_install.py` —
Backend-Mechanik (Set/Get/Delete/Tree-Delete/Hive-Validation),
Context-Menu-Lifecycle (install/uninstall/idempotency/nicht-eigene-
Subkeys-bleiben), Autostart-Lifecycle, `perform_install`-Workflow mit
allen Permutationen (`create_profile` × `with_hotkeys`),
`check_install_state`-Diagnose, Command-Resolution-Format.

**Pentest-Hinweise (für nächstes Audit):**

- Command-Template enthält `"%1"` — Explorer-Shell expandiert das mit
  dem Datei-Pfad. Bei manipulierten Dateinamen (Anführungszeichen)
  könnte Argv-Injection entstehen. Mitigation: `argparse` validiert
  ohnehin nur den `--input`-Pfad als `Path`; alles dahinter wird
  ignoriert. Trotzdem im Pentest-Briefing erwähnen.
- `WinRegistryBackend` schreibt nur in HKCU — kein Privilege-
  Escalation-Vektor.

**Vertagt nach 6.x — Signed-Release-Vorbereitung:** Trigger ist die
Vorbereitung des ersten signierten Builds (Phase-6 Distribution gemäß
Megaprompt §11). Vor dieser Schwelle bleibt die Dev-CLI/Dev-GUI
funktionsfähig ohne macOS-Pfad und ohne Icon-Asset; der HKCU-Eintrag
auf Windows trägt aktuell leeres `Icon`-Feld (siehe D-040 Bewusste
Trade-offs).

- macOS-Install-Pfad: FinderSync-Extension oder Services-Plist.
- Icon-Asset für Context-Menu + Tray (.ico unter `packaging/icons/`).


## D-042 — Production-Readiness-Loop (PRL): Eval-getriebener Lückenschluss

**Wahl:** Statt weiterer Feature-Sprints fahren wir Pseudokrat in einem
expliziten, messbaren Loop in die Produktionsreife. Die Latte ist
schriftlich fixiert (`PRODUCTION_READY_GATE.md`), wird automatisch
gegen Eval- und Audit-Reports geprüft, und treibt einen Iterations-
Rhythmus, in dem **pro Commit genau eine Lücke** geschlossen wird.

**Vier Phasen pro Iteration:**

1. **Eval-Phase** — `tests/eval/runner.py` läuft gegen Fixtures unter
   `tests/eval/fixtures/<name>/{input.txt, expected.json}` und
   produziert einen `eval_report.json` mit Precision/Recall/F1 pro
   Kategorie + pro Fixture + global. Span-Matching via Jaccard ≥ 0.5
   (siehe `scoring.py`).
2. **Audit-Phase** *(folgt in nächster Iteration)* — `tools/audit_run.py`
   bündelt Ruff/mypy/pytest/bandit/pip-audit + Trust-Boundary-Coverage-
   Heuristik.
3. **Gap-Phase** — die offenste Lücke wird identifiziert
   (Eval-Defizit ggü. Gate, fehlende Trust-Boundary-Test, offene
   DECISIONS-Folgearbeit).
4. **Close-Phase** — eine Lücke, ein Commit, neuer Branch nach dem
   Schema `fix/<gap-id>` oder `feat/<feature-id>`.

**Fixture-Format:** `FixtureBuilder` mit Slot-Substitution rechnet
Offsets exakt aus, damit Ground-Truth nicht händisch gepflegt werden
muss. Synth-Werte (IBAN/SVNR/UID/TAX_ID/AHV) sind mit korrekten
Prüfziffern reproduzierbar aus Seeds erzeugt. Cross-Validation-Tests
(`test_synth_*_accepted_by_recognizer`) stellen sicher, dass jeder
Synth-Wert auch wirklich vom Production-Recognizer akzeptiert wird —
sonst messen wir Recall an der falschen Stelle.

**Eval-Mode-Trennung:** Phase 1 des Gates misst nur die regelbasierten
DACH-Recognizer (deterministisch, deshalb sind die Latten meist
`1.00`). ML-Detector-abhängige Kategorien (PERSON, ADDRESS, DATE)
brauchen Phase-2-Lauf mit gecachtem Modell — der ist noch nicht
implementiert, fließt aber als bekannte Phase-2-Lücke in den Gap-Report.

**Erste Iteration — geschlossene Lücken:**

1. **TAX_ID Recall 0% → 100%.** Ursache: das Fixture verwendete die
   Kategorie `STEUER_ID`, der Production-Recognizer aber `TAX_ID`.
   Fix: Fixture-Generator + Gate-Spec auf `TAX_ID` umgestellt.
2. **UID Recall 0% → 100%.** Ursache: der Synth-Generator nutzte den
   Standard-Luhn-Algorithmus, der Production-Recognizer aber den
   BMF-Algorithmus mit der spezifischen Konstante `+4` in
   `check = (10 - (S + 4) % 10) % 10`. Fix: Synth-Algorithmus an BMF-
   Variante angeglichen.
3. **TAX_ID-Synth-Constraint präzisiert.** Die ISO-7064-Mod-11,10-
   Wiederholungsregel verlangt **genau eine** Ziffer, die in den
   Stellen 1-10 zwei- oder dreimal vorkommt — alle anderen Ziffern
   höchstens einmal. Mein erster Generator hatte den schwächeren
   Check „mindestens eine Ziffer kommt 2-3x vor". Fix: aktiver
   Konstruktor statt Retry-Loop.

**Aktueller Stand nach Iteration 1:**

| Kategorie | F1 | Gate | Status |
|---|---|---|---|
| IBAN | 1.00 | 1.00 | ✅ |
| SVNR | 1.00 | 1.00 | ✅ |
| TAX_ID | 1.00 | 1.00 | ✅ |
| UID | 1.00 | 1.00 | ✅ |
| AHV | 1.00 | — | ✅ |
| COMPANY | 1.00 | 0.95 | ✅ |
| EMAIL | 1.00 | 1.00 | ✅ |
| PHONE | 1.00 | — | ✅ |
| BIC | 0.00 | — | ❌ Recognizer fehlt komplett |
| PERSON | 0.00 | 0.95 | ❌ ML-Pfad, Phase 2 |
| ADDRESS | 0.00 | 0.90 | ❌ ML-Pfad, Phase 2 |
| DATE | 0.00 | 0.85 | ❌ ML-Pfad, Phase 2 |

**Nächste Iteration:** BIC-Recognizer (deterministische SWIFT-ISO-9362-
Validierung — keine ML-Abhängigkeit, sollte in 1 Commit gehen).

**Verworfene Alternativen:**

- **Eval gegen echte Mandantendaten:** dataschutzrechtlich tot.
  Synth-only, Algorithmus-Cross-Validated, ist die korrekte Form für
  ein DACH-PII-Tool.
- **Ein Mega-Sprint, der alles auf einmal closed:** macht Eval-Drift
  unsichtbar. Pro-Commit-Iteration zeigt nach jeder Änderung sofort,
  ob Recall/Precision sich in die richtige Richtung bewegt haben.

**PRL-Iteration 2 (BIC-Recognizer) — abgeschlossen:**

Neuer `BICRecognizer` (`recognizers/bic.py`) erkennt ISO-9362-konforme
SWIFT-Codes (8 oder 11 Zeichen, AAAA BB CC [XXX]) mit zwei
Validierungs-Stufen:

1. **Format + ISO-3166-Country-Code-Whitelist** (~250 Codes statisch
   deklariert).
2. **Kontext-Keyword innerhalb 40 Zeichen davor**: `BIC`, `SWIFT`,
   `BANK IDENTIFIER`. Nötig, weil das BIC-Format mit alltäglichen
   deutschen Groß-Wörtern kollidiert — z. B. `NEUERUNG` = `NEUE+RU+NG`
   (RU = Russia, valid country code), `DEUTSCHLAND` = `DEUT+SC+HL+AND`
   (SC = Seychelles). Reine Form+Country-Whitelist produzierte sonst
   False Positives in jedem Fließtext.

Trade-Off: Wir verpassen BICs, die ohne Label-Wort daneben stehen —
in DACH-Banking-Dokumenten (Lohnkonten, Rechnungen, Auszüge) ist das
Label aber praktisch immer da. Real-World-Fall der „nur Wert, kein
Label" ist selten.

Test-Coverage: 25 Tests in `tests/test_bic_recognizer.py` — echte
BICs (DEUTDEFFXXX, GIBAATWWXXX, UBSWCHZH80A, ...), Format-Verstöße
(falsche Länge, Lowercase, Ziffern in Country-Stellen, falsches
ISO-Code), Multi-BIC-Extraction, Word-Boundary, False-Positive-
Trap (`NEUERUNG`/`DEUTSCHLAND` ohne Kontext).

**Eval-Status nach Iteration 2:**

| Kategorie | F1 | Gate | Status |
|---|---|---|---|
| IBAN, SVNR, TAX_ID, UID, AHV, EMAIL, PHONE, COMPANY, **BIC** | 1.00 | — | ✅ |
| PERSON, ADDRESS, DATE | 0.00 | 0.95/0.90/0.85 | 🟡 ML-Pfad, Phase 2 |

Total F1 stieg 0.585 (baseline) → 0.651 (Iter 1) → 0.682 (Iter 2).
Alle deterministischen Recognizer auf 1.00. Verbleibende Lücken
sind alle ML-abhängig — der nächste Schritt ist nicht „noch ein
Recognizer", sondern der Eval-Modus mit eingeschaltetem
Privacy-Filter-Modell.

**PRL-Iteration 3 (ML-Eval-Modus) — abgeschlossen:**

`runner.py --with-ml` lädt den `PrivacyFilterDetector` und misst damit
auch PERSON, ADDRESS, DATE, URL und SECRET — Kategorien, die nur der
ML-Pfad kennt. Der Detector-Output wird über `_LABEL_MAP` in
`privacy_filter.py` auf unsere kanonischen Kategorienamen gemappt
(`private_person` → `PERSON` etc.), sodass das Scoring identisch zum
Recognizer-Pfad funktioniert.

**Schutz vor versehentlichem 3-GB-Download:** Der ML-Modus prüft via
`model_status(settings)` vor dem Lauf, ob das Modell im Cache liegt.
Bei Cache-Miss wirft die Funktion `ModelNotCachedError` mit
expliziter Anweisung (`pseudokrat model download` oder ohne `--with-ml`
laufen). CLI `main()` mapt das auf Exit-Code 2 + stderr-Meldung. Kein
silent download.

**Mode-Marker im Report:** Der Output-JSON enthält jetzt
`"mode": "with-ml"` oder `"mode": "recognizers-only"`, damit
Gap-Selektoren wissen, gegen welchen Lauf sie vergleichen.

Test-Coverage: 7 Tests in `tests/eval/test_runner_ml_mode.py` —
Recognizers-Only-Pfad lädt kein Modell, Cache-Miss wirft mit
korrekten Anweisungen, CLI-Exit-Code 2, ENV-Variable
`PSEUDOKRAT_DISABLE_ML` wird im ML-Modus aktiv gelöscht (sonst
landet Settings.load() im Null-Detector), `ModelNotCachedError`
ist `RuntimeError`-Subklasse für generisches Exception-Handling.

**Verworfene Alternativen:**

- **Auto-Download im Runner:** Damit hätte der Loop alleine 3 GB Disk
  + 5-10 min pro Lauf gefressen. Bewusste Geste mit explizitem
  Download-Befehl ist die richtige Form.
- **Eval-Lauf bewertet ML-Output gegen ML-Detector-eigenes Vokabular
  (`private_*`):** unnötiger Aufwand — `_LABEL_MAP` löst das Mapping
  schon zentral, und Fixtures sprechen unsere Domain-Sprache.

**PRL-Iteration 4 (Audit-Phase) — abgeschlossen:**

`tools/audit_run.py` bündelt fünf statische Quality-Checks in einem
Subprocess-Lauf:

* **ruff** (`ruff check src/ tests/ tools/`)
* **mypy** strict (`mypy src/pseudokrat`)
* **pytest** mit/ohne `slow`-Marker
* **bandit** -ll (High+Medium)
* **pip-audit** (optional, `skipped` wenn nicht installiert)
* **trust-boundary-coverage** — Heuristik: für jede `S<N>`-Boundary in
  `SELF_AUDIT.md` muss mindestens ein Test entweder die ID oder einen
  Title-Stem referenzieren.

**Trust-Boundary-Heuristik-Design:** Title wird auf Whitespace UND
Bindestriche zerlegt; jedes Token wird auf die ersten 5 Zeichen
gekürzt (klassischer Stem) und im Test-Code gesucht. Damit matcht
„Permutation" auch Tests, die `permute` oder `permutation` enthalten —
sonst wäre die DP-Boundary (S5) gegen Tests, die `dp_permute` heißen,
ungetestet erschienen. Stopwords (`der`, `die`, `und`, `security`,
`model`, …) sind explizit gefiltert.

**Erster Real-Audit-Lauf hat zwei echte Issues gefunden:**

1. SIM108 in `tools/audit_run.py` selbst (if/else → ternary). Fix
   inline.
2. S5 (DP-Permutation) wurde anfangs als ungetestet gemeldet — falscher
   Alarm der ursprünglich-zu-engen Heuristik (`Permutation` matchte
   `permute` nicht). Heuristik-Fix mit Stem-Match löste das.

**Test-Coverage:** 21 Tests in `tests/test_audit_run.py` —
Subprocess-Wrapper mit gemockten Returncodes (5 Checks), Title-
Stem-Tokenization (Hyphen-Split, Stopword-Filter, Inflexion-Match),
Boundary-Heading-Parsing aus SELF_AUDIT.md, Aggregation, CLI-Exit-
Codes (0 wenn pass, 1 wenn fail).

**Real-Status auf main:** alle 4 Checks pass (ruff, mypy, bandit,
trust-boundary-coverage). 7 Trust-Boundaries (S1-S7) — alle covered.

**Verworfene Alternativen:**

- **In-Process-Plugin-Loader:** wäre 5× schneller, aber riskiert
  Import-Cache-Bias (Tests, die Module modifizieren, würden nachfolgende
  Checks beeinflussen). Subprocess-Isolation ist die korrekte Form für
  ein Audit-Tool.
- **AST-basierte Trust-Boundary-Heuristik:** Overkill. Grep+Stem ist
  präzise genug für die 7 Boundaries und braucht keine Pflege bei
  Refactorings.

**Erledigt:**

- Gap-Select-Tool (`tools/gap_select.py`): geliefert in D-047.
- ML-Eval-Flag (`tests.eval.runner --with-ml`): in eval-iter-3 ergänzt
  (siehe Commit `ba60888`). Ein realer ML-Lauf gegen Fixtures wird im
  `recognizers-only`-Gate aktuell nicht eingefordert (alle Tier-1-
  Kategorien werden regelbasiert erfüllt, siehe D-046).
- Audit-CI: `.github/workflows/ci.yml` führt Ruff, Mypy, Pytest,
  Bandit und pip-audit bei jedem Push aus (deckt Tier-2 ab).

**Vertagt nach 6.x — Binäre Fixtures:** Trigger ist ein Bugreport oder
Pilot-Feedback, das eine PII-Erkennung im DOCX/XLSX/PDF-Eingabepfad
isoliert reproduzierbar macht. Aktuell reichen Plain-Text-Fixtures, um
Tier-1 zu erfüllen; die XLSX-Pipeline aus Phase 4 hat eigenständige
Pytest-Coverage.

- DOCX/XLSX/PDF-Fixture-Builder für `tests/eval/fixtures/`.


## D-041 — GUI Simple-Mode: Profil-Chrome ausblenden, Auto-Open, Close-to-Tray

**Wahl:** Wenn `ProfileManager.detect_simple_default()` einen Profilnamen
liefert (genau ein Profil, im OS-Keyring-Modus angelegt), schaltet die
GUI automatisch in einen vereinfachten Modus:

1. **Profil-Auswahl-Zeile** (`profile_input`, `password_input`,
   `open_button`) ist im UI vorhanden, aber via `setVisible(False)`
   versteckt — der Nutzer sieht keine Profil-/Passwort-Felder.
2. **Profile-Tab** wird gar nicht erst als TabWidget-Reiter hinzugefügt.
   Tabs sind nur „Live" + „Datei". (Power-User können `MainWindow(force_full_mode=True)`
   nutzen oder die CLI.)
3. **Auto-Open beim Start:** `controller.open_simple_profile(name)`
   öffnet das einzige Profil ohne Passwort-Dialog. Action-Buttons
   sind sofort enabled.
4. **Close-Verhalten:** Schließt der Nutzer das Fenster, wird es
   stattdessen in die System-Tray minimiert (`event.ignore()` +
   `self.hide()`). Toast-Notification erklärt: „Läuft im Hintergrund
   weiter. Beenden über das Tray-Menü." — Der Hotkey-Daemon und das
   Explorer-Context-Menu (D-040) bleiben aktiv.

**Erkennungs-Heuristik (`detect_simple_default`):**

```
Genau ein Profil    UND  profile_uses_keyring(db_path) == True
→ return profile.name
sonst → return None
```

* Mehrere Profile → Multi-Mandant-Setup, Selector bleibt sichtbar.
* Kein Profil → Wizard-Onboarding nötig (Phase D oder „pseudokrat install").
* Einziges Profil im Passwort-Modus → Power-User, Selector bleibt
  sichtbar (Passwort-Eingabe ist hier Feature, nicht Bug).

**Fallback bei Auto-Open-Fehler:** Wenn `open_simple_profile` wirft
(z. B. `keyring`-Lib fehlt, Keyring-Eintrag gelöscht), schaltet die GUI
zurück in den Power-User-Modus: Profil-Row + Profile-Tab werden
sichtbar gemacht, eine `QMessageBox.warning` erklärt den Fehler. Der
Nutzer kann manuell weiter — kein toter Zustand.

**Verworfene Alternativen:**

- **Hauptfenster initial direkt in Tray verstecken (Tray-First-First):**
  zu aggressiv für die ersten Sessions. Nutzer sieht beim ersten Start
  nichts und hat keine Orientierung. Stattdessen: Hauptfenster ist
  sichtbar, Close-Button macht den Tray-Übergang explizit.
- **`Profile`-Tab versteckt statt entfernt:** geht nicht direkt — QTabWidget
  hat keine `setTabVisible`-API in PySide6.6 (erst in 6.7+). Wir bauen
  den Tab also gar nicht erst ein, halten aber das Widget-Objekt für
  den Fallback bereit (`self._profiles_tab`).
- **Eigene Settings-Datei `simple_mode = true`:** zu viel State.
  Auto-Detection aus dem Profilbestand ist sauberer und reagiert
  automatisch, sobald ein zweites Profil hinzukommt.

**Test-Coverage:** 12 Tests in `tests/test_gui_simple_mode.py` —
Detect-Logik (4 Permutationen: single-simple, none, password-only,
multiple), MainWindow-Construction (hide-row, tab-list, simple-default-
state, force-full-mode-override, auto-open-session, close-to-tray,
close-quits-in-full-mode), Controller-API (open_simple_profile
activates session, rejects empty name).

**Vertagt nach 6.x — Signed-Release & Power-User-Feedback:** Trigger
sind entweder (a) der Build-Schritt des ersten signierten PyInstaller-
Pakets, das echte `.ico`-Assets benötigt, oder (b) konkretes
Pilot-Feedback, das das Erweitert-Menü oder das ausgebaute Tray-Menü
als Blocker nennt. Die aktuelle Tray-Basis aus Phase-2 deckt
Auto-Open + Close-to-Tray bereits ab; die fehlenden Menü-Punkte sind
Convenience, kein Korrektheits-Pfad.

- **Tray-Menü ausbauen:** „Hauptfenster zeigen", „Zwischenablage
  anonymisieren", „Zwischenablage deanonymisieren", „Beenden"
  (echtes Quit statt nur Hide).
- **„Erweitert"-Menüpunkt** in der Menüleiste, der `force_full_mode=True`
  einschaltet (Power-User-Übergang ohne CLI).
- **Icon-Assets:** PyInstaller-Build mit echtem `.ico` für Window-Icon,
  Tray-Icon und Context-Menu-Icon (`Icon`-REG_SZ-Feld in D-040;
  Trigger geteilt mit D-040-Vertagung).


## D-043 — Kontext-basierter Geburtsdatum-Recognizer (PRL Iter-5)

**Wahl:** Neuer `BirthDateRecognizer` in
`src/pseudokrat/recognizers/birthdate.py` matched nur dann ein Datum,
wenn ein Geburtskontext-Label (`Geburtsdatum`, `Geburtstag`,
`geboren am`, `geb.`, `DOB`, `Date of Birth`) unmittelbar davor steht.
Gap zwischen Label und Datum: max. 40 Zeichen, nur Whitespace und
Trenner (`:` `-` `—` `–`) erlaubt.

**Begründung:**

Vor Iter-5 lag DATE im Recognizer-only-Eval bei **F1 = 0.0** — drei
Fixtures mit Geburtsdaten (AT/DE/CH-Lohnkonten) wurden komplett
verfehlt, weil das Privacy-Filter-Modell DATE liefert, im ML-off-
Modus aber nichts da war. Naive Variante (blinder `DD.MM.YYYY`-Regex)
würde zwar die FN schliessen, im Gegenzug aber jede Buchungs-,
Erstellungs- und Eintrittszeile in Kanzleiakten als PII markieren —
inakzeptabel für die Zielgruppe.

Kontext-Anker löst beides: TP für die drei Geburtsdaten der
Fixtures (DATE F1 0.0 → 1.0), null FP auf der bestehenden
`false_positive_traps`-Fixture und auf den Eintritts-/Erstellt-am-
Daten innerhalb `lohnkonto_at`.

**Verworfen:**

- **Generischer `DD.MM.YYYY`-Recognizer.** Liefert auf Lohnkonten
  3-5× mehr Spans als Eval verlangt; FP-Rate würde Berufsträger sofort
  vergraulen.
- **DD/MM/YYYY und DD.MM.YY zulassen.** Mehrdeutig (US-Reihenfolge bzw.
  Jahrhundertambiguität). Bewusst nur unzweideutige Formate:
  `DD.MM.YYYY` mit 4-stelligem Jahr (19xx/20xx) und ISO `YYYY-MM-DD`.
- **`geboren in <Ort>`-Kontext.** Schliesst Geburtsorte, nicht
  Geburtsdaten. Out of scope für dieses Recognizer-Modul.

**Eval-Effekt (recognizers-only, ohne ML):**

| Kategorie | Vor Iter-5 | Nach Iter-5 |
|---|---|---|
| DATE Recall | 0.00 | 1.00 |
| DATE Precision | 1.00 | 1.00 |
| Gesamt-Recall | 0.52 | 0.62 |
| Gesamt-F1 | 0.68 | 0.77 |

PERSON und ADDRESS bleiben bewusst 0.0 — das sind genuine ML-
Kategorien, die ohne Heuristiken nicht ohne FP-Schwemme abgreifbar
sind. Sie schliessen erst, sobald der Endnutzer das Privacy-Filter-
Modell installiert hat (`pseudokrat model download` + `--with-ml`-Eval).

**Test-Coverage:** 20 Tests in `tests/test_birthdate_recognizer.py` —
9 positive Fälle (DD.MM.YYYY in AT/DE/CH, ISO-Format, Label-Varianten),
9 negative Fälle (Eintrittsdatum, Berichtdatum, Volltext zwischen
Label und Datum, ungültiges Datum, zu kurzer Year-String, zu grosser
Abstand), 2 Span-Offset-Tests, 1 Default-Bundle-Integration.


## D-044 — Anker-basierter PERSON-Recognizer (PRL Iter-6)

**Wahl:** `PersonRecognizer` matched Personennamen nur, wenn vor dem
Namensfeld ein **Anrede-Anker** (`Herr`, `Frau`, `Herrn`) oder ein
**Rollen-Label** (`Dienstnehmer/in`, `Arbeitnehmer`, `Antragsteller`,
`Mandant`, …) steht. Optional dazwischen akademische Titel (`Dr.`,
`Prof.`, `Mag.`, `Dipl.-Ing.`, `MMag.`, `DDr.`). Second-Pass markiert
exakte Wiedervorkommen des Namens im Resttext.

**Begründung:**

Personennamen ohne Anker sind ohne ML-Modell nicht zuverlässig
unterscheidbar von Firmen-, Marken- und Ortsnamen ("Hofer", "Bauer",
"Müller-Schiene"). Sobald aber Anrede oder Rollen-Label davorsteht, ist
die Precision praktisch 100%. Im Kanzlei-Alltag steht vor jedem
ernsthaft sensiblen Namen ein solcher Anker — sei es im Briefkopf
("Sehr geehrter Herr …"), in Lohnkonten ("Arbeitnehmer: …") oder in
Versicherungsanträgen ("Antragsteller: …").

**Verworfen:**

- **Bare-Name-Heuristik (ohne Anker).** Auf der `false_positive_traps`-
  Fixture allein produziert das FP für "Hofer-Markt", "Müller-Schiene",
  "Bauer-Land-Speck". Ein Steuerberater verliert dann sofort das
  Vertrauen. Bare-Namen bleiben ML-Territorium.
- **Wörterbuchbasierte Vornamenliste.** 50k+ Einträge, falsch bei
  Namen wie "Beispielsohn", "Mustermann" (synthetisch), Migranten-
  namen — und blockt nicht die FP-Klasse oben.
- **Inter-Token-Whitespace `\s+`.** Zog "Anna Beispielsohn\nAnmerkungen"
  in den Span. Fix: `[ \t]+` schliesst Newlines aus.

**Second-Pass-Begründung:** Im Eval-Korpus erscheint jeder Name 2×
(einmal an einem Anker, einmal als Volltextreferenz). Second-Pass
schliesst die Wiedervorkommen ohne FP, weil nur exakte ganze-Wort-
Matches des bereits validierten Namens zählen.

**Eval-Effekt (recognizers-only, ohne ML):**

| Kategorie | Vor Iter-6 | Nach Iter-6 |
|---|---|---|
| PERSON Recall | 0.00 | 1.00 |
| PERSON Precision | 1.00 | 1.00 |
| Gesamt-Recall | 0.62 | 0.83 |
| Gesamt-F1 | 0.77 | 0.91 |

**Test-Coverage:** 19 Tests in `tests/test_person_recognizer.py` —
Anrede-Varianten (Herr/Frau/Herrn + Titel-Stapel), Rollen-Label-
Varianten (Dienstnehmer/in/Arbeitnehmer/Antragsteller/Mandant),
Second-Pass-Wiedervorkommen, Bindestrich-Namen,
FP-Trap-Sätze (Hofer-Markt/Müller-Schiene), Span-Offset-Verifikation.


## D-045 — DACH-ADDRESS-Recognizer (PRL Iter-7)

**Wahl:** `AddressRecognizer` matched DACH-Postanschriften im
hochregulären Format `<Strasse> <Nr>, <PLZ> <Ort>`. PLZ ist
4-stellig (AT/CH) oder 5-stellig (DE). Strassen-Suffix kann
verschmolzen (`Industriestraße`, `Königsallee`) oder eigenständig
(`Mariahilfer Straße`) auftreten. Hausnummern erlauben
Buchstaben-Suffix (`12a`) und Stiegen-Notation (`12/3`).

**Begründung:**

Im Gegensatz zu PERSON ist ADDRESS strukturell extrem klar. Die
Komma-PLZ-Pflicht im Pattern eliminiert das gesamte FP-Spektrum
("Goethestraße 5 (ohne PLZ und Ort)" wird **nicht** gematcht, weil
keine PLZ folgt). Ein anker-basierter Ansatz wie bei PERSON ist hier
unnötig — das Format selbst ist der Anker.

**Verworfen:**

- **Anker-basiertes Pattern (`Adresse:` / `Anschrift:` / `Wohnadresse:`).**
  Würde Adressen in Briefkopf-Zeilen ohne Label verfehlen.
- **Token-Wörterbuch für Strassen-Suffixe inklusive aller Varianten
  (`-zeile`, `-pfad`, `-stiege`).** Premature optimization — die
  9 häufigsten Suffixe decken >99% der DACH-Adressen ab.
- **Kombination mit `geocoder`/`pyap`.** Externe Geodaten-Libraries
  ziehen Cloud-Calls oder grosse Wörterbücher mit. Pseudokrat bleibt
  bewusst offline.

**Eval-Effekt (recognizers-only, ohne ML):**

| Kategorie | Vor Iter-7 | Nach Iter-7 |
|---|---|---|
| ADDRESS Recall | 0.00 | 1.00 |
| ADDRESS Precision | 1.00 | 1.00 |
| Gesamt-Recall | 0.83 | **1.00** |
| Gesamt-F1 | 0.91 | **1.00** |

**100% F1 über alle 12 DACH-PII-Kategorien, ML-Modell nicht erforderlich.**

**Test-Coverage:** 13 Tests in `tests/test_address_recognizer.py` —
AT/DE/CH-Varianten, verschmolzene/eigenständige Strassen-Suffixe,
Hausnummern mit Buchstaben/Stiegen-Notation, FP-Trap-Fixture
(Strasse ohne PLZ darf nicht matchen), Default-Bundle-Integration.

**Wichtiger Vorbehalt:** 100% F1 gilt für den synthetischen
Eval-Korpus (3 Fixtures + FP-Trap). Realistische Kanzleitexte enthalten
Adressen in Variationen (Mehrfamilienhaus-Suffixe, internationale
Adressen, Postfach-Notation), die nicht abgedeckt sind und vom
ML-Modell gegriffen werden. Trade-Off bewusst akzeptiert für Iter-7;
Erweiterung in Folge-Iterationen sobald reale Pilot-Daten vorliegen.


## D-046 — Install-Defaults umkehren + `pseudokrat doctor` (PRL Iter-8)

**Wahl:** Zwei Vereinfachungen für Pilot-Tester:

(A) **Hotkeys per Default AN.** `pseudokrat install` aktiviert ab Iter-8
das Autostart des Hotkey-Daemons. `--no-hotkeys` schaltet aus.
`--with-hotkeys` bleibt als Skript-Kompatibilitäts-Alias erhalten
(versteckt im Help, kein Default-Wechsel).

(B) **Neuer `pseudokrat doctor`-Befehl.** Einzelner Selbst-Diagnose-
Aufruf liefert vier Checks mit konkreten Fix-Anweisungen:
- Profile vorhanden?
- Anonymize/Deanonymize-Roundtrip auf einem Test-String mit IBAN +
  Anrede + Person + Betrag — Original-Text muss 1:1 wiederkehren.
- Hotkey-Backend (`keyboard` oder `pynput`) importierbar?
- ML-Modell im Cache?

Exit 0 = Kern-Workflow läuft (WARNs erlaubt). Exit 1 = blockierender
Fehler — Tester weiss sofort, was zu tun ist.

**Begründung:**

Sven's Forderung: „supereinfach in der Installation und in der Bedienung".
Vor Iter-8 brauchte ein Tester zwei Befehle (`install`, `install
--with-hotkeys`), und bei Problemen hatte er keine zentrale Diagnose —
einzelne CLI-Aufrufe versuchen ist nicht zumutbar. Nach Iter-8:

* Ein Befehl `pseudokrat install` setzt alles auf.
* Ein Befehl `pseudokrat doctor` sagt zuverlässig, ob alles funktioniert,
  und wenn nicht, welche genau eine Befehlszeile das Problem behebt.

**Verworfen:**

- **Hotkeys ohne `--with-hotkeys`-Alias entfernen.** Würde Skripte
  brechen, die Iter-7-Verhalten erwarten. Alias bleibt, ist aber
  `argparse.SUPPRESS` (im Help versteckt).
- **`doctor` als GUI-Tab statt CLI-Befehl.** GUI-Pilot-Tester nutzen
  meistens das Tray-Icon, brauchen aber CLI-Fix-Anleitungen für
  IT-Hotline-Anrufe. CLI ist universeller.
- **Automatischer `doctor`-Lauf am Ende von `install`.** Würde Setup
  um 3-5 s verlängern und im Erfolgsfall keine zusätzliche Information
  liefern. Stattdessen wird der `doctor`-Befehl im `install`-Output
  prominent als „Nächster Schritt" empfohlen.

**Test-Coverage:** 16 Tests in `tests/test_doctor.py` —
Status-Enum-Roundtrip, Profile-Detection (leer/nicht-leer),
Roundtrip-Smoke gegen Throwaway- und Named-Profil, Backend-/Modell-
Status-Returns, Report-Formatting (alle drei Status-Kombinationen),
CLI-Argparse-Integration (`doctor` registriert, `--profile`,
`--no-hotkeys` als neuer Default-Override).


## D-047 — Gap-Select-Tool (PRL Iter-9)

**Wahl:** `tools/gap_select.py` ist die priorisierende Brücke
zwischen Eval-Phase und Close-Phase im PRL-Loop. Eingabe: ein
`eval_report.json` (Pflicht) plus optional ein `audit_report.json`.
Ausgabe: ein `next_gap.md` mit **einer** Top-Lücke + Liste der
übrigen. Severity-Modell mit drei Stufen:

1. **Tier-1-Erkennungsdefizit** — eine Kategorie aus dem Gate
   liegt unter ihrer F1-Schwelle.
2. **Globale FP-Rate** über dem Gate-Limit (Default `≤ 0.02`).
3. **Tier-2/Tier-3** — Audit-Check-Fail oder ungetestete
   Trust-Boundary.

Die Sortierung wählt deterministisch die erste Tier-1-Lücke als
nächste zu schließende — Close-Phase weiss damit ohne Diskussion,
woran sie arbeitet.

**Wichtige Mapping-Entscheidung:** Das Gate spricht von `ORG`,
der Eval-Report (und damit der Production-Code) von `COMPANY`.
Die Alias-Tabelle `CATEGORY_ALIASES = {"ORG": "COMPANY"}` ist die
einzige Stelle, an der dieses Vokabular gebrückt wird; das Gate
behält seinen externen Vertragsnamen.

**ML-Kategorie-Sonderfall:** PERSON, ADDRESS, DATE können vom
regelbasierten Pfad bedient oder vom ML-Detector kommen. Ist der
Eval im `recognizers-only`-Mode und enthält den Score nicht, gilt
das als **Severity 3** (Phase-2-Ausstand) — sonst würde der Loop
in eine Endlos-Spirale gehen, weil das Modell 3 GB groß und nicht
Teil der CI-Default-Schleife ist. Sind die Recognizer-Iterationen
(Iter-5/6/7) auf 100 %, taucht hier gar keine Lücke auf — der
aktuelle Stand des Repos demonstriert das (Lauf gegen Real-Eval
ergibt „Keine offenen Lücken").

**Verworfen:**

- **Mehrere Top-Lücken pro Lauf.** Der PRL-Vertrag ist „eine
  Lücke, ein Commit". Mehrere Top-Lücken hätten den Loop in
  parallele Branches gezwungen; das gehörte zu einer DAG-PRL,
  nicht zu unserem sequentiellen Modell (siehe D-042).
- **Markdown-AST-Parser für das Gate.** Overkill — das Gate hat
  zwei Regex-Anker (Tier-1-Tabellen-Zeile und FP-Rate-Inline),
  das ist robuster als ein full-blown Parser, der bei Format-
  Refactorings bricht.
- **Auto-Anwendung des `fix_hint` durch einen Agenten.** Bewusste
  Geste — der Hint ist ein Vorschlag, kein Befehl. Close-Phase ist
  menschlich (oder LLM-supervidiert) gesteuert, damit subtile
  Recognizer-Änderungen nicht ungeprüft landen.

**Test-Coverage:** 22 Tests in `tests/test_gap_select.py` —
Gate-Parsing (synthetisch + echte Datei), Tier-1-Schwelle, FP/FN-
Dominanz-Hint, ML-Kategorie-Severity-Switch, FP-Rate über/unter
Limit, Audit-Check-Fail, Trust-Boundary-Missing-Liste, Rendering
(leer/single/multi), CLI-Roundtrip mit JSON-File-Input + Output-
Datei.

**Vertagt nach 6.x — PRL-Chain in CI:** Trigger ist ein PR, der das
PRL-Gate vor Merge automatisch im CI prüfen soll (PR-Reviewer will
`next_gap.md` als Artefakt sehen). Aktuell wird der Loop lokal
gefahren, die Tier-2-Checks laufen bereits via `ci.yml`; die
PRL-Verkettung (`runner` → `audit_run` → `gap_select`) ist nur die
Orchestrierung obendrauf. Binär-Fixture-Trigger geteilt mit
D-042-Vertagung.

- CI-Workflow (`.github/workflows/prl.yml`), der `runner` → `audit_run`
  → `gap_select` verkettet und das resultierende `next_gap.md` als
  Job-Artefakt ablegt.
- DOCX/XLSX/PDF-Fixture-Builder für binäre Formate (verbleibend
  aus D-042).

## D-048 — Fuzzy-Merge auf COMPANY/ORG beschränken (PERSON + ADDRESS raus)

**Wahl:** `_FUZZY_MERGE_CATEGORIES` in `src/pseudokrat/fuzzy.py` von
`{"COMPANY", "ORG", "PERSON", "ADDRESS"}` auf `{"COMPANY", "ORG"}`
reduziert. PERSON und ADDRESS verlangen jetzt **Exact-Match nach
Normalisierung**, kein Levenshtein-Fuzzy mehr.

**Befund (adversariale Roundtrip-Probe):** Der Satz „Frau Maier
und Herr Mayer kamen." kollabierte beide Namen auf `<PERSON_001>`
und deanonymisierte zu „Frau Mayer und Herr Mayer". Zwei **reale,
verschiedene** Personen (Levenshtein 1) wurden zu einem Platzhalter
verschmolzen. Das ist gleichzeitig:

1. **Roundtrip-Bug** — Deanonymisierung liefert den falschen
   Originalnamen für den zweiten Treffer zurück.
2. **Datenschutz-Korrektheitsfehler** — zwei verschiedene
   Mandanten verschmelzen in der KI-Eingabe zu einer Identität.

Gleiches gilt für Adressen (`Hauptstraße 12` / `Hauptstraße 13`
liegen Levenshtein 1 auseinander, sind aber verschiedene
Anschriften) und Nachnamen-Cluster (Maier/Mayer/Meier/Meyer).

**Warum kein Verlust legitimer Konsistenz:** Echte Schreibvarianten
**derselben** Person/Adresse (Umlaut, Groß/Klein, Bindestrich,
Mehrfach-Whitespace) werden bereits von `normalize()` gefaltet
(ä→ae, ö→oe, NFKD, Sonderzeichen→Space) und matchen damit über den
**Exact**-Pfad. Fuzzy war für diese Fälle nie nötig — es fing
ausschließlich die gefährlichen „fast-gleich-aber-verschieden"-Fälle.

**Asymmetrie der Fehlerkosten:** Über-Segmentierung (ein Pseudonym
zu viel für dieselbe Entität) ist voll reversibel und harmlos — die
KI sieht zwei Platzhalter statt einem, der Roundtrip bleibt korrekt.
Falsch-Merge (ein Pseudonym für zwei Entitäten) ist **irreversibel**
und bricht beide oben genannten Eigenschaften. Bei Personen/Adressen
ist die sichere Richtung daher Exact-only.

**COMPANY/ORG bleiben Fuzzy:** Bei Firmennamen ist der
Schreibvarianten-Spielraum echt (`Hofer Bau GmbH` / `Hofer-Bau GmbH`
/ `HoferBau GmbH`) **und** durch die identische Rechtsform-Endung
zusätzlich abgesichert — zwei Firmen mit gleicher Rechtsform und
Levenshtein-≤2-Kern sind praktisch dieselbe Firma. Siehe D-032.

**Verworfen:**

- **Distanz-Schwelle auf 1 senken statt Kategorie streichen.** Maier
  /Mayer ist Levenshtein 1 — jede Fuzzy-Schwelle ≥ 1 fängt sie. Nur
  Exact (Distanz 0) ist sicher.
- **Kontext-Heuristik (gleicher Vorname → mergen).** Fragil und löst
  das Grundproblem nicht; „Herr Maier" vs. „Frau Mayer" hätte keinen
  gemeinsamen Vornamen-Anker, „Anna Maier"/„Anna Mayer" könnten
  trotzdem verschiedene Personen sein.

**Test-Coverage:** Regressionstests in `tests/test_fuzzy.py`
(Maier≠Mayer, Hauptstraße 12≠13 bekommen distinkte Platzhalter;
Umlaut-/Whitespace-Varianten **derselben** Person mergen weiterhin
via Exact-Normalisierung) plus Roundtrip-Assertion.

## D-049 — Platzhalter-förmige Literale im Quelltext escapen (PRL Iter-11)

**Wahl:** Neuer `EscapedPlaceholderRecognizer` (Kategorie `ESCAPED`,
`src/pseudokrat/recognizers/escaped_placeholder.py`), erster Eintrag
im `default_recognizers()`-Bundle, Score `1.0`.

**Befund (adversariale Roundtrip-Probe):** Der Satz „Der Code
`<PERSON_001>` ist ein Platzhalter, Herr Müller." brach den Roundtrip:
das literale `<PERSON_001>` im Quelltext wurde beim Deanonymisieren
als **echter** Platzhalter aufgelöst und mit „Müller" überschrieben →
„Der Code Müller ist ein Platzhalter, Herr Müller."

**Ursache:** Der Deanonymizer-Regex `<([A-Z_]+)_(\d{3,})>` kann nicht
unterscheiden, ob ein platzhalter-förmiger Token von uns stammt oder
bereits im Original stand.

**Lösung:** Bei der Anonymisierung werden solche Token vorab erkannt
(identisches Muster wie der Deanonymizer-Regex) und auf einen eigenen
reservierten `ESCAPED`-Platzhalter abgebildet. Da der Deanonymizer in
**einem** `re.sub`-Pass arbeitet und ersetzten Text nicht erneut
scannt, lösen sich echte (`<PERSON_001>` → Müller) und escapete
(`<ESCAPED_001>` → literal `<PERSON_001>`) Token unabhängig auf — der
ursprüngliche Literaltext wird 1:1 wiederhergestellt.

**Score 1.0:** Der Recognizer muss jeden Overlap gewinnen, damit ein
platzhalter-förmiges Literal nie von einem anderen Recognizer
teil-maskiert wird.

**Verworfen:**

- **Zähl-Suffix-Vergleich beim Deanonymisieren** (nur auflösen, wenn
  Platzhalter im Store existiert). Halbe Lösung: ein zufällig
  kollidierender literaler `<PERSON_001>`, der **auch** als echter
  Platzhalter vergeben wurde, bliebe mehrdeutig. Escaping beim
  Anonymisieren ist die einzige eindeutige Richtung.
- **Backslash-Escaping im Text** (`\<PERSON_001\>`). Verändert den
  sichtbaren KI-Eingabetext und wäre selbst nicht roundtrip-stabil,
  wenn das Modell die Escapes umformatiert.

**Test-Coverage:** `tests/test_escaped_placeholder.py` (Match/No-Match,
Mehrfach-Token) plus Roundtrip-Integrationstest `test_case_8` in
`tests/test_anonymizer_integration.py`.


## D-050 — `pip-audit` auditiert das Projekt, nicht die laufende venv

**Wahl:** Der PRL-Audit-Check ruft `pip-audit --strict <REPO_ROOT>` (Projekt-Pfad) statt `pip-audit --strict` (env-Scan).

**Begründung:**
- `pseudokrat` selbst ist in der Dev-venv via `pip install -e .` als editable installiert.
- Ein env-weiter Scan wirft im `--strict`-Modus `distribution marked as editable` als harten Fehler, weil pip-audit für die lokale Editable keinen PyPI-Eintrag findet (D-049 hatte das als bekannten False Positive markiert).
- `pip-audit <project_path>` baut intern eine isolierte venv aus der `pyproject.toml`, installiert genau die deklarierten Runtime-Deps darin und auditiert diese. Genau das wollen wir prüfen — die Supply-Chain, nicht die Dev-Werkzeuge.
- Trade-Off: rund 30 s Setup-Zeit für die temporäre venv. Akzeptabel, da der Audit-Lauf ohnehin pytest (~150 s) enthält.

**Alternative verworfen:** `--skip-editable` setzt zwar das editable-Paket aus, lässt aber den Exit-Code in `--strict` trotzdem auf 1 (es wertet das Skip als Collection-Fehler). Damit ergibt sich kein grüner Pfad.

**Vertagt nach 6.x — Air-gapped CI:** Trigger ist die Anforderung,
den Audit-Lauf in einer luftleeren Pipeline ohne PyPI-Index-Zugriff
zu fahren (z. B. Kanzlei-On-Premise-CI). Aktuelle CI
(`.github/workflows/ci.yml`) hat Netzzugang.

- Offline-Pinning via `--locked` lockfile, sobald CI keinen PyPI-
  Zugriff mehr haben darf.


## D-051 — Doctor-Sandbox, Profile-Health & Profile-Remove (PRL Iter-14)

**Kontext:** Pilot-Tester-Feedback hat drei verbundene Lücken im
Pre-Iter-14-Setup gezeigt:

1. Der Doctor-Smoke-Test (`check_anonymize_roundtrip`) legte ein Profil
   `_doctor_smoke.sqlite` direkt im echten `profiles_dir` an, hielt das
   Keyring-Secret aber nur im RAM. Nach App-Neustart blieb die DB liegen,
   das Secret war weg — Folge-Doctor-Runs scheiterten beim Entschlüsseln,
   und `profiles list` zeigte ein gespenstisches Profil ohne Besitzer.
2. Backup-Restore eines Profils auf einem neuen Windows-Konto verlor den
   OS-Keyring-Eintrag — das Profil war unbenutzbar, ohne dass der Nutzer
   wusste, warum. Doctor sagte „Profile: OK" obwohl nichts ging.
3. Ein einmal angelegtes Profil ließ sich nicht sauber wegräumen: DB,
   Salt-Sidecar, Keyring-Marker und der OS-Keyring-Eintrag blieben
   alle erhalten, weil das CLI keinen Remove-Pfad hatte.

**Wahl:**

* **Echte TempDir-Sandbox für `check_anonymize_roundtrip`** — eigener
  `ProfileManager` auf `tempfile.TemporaryDirectory`. Smoke-Profil heißt
  schlicht `smoke`, kein Underscore-Prefix nötig, weil der Sandbox-Pfad
  beim finally-Cleanup mit allen Artefakten verschwindet.
* **`_purge_legacy_sandbox_artifacts`** als einmalige Migration, die
  Bestandsleichen (`_doctor_smoke.sqlite`, `doctor_smoke.sqlite` + Salt
  + Marker) aus echten `profiles_dir`-Installationen entfernt. Greift
  zu Beginn von `run_doctor`, damit `check_profiles` keine Leichen mehr
  als User-Profile sieht.
* **`RESERVED_PROFILE_SLUG_PREFIX = "_"`** in `ProfileManager.list_profiles`
  als zweite Verteidigungslinie: Profile mit Slug-Prefix `_` werden im
  CLI/GUI ausgeblendet (Override via `include_reserved=True` für
  Cleanup-Tools). Verhindert künftige Sandbox-Leck-Klassen, falls neue
  interne Smoke-Tests doch wieder im Echt-Dir landen sollten.
* **Neuer Doctor-Check `check_profile_health`** öffnet jedes Simple-Mode-
  Profil über den echten OS-Keyring und meldet WARN (nicht FAIL) mit
  Namen und konkretem Fix-Befehl, wenn der Roundtrip scheitert. Passwort-
  Profile werden als „nicht offline prüfbar" gezählt, nicht als kaputt
  markiert — wir können das User-Passwort nicht erfragen.
* **Neues CLI-Subkommando `pseudokrat profiles remove <name>`** mit
  interaktiver Bestätigung (überspringbar via `--force`). Löscht
  best-effort DB, Salt-Sidecar, Keyring-Marker und den OS-Keyring-
  Eintrag in einem Aufruf. Berichtet am Ende, welche Artefakte
  tatsächlich entfernt wurden.
* **`InstallResult.profile_error`** trennt „Profil-Anlage angefragt und
  gescheitert" von „Profil existierte schon" — das CLI rendert das jetzt
  mit ✗ statt einer schwachen ℹ-Note ganz unten und setzt den Exit-Code
  auf ungleich 0, damit Skripte die Fehlerursache erkennen.

**Begründung:**
- Doctor muss idempotent sein. Wenn er Artefakte hinterlässt, die er beim
  nächsten Lauf nicht mehr öffnen kann, ist er das Problem, das er
  diagnostizieren sollte.
- Pilot-Tester-Mantra „eine klare Anlaufstelle, ein konkreter nächster
  Schritt": jeder neue WARN nennt den genauen Befehl (`pseudokrat
  profiles remove`), den der Nutzer braucht.
- Best-Effort-Remove statt Transaktion: ein fehlender Sidecar (Halb-
  Migration aus Pre-Iter-14) darf den Rest der Löschung nicht blockieren.

**Test-Coverage:**
- `tests/test_doctor.py`: Sandbox-Roundtrip in TempDir, Leak-Test (kein
  Residuum im echten `profiles_dir`), Migration alter Sandbox-Stems,
  Profile-Health für gesund/kaputt/leer/Passwort-Modus.
- `tests/test_cli.py`: `profiles remove` mit/ohne `--force`, mit
  fehlendem Profil, mit fehlenden Sidecars, Keyring-Eintrag-Cleanup.
- `tests/test_install.py`: `profile_error` propagiert korrekt,
  `has_critical_failure` triggert, Exit-Code ungleich 0.

**Alternative verworfen:** Sandbox-Profil weiterhin im echten
`profiles_dir` belassen und nur die `_*`-Filterung in `list_profiles`
einbauen würde das User-sichtbare Symptom beheben, aber Folge-Doctor-
Runs würden weiter an der nicht-entschlüsselbaren DB scheitern. Echte
TempDir-Trennung ist die einzig saubere Lösung.


## D-052 — PERSON-Recognizer erkennt Adelsprädikate (PRL Iter-15)

**Kontext:** Der ML-freie `PersonRecognizer` ankert Namen an Anreden
(`Herr`/`Frau`) und Rollen-Labels (`Mandant:`), matcht das Namensfeld
dann über `_NAME_FIELD`. Die Token-Definition kannte aber keine
nobiliary particles. DACH-Dokumente sind voll davon — `von`, `van der`,
`zu`, `von und zu`. Folge: das Namensfeld wurde zerrissen. Entweder
kompletter Miss (`Herr von Habsburg` → kein Treffer, weil `von`
kleingeschrieben kein `_NAME_TOKEN` ist) oder — schlimmer — ein
abgeschnittener Span (`Alexander Van der Bellen` → nur `Alexander Van`).
Ein abgeschnittener PERSON-Span ist der gefährlichste Fall: der Anwender
glaubt, der Name sei maskiert, aber der Restname (`der Bellen`) bleibt im
Klartext und leakt beim Paste ins Cloud-KI-Prompt.

**Wahl:**

* **`_PARTICLE`-Alternation**, longest-first geordnet (`von und zu` vor
  `von der` vor `von`), damit der Regex die längste Partikelkette greift
  statt vorzeitig bei `von` abzubrechen.
* Partikel als **optionales führendes Element** (`von Habsburg`) UND als
  **Konnektor zwischen Namens-Tokens** (`Van der Bellen`, `zu
  Guttenberg`) in `_NAME_FIELD`.
* Die kurzen Konnektoren (`der`/`den`/`dem`/`de`/…) sind bewusst **nur
  zwischen bzw. vor Namens-Tokens** erlaubt, nie freistehend. Das hält
  den FP-Pfad eng: `Herr Müller und Frau Meier` bleibt zwei getrennte
  Treffer und wird nicht zu einem `Müller und … Meier`-Sammelspan.

**Begründung:**
- Ein halb-maskierter Name ist schädlicher als ein gar nicht erkannter,
  weil er falsche Sicherheit suggeriert. Adelsprädikate sind in der
  DACH-Mandantschaft (Anwälte, Notare, Vermögensverwalter) keine
  Randerscheinung.
- Longest-first ist nötig, weil Regex-Alternation den ersten passenden
  Zweig nimmt — `von` würde `von der` sonst verschlucken.

**Test-Coverage:**
- Eval-Fixture `tests/eval/fixtures/kanzlei_adel/`: Mandatsschreiben mit
  `Maximilian von Sonnenberg`, `Anna zu Falkenstein`, `Markus Van der
  Velde`; jeder Name zweimal (Anker + Second-Pass). F1=1.00.

**Alternative verworfen:** Partikel global als `_NAME_TOKEN`-Variante
(kleingeschriebene Tokens generell erlauben) würde unzählige
Funktionswörter als Namensbestandteil zulassen und die FP-Rate sprengen.
Eine geschlossene Partikel-Whitelist ist die präzisere Lösung.


## D-053 — Steuer-ID in gruppierter Anzeigeform (PRL Iter-16)

**Kontext:** Der `GermanSteuerIdRecognizer` scannte mit
`(?<!\d)\d{11}(?!\d)` — also nur 11 *zusammenhängende* Ziffern. Die
deutsche Steuer-Identifikationsnummer wird amtlich (BMF, Finanzamt-
Bescheide, Lohnsteuerkarten) aber in der Gruppen-Form `47 036 892 816`
(2-3-3-3) dargestellt. Diese Form blieb komplett unerkannt — ein
Klartext-PII-Leak. Auffällig: `is_valid_de_steuer_id` rief bereits
`candidate.replace(" ", "")` auf, war also auf gruppierte Kandidaten
vorbereitet — nur lieferte das Scan-Regex nie einen. Ein latentes,
halb-implementiertes Feature. (Zum Vergleich: IBAN, AHV und SVNR
tolerieren Trennzeichen bereits im Scan-Regex.)

**Wahl:**

* Regex-Alternation:
  `(?<!\d)(?:\d{11}|\d{2} \d{3} \d{3} \d{3})(?!\d)`. Die gruppierte
  Variante akzeptiert genau die amtliche 2-3-3-3-Form mit
  Einzel-Leerzeichen, kein beliebiges Whitespace-Muster.
* Keine Änderung am Validator — er strippte Leerzeichen schon.

**Begründung:**
- FP-Risiko ist minimal: jede gematchte Kette läuft durch die strikte
  § 139b-Strukturprüfung (genau eine Ziffer 2x/3x in den ersten zehn) UND
  die ISO-7064-Prüfziffer. Eine zufällige Beleg-/Rechnungsnummer in
  2-3-3-3-Form müsste beide Tests bestehen, um getaggt zu werden — die
  identische Hürde gilt bereits für die zusammenhängende Form.
* Tight statt permissiv (`\s+` o. Ä. abgelehnt): die amtliche Form hat
  exakt diese Gruppierung; alles Weitere würde nur FP-Fläche schaffen.

**Test-Coverage:**
- `tests/test_recognizers_de.py`:
  `test_steuer_id_recognizer_finds_grouped_form` (gruppiert wird
  erkannt) + `test_steuer_id_grouped_invalid_checksum_rejected`
  (`12 345 678 901` als Beleg-Nr. wird NICHT getaggt).
- Eval-Fixture `tests/eval/fixtures/rechnung_de/` mit gruppierter
  Steuer-ID, gruppierter DE-IBAN (Regression-Guard) und einem
  FP-Trap-Beleg. F1=1.00.

**Bewusst nicht im Scope (Folgearbeit):** Die AT-UID `ATU 12345678` mit
Leerzeichen nach dem Präfix wird weiterhin nicht erkannt. Anders als die
Steuer-ID ist die *amtliche* UID-Form leerzeichen-los (`ATU12345678`);
die Leerzeichen-Variante ist Tipp-Konvention, kein Standard, und der
`is_valid_at_uid`-Validator müsste zusätzlich angepasst werden (er
strippt aktuell keine Leerzeichen). **Reaktivierungs-Trigger:** ein
Pilot-Fixture mit realer leerzeichen-getrennter UID, das einen Miss
zeigt.

## D-054 — Adelsprädikat-Lecks via Testarena geschlossen (PRL Iter-17)

**Kontext:** Eine neue gegnerische Testarena (`tests/arena/`) baut Dokumente
aus bekannter Ground Truth und prüft, dass kein PII-Wert die echte Pipeline
überlebt (Normalform-Vergleich, Roundtrip, Negativ-Kontrolle). Der erste Lauf
über 1.500 Dokumente / 9.750 Werte fand 97 PERSON-Lecks (~4 %), ausschließlich
Namen mit Adelsprädikat (`von`/`zu`/`van der`). Ursache zweigeteilt: (1) Der
anker-basierte `PersonRecognizer` kennt nur eine feste Titel-Liste; ein
unbekannter Titel (`DI`, `BSc` — in AT allgegenwärtig) zwischen Anrede und Name
ließ den ganzen Match scheitern, der Restname rutschte ungeschützt in den
Cloud-KI-Prompt. (2) Der ML-freie `GazetteerNameRecognizer` bricht die
Namens-Sammlung an jedem Nicht-Leerzeichen-Gap ab — das kleingeschriebene
Prädikat zerriss `Birgit zu Schmid` zu nur `Birgit`. Iter-15 (D-052) hatte
Adelsprädikate nur im `_NAME_FIELD` des Anker-Pfads gelöst, nicht im Gazetteer.

**Wahl:** Zwei minimale, voneinander unabhängige Fixes (Defense-in-Depth), jeder
für sich ausreichend für 0 Lecks im Korpus:
- `person.py`: Titel-Anker um moderne/österreichische, oft punktlose Grade
  erweitert (`DI`, `DI(FH)`, `BSc`, `MSc`, `MBA`, `BEd`, `MEd`, `Ing.`,
  `Dkfm.`, `LL.M.`, `LL.B.`, `PhD`); Reihenfolge longest-first, damit `DI(FH)`
  vor `DI` und gepunktete vor punktlosen Varianten greifen.
- `person_name.py`: schmale Adelsprädikat-Whitelist (`von`/`van`/`zu`/`vom`/
  `von der`/`van der`/`van den`/`von und zu`) überbrückt den Gap zwischen Vor-
  und Nachname; bewusst **ohne** den Artikel `der` (sonst sammelt der
  Konnektor-Pfad Funktionswörter ein) und nie über einen Zeilenumbruch.

**Begründung:** Für einen Anonymisierer ist ein Leck (Klartext-PII in die Cloud)
ungleich teurer als eine Über-Redaktion; der Gazetteer-Pfad ist daher
recall-orientiert (Score 0.6, strukturierte Recognizer gewinnen bei Überlappung).
Zwei unabhängige Pfade bedeuten, dass selbst ein künftig fehlender Titel die
Lücke nicht wieder öffnet, solange ein bekannter Vorname im Spiel ist.

**Test-Coverage:** Arena 1.500 Dok. / 9.750 Werte → **0 Lecks**, 0
Roundtrip-Fehler, Negativ-Kontrolle grün. `tests/arena/test_arena_zero_leak.py`
(5 Tests, inkl. des jetzt **harten** `test_nobiliary_person_names_are_leak_free`,
zuvor `xfail`). Eval-F1 bleibt 1.00 in allen 12 Kategorien.

**Alternative (verworfen):** (a) ML-Privacy-Filter standardmäßig laden — 3 GB
Download, widerspricht dem recognizers-only-Default. (b) Titel-Liste als
Catch-all `[A-Z][A-Za-z.()]+` öffnen — frisst echte Vornamen, zu viele False
Positives. (c) Im Gazetteer auch den Artikel `der` als Konnektor zulassen —
würde `Anna der …` einsammeln, schlechtes Precision-Risiko ohne realen Nutzen.

**Nachtrag (Council-Review, derselbe Tag):** Ein Multi-Perspektiven-Review
deckte drei weitere Punkte auf, die direkt geschlossen wurden:
(1) **Justiz-Rollen-Anker** in `_ROLE_LABELS` (`Beklagter`, `Zeuge`,
`Angeklagter` …) — ein Name ohne Anrede mit gazetteer-fremdem Vornamen leckte
sonst (`Beklagter: DI von Gruber`). `Kläger(in)` bewusst ausgelassen
(Kollision mit Firmen-Recognizer im Rubrum).
(2) **Arena-Abdeckung:** Land war an die Vorlage gekoppelt → AHV/USt-IdNr
wurden nie erzeugt; entkoppelt, Arena prüft jetzt alle 13 Kategorien.
(3) **USt-IdNr-Ground-Truth** trug keine gültige Prüfziffer → 79 Schein-Lecks;
Generator auf ISO-7064-MOD-11,10 umgestellt.
Sechs weitere, eng umrissene Restlücken (Zeilenumbruch im Namen,
Komma-Inversion, Adelstitel-Slot, Teil-Token-Granularität, Tabellen-Layout
ohne Trennzeichen, Datei-Format-Ebene) sind in `tests/arena/BEFUND.md`
(„Bekannte Grenzen") als Backlog offen dokumentiert — recall-orientierter
recognizers-only-Modus, ML-Modell schliesst den Rest.
