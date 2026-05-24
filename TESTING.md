# Test-Umgebung

Diese Datei beschreibt die Pseudokrat-Test-Pyramide und wie sie ausgeführt wird.

## Übersicht

| Schicht | Datei(en) | Tests | Laufzeit | Pflicht |
|---------|-----------|-------|----------|---------|
| Unit + Integration | `test_*.py` (Baseline) | 335 | ~3 min | ✅ |
| Property-Based (Recognizer) | `test_property_recognizers.py` | 28 | ~45 s | ✅ |
| Round-Trip-Property | `test_property_roundtrip.py` | 6 | ~90 s | ✅ |
| Fuzz (Format-Parser) | `test_fuzz_pipelines.py` | 12 | ~3 min | ✅ |
| Security (excessive) | `test_security_excessive.py` | 15 | ~30 s | ✅ |
| Stress | `test_stress.py` | 6 | ~5–6 min | `@slow` opt-in |

**Gesamt:** ≥ 400 Tests, alle grün.

## Voraussetzungen

```bash
pip install -e .[dev]
pip install hypothesis sqlcipher3-wheels  # für Property/Fuzz/Stress + SQLCipher
```

## Befehle

### Standard-Lauf (skip slow)

```bash
python -m pytest -m "not slow" -q
```

Dauer: ~7 min auf einem Standard-Entwicklerrechner.

### Voller Lauf inkl. Stress

```bash
python -m pytest -q
```

Dauer: ~12–15 min.

### Coverage-Report

```bash
python -m pytest -m "not slow" --cov=src/pseudokrat --cov-branch --cov-report=term --cov-report=html
```

Erzeugt `htmlcov/index.html`.

### Nur Property-Based-Tests

```bash
python -m pytest tests/test_property_recognizers.py tests/test_property_roundtrip.py -q
```

### Nur Security-Tests

```bash
python -m pytest tests/test_security_excessive.py tests/test_sqlcipher_backend.py -q
```

### Tests gegen einen bestimmten Hypothesis-Seed reproduzieren

Wenn Hypothesis einen Counter-Example findet, schreibt es eine
Reproduktions-Anweisung in den Fehler-Output, z. B.:

```
You can reproduce this failure by adding @seed(170531794421892651276460923750296000782)
or by running pytest with --hypothesis-seed=170531794421892651276460923750296000782.
```

## Test-Kategorien im Detail

### 1. Property-Based-Tests (Hypothesis)

Statt feste Beispiele zu prüfen, generieren wir **gültige** IDs algorithmisch
(Prüfziffer-Berechnung pro Standard) und lassen Hypothesis 200+ Beispiele pro
Recognizer probieren.

Geprüfte Invarianten:

- Jede algorithmisch erzeugte gültige ID wird vom Recognizer akzeptiert.
- Eine geflippte Prüfziffer macht die ID in ≥ 9 von 10 Flip-Varianten ungültig.
- Der Recognizer extrahiert die ID korrekt aus umschließendem Text.
- Robustheit: Beliebiger Unicode-Text führt nie zum Crash.

### 2. Round-Trip-Property

`deanonymize(anonymize(text)) == text` muss für alle Texte gelten, die
ausschließlich PII + neutralen Glue enthalten. Hypothesis generiert solche
Texte und prüft die Identität.

**Bug-Funde dieser Schicht:**

- **D-032** — Fuzzy-Merge griff irrtümlich auch bei numerischen IDs.
  `ATU00000015` und `ATU00000006` haben Levenshtein-Distanz 2 → wurden auf
  denselben Platzhalter gemerged → Reverse-Lookup lieferte für die zweite
  ID fälschlich die erste zurück. Fix: Fuzzy-Merging nur für textuelle
  Kategorien (COMPANY, ORG, PERSON, ADDRESS).

- **D-033** — IBAN-Regex matchte über die korrekte Länge hinaus, wenn nach
  einer gültigen IBAN direkt ein alphanumerisches Zeichen folgte. Die
  Längenprüfung schlug dann an, der Recognizer verfehlte aber den valide
  IBAN-Treffer. Fix: länderspezifische exakte Pattern + Negative-Lookahead.

