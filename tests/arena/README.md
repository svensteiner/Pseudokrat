# Pseudokrat Testarena — Zero-Leak-Nachweis

Ein gegnerischer Belastungstest, der beweist, dass die Anonymisierung
**wirklich** anonymisiert — nicht nur auf bekannten Beispielen
(das macht `tests/eval/`), sondern auf tausenden neu erzeugten,
absichtlich schwierigen DACH-Dokumenten.

## Prinzip

1. **Ground Truth durch Konstruktion.** Jedes Dokument wird aus
   bekannten PII-Geheimnissen (Name, IBAN, SVNR, Steuer-ID …)
   zusammengebaut. Wir wissen also exakt, was verschwinden muss.
2. **Echte Pipeline.** Jedes Dokument läuft durch `default_recognizers()`
   wie im Produktivbetrieb.
3. **Leck-Tor.** Kein Geheimnis darf im Output überleben — verglichen in
   Normalform, sodass auch über Zeilenumbruch/Leerzeichen zerrissene
   Werte erkannt werden.
4. **Roundtrip.** De-Anonymisierung muss das Original exakt herstellen.
5. **Negativ-Kontrolle.** Beweist, dass das Tor ein echtes Leck auch
   findet (kein blind-grüner Test).

Härtegrade: realistische Modi (`clean`, `spacing`, `table`,
`labelbreak`) bilden das Pass/Fail-Tor; `reflow` (Wert mitten im Wort
umgebrochen) ist ein bewusster Extremfall und wird separat ausgewiesen.

## Großer Nachweis-Lauf

```bash
python -m tests.arena.runner --count 1500 --reflow-count 300 --out arena_report
```

Erzeugt `arena_report.md` (lesbarer Nachweis) und `arena_report.json`.
Exit-Code 1 bei einem Leck oder Roundtrip-Fehler im realistischen Korpus.

## Schnelles CI-Tor

```bash
pytest tests/arena/test_arena_zero_leak.py -q
```

## Auf andere Tools übertragen

Das Muster ist tool-unabhängig: **(a)** adversen Input mit bekannter
Ground Truth erzeugen, **(b)** echtes Tool laufen lassen, **(c)** eine
harte Invariante prüfen (hier: „kein Geheimnis überlebt"), **(d)**
Nachweis-Report + Negativ-Kontrolle. Für ein neues Tool werden nur der
Generator (`corpus.py`) und die Invariante (`leakcheck.py`) ersetzt.
