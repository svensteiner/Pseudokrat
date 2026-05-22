"""Tests für konfigurierbaren Mandanten-Nummern-Recognizer."""

from __future__ import annotations

import re

from pseudokrat.recognizers.mandanten_nr import MandantenNummerRecognizer


def test_mandanten_nr_string_pattern_detects_matches() -> None:
    rec = MandantenNummerRecognizer(r"M-\d{5}")
    text = "Bitte beachten: Mandant M-12345 und M-67890 sind betroffen."
    spans = rec.analyze(text)
    assert {s.text for s in spans} == {"M-12345", "M-67890"}
    assert all(s.category == "MANDANT_NR" for s in spans)
    assert all(0 < s.score <= 1 for s in spans)


def test_mandanten_nr_compiled_pattern_accepted() -> None:
    compiled = re.compile(r"MND_\d{4}-[A-Z]{2}")
    rec = MandantenNummerRecognizer(compiled, score=0.95)
    spans = rec.analyze("Akte MND_4711-AT wurde aktualisiert.")
    assert len(spans) == 1
    assert spans[0].text == "MND_4711-AT"
    assert spans[0].score == 0.95


def test_mandanten_nr_no_matches_returns_empty() -> None:
    rec = MandantenNummerRecognizer(r"X-\d+")
    assert rec.analyze("Nichts hier zu sehen.") == []


def test_mandanten_nr_position_correct() -> None:
    rec = MandantenNummerRecognizer(r"\bMND-\d+\b")
    text = "Vor MND-42 nach."
    spans = rec.analyze(text)
    assert len(spans) == 1
    span = spans[0]
    assert text[span.start : span.end] == "MND-42"