### 3. Fuzz-Tests

Generative File-IO-Tests für TXT- und CSV-Pipelines. Prüfen:

- Beliebiger UTF-8-Input → Round-Trip ohne Datenverlust.
- Binärbytes → graceful failure (kein Crash).
- Format-Dispatcher: unbekannte Endung → `UnsupportedFormatError`.
- Realistische Multiline-Dokumente mit mehreren PII-Sorten round-tripen sauber.
- Unbekannte Platzhalter im Input bleiben unverändert (kein Phantom-Replace).

### 4. Security-Tests (excessive)

- PBKDF2-Iterationen ≥ 256.000.
- `derive_keys` ist deterministisch (gleiches Passwort+Salt → gleiche Keys).
- Verschiedene Passwörter / Salts → verschiedene Keys.
- Falsches Master-Passwort → `InvalidPasswordError`.
- Fehlende oder manipulierte Salt-Datei → `InvalidPasswordError`.
- Audit-Log-Hash-Chain erkennt: gelöschte Zeile, modifizierte Zeile,
  manipulierten `this_hash`.
- Originaltexte landen NICHT plaintext im SQLite-File.
- Audit-Log-Einträge enthalten keine Originaltexte oder IBANs.
- Wiederöffnen mit korrektem Passwort liefert dieselben Platzhalter
  (stabile Mappings über Sessions hinweg).
- Verifikations-Token-Manipulation → Open scheitert.

### 5. Stress-Tests (@slow)

Skip mit `pytest -m "not slow"`. Bei vollem Lauf prüfen:

- 2.000-Zeilen-Dokument mit unique UIDs round-trip-perfekt + < 120 s.
- 1.000 distinct Mandanten → 1.000 distinct Platzhalter.
- Eine Entität 2.000-mal → ein einziger Platzhalter (Konsistenz).
- Mixed PII (500 IBANs + 500 UIDs + 500 USt-IdNrs) → konsistente Mappings.
- XLSX 1.000 Zeilen / 5 Mandanten / Formel-String-Literale → § 12.7.
- Audit-Log mit 1.000 Einträgen → Hash-Chain bleibt valide.

## Hypothesis-Tuning

`max_examples` ist pro Klasse abgestimmt:

- `HYP_SETTINGS` (Recognizer-Property-Tests) — 200 Beispiele.
- `HYP_SETTINGS` (Round-Trip) — 80 Beispiele (Pipeline ist teurer).
- `FUZZ_SETTINGS` — 50 Beispiele (File-IO).
- `FAST_FUZZ_SETTINGS` — 120 Beispiele (rein in-memory).

Erhöhe für gründlichere Suche lokal über
`HYPOTHESIS_PROFILE=ci pytest …` (siehe `tests/conftest.py`).

## Bekannte Bugs durch Tests entdeckt

| Bug | Fundort | Fix in |
|-----|---------|--------|
| Fuzzy-Merge kollabiert numerische IDs | `test_property_roundtrip.py` | `D-032`, `fuzzy.py` |
| IBAN-Regex over-matched in nachfolgende Alphanumerik | `test_property_roundtrip.py` | `D-033`, `recognizers/iban.py` |
| O(n²)-Linear-Scan in `find_by_original` für Exact-Match-Kategorien | Stress-Lauf | `mapping_store.py` — Skip Fuzzy-Scan für non-fuzzy-Kategorien |

## CI-Konfiguration

Empfohlene Job-Matrix:

| Job | Befehl | Frequenz |
|-----|--------|----------|
| `quick` | `pytest -m "not slow" --maxfail=3` | jedes Push |
| `full` | `pytest --maxfail=3` | nightly / pre-release |
| `coverage` | `pytest -m "not slow" --cov=... --cov-fail-under=85` | jedes Push |
| `lint` | `ruff check src tests && mypy --strict src` | jedes Push |
| `security` | `bandit -r src && pip-audit` | jedes Push |
