# Production-Ready Gate

> **Was muss erfüllt sein, damit Pseudokrat als „produktionsreif" gilt?**
> Diese Datei definiert die objektive Schwelle. Der Production-Readiness-
> Loop (PRL) misst gegen sie, prioriziert die offenste Lücke, schließt sie,
> misst erneut. Iteriert wird, bis alle Bedingungen `pass` sind.

## Tier-1 — Erkennungs-Qualität (Eval)

Quelle: `tests/eval/` Fixtures, Auswertung via `tools/eval_run.py`.

| Kategorie | F1 (min) | Begründung |
|---|---|---|
| `PERSON` | **0.95** | Personennamen sind das Killer-Feature. Fehler hier heißt: Mandant im Cloud-KI-Chat. |
| `ORG` | **0.95** | Firmen-Namen ähnlich kritisch — Kanzlei-Kontext. |
| `IBAN` | **1.00** | Recognizer ist deterministisch (Mod-97-Prüfziffer). Jeder Miss ist ein Bug. |
| `SVNR` | **1.00** | Algorithmisch (Mod-11). Deterministisch. |
| `TAX_ID` | **1.00** | Algorithmisch (§ 139b AO). Deterministisch. |
| `UID` | **1.00** | Algorithmisch. Deterministisch. |
| `EMAIL` | **1.00** | Regex-deterministisch. |
| `ADDRESS` | **0.90** | Adressen sind formal weniger eindeutig; gewisse Toleranz erlaubt. |
| `DATE` | **0.85** | Datumserkennung muss zwischen Geburtsdatum (PII) und z. B. Rechnungsdatum (nicht PII) unterscheiden — schwierig, niedrigere Schwelle bewusst. |

**Falsch-Positiv-Rate über alle Kategorien:** `≤ 0.02` (max. 2 % der erkannten Spans dürfen Fehlalarme sein — sonst frustriert die Vorschau-UI den Nutzer mit ständigen manuellen Korrekturen).

## Tier-2 — Statische Qualität

| Check | Schwelle | Tool |
|---|---|---|
| Ruff Lint | 0 Errors | `ruff check src/ tests/` |
| Mypy Strict | 0 Errors | `mypy --strict src/pseudokrat` |
| Bandit (High) | 0 Findings | `bandit -r src/ -ll` |
| pip-audit | 0 known CVEs (high/critical) | `pip-audit --strict` |
| Pytest („not slow") | 100 % grün | `pytest -m "not slow"` |
| Coverage (Branches) | ≥ 80 % | `pytest --cov=src --cov-report=json` |

## Tier-3 — Trust-Boundary-Coverage

Quelle: `SELF_AUDIT.md` Abschnitte S1–S7.

Jede Trust-Boundary muss **mindestens einen** Test referenzieren, der ihren
Kontrakt verifiziert. Der Loop prüft per Heuristik: für jede `S<N>`-
Überschrift im Self-Audit muss ein Test in `tests/` existieren, der
`S<N>` im Docstring nennt **oder** der Schlüsselbegriff aus der Boundary-
Beschreibung im Test-Body trifft.

| Boundary | Aktueller Coverage-Status |
|---|---|
| S1 — Fuzzy-Merge-Side-Channel | covered (PRL iter-13) |
| S2 — Audit-Log-Manipulation | covered (PRL iter-13) |
| S3 — XLSX-Formula-Injection | covered (PRL iter-13) |
| S4 — Modell-Download | covered (PRL iter-13) |
| S5 — DP-Permutation | covered (PRL iter-13) |
| S6 — Simple-Mode / OS-Keyring | covered (PRL iter-13) |
| S7 — Windows-Registry-Integration | covered (PRL iter-13) |

> Quelle: `tools.audit_run` → `trust-boundary-coverage`. Titel-Liste
> stammt aus den `S<N> — …`-Überschriften in `SELF_AUDIT.md` und wird
> bei jeder PRL-Iteration automatisch geprüft.

## Tier-4 — Offene Folgearbeiten (DECISIONS.md)

Jede Decision in `DECISIONS.md` mit einem `**Folgearbeit:**`-Block muss
entweder:
- Erledigt sein (Folgearbeit-Block wird beim Schließen entfernt), **oder**
- Mit einer ADR-Pendant-Begründung verschoben sein (`**Vertagt nach X.Y:**`-
  Block, der den Trigger nennt, der die Folgearbeit reaktiviert).

Der PRL flaggt offene Folgearbeiten, schließt sie aber nicht automatisch —
hier ist menschliche Priorisierung gefragt.

## Tier-5 — Manueller Akzeptanztest (vor Release-Tag)

Diese Punkte sind **nicht** Teil des automatischen Gates, aber Pflicht
vor dem ersten signierten Release:

- [ ] `pseudokrat install` auf frischer Win11-VM ohne Pseudokrat-Vorinstallation: läuft durch ohne Admin-Prompt
- [ ] Explorer-Rechtsklick auf Test-Lohnkonto.pdf: erzeugt `Lohnkonto.anon.pdf` mit korrekt anonymisierten Namen
- [ ] GUI auf zweitem Account: erkennt den Simple-Default automatisch, Auto-Open funktioniert
- [ ] Hotkey Strg+Shift+A auf Word-Auswahl: Zwischenablage wird anonymisiert
- [ ] `pseudokrat uninstall`: Registry-Einträge weg, Profile noch da
- [ ] Externer Pentest-Report (Dritter, nicht ich) ohne unmitigated High-Severity-Findings

---

## PRL-Lebenszyklus

```
   ┌────────────────┐
   │ 1. Eval-Phase  │ → eval_report.json
   └────────┬───────┘
            │
   ┌────────▼───────┐
   │ 2. Audit-Phase │ → audit_report.md
   └────────┬───────┘
            │
   ┌────────▼───────┐
   │ 3. Gap-Phase   │ → next_gap.md (genau eine Lücke)
   └────────┬───────┘
            │
   ┌────────▼───────┐
   │ 4. Close-Phase │ → Commit, Push
   └────────┬───────┘
            │
            └─── Loop oder Stop wenn alles "pass" ───
```

Der Loop läuft autonom. Stopp-Bedingung: alle Tiers 1-4 erfüllt **oder**
manueller Abbruch.
