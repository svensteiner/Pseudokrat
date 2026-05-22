"""Tests für CompanyLegalFormRecognizer."""

from __future__ import annotations

from pseudokrat.recognizers.base import Span
from pseudokrat.recognizers.company import (
    CompanyLegalFormRecognizer,
    detect_legal_form_suffix,
)


def test_finds_simple_company() -> None:
    recognizer = CompanyLegalFormRecognizer()
    spans = recognizer.analyze("Wir arbeiten mit der Hofer Bau GmbH zusammen.")
    assert len(spans) == 1
    assert spans[0].text == "Hofer Bau GmbH"
    assert spans[0].category == "COMPANY"


def test_finds_complex_legal_form() -> None:
    recognizer = CompanyLegalFormRecognizer()
    spans = recognizer.analyze("Beauftragt wurde die Müller Söhne GmbH & Co. KG.")
    assert len(spans) == 1
    assert "GmbH & Co. KG" in spans[0].text


def test_prefers_longest_legal_form_when_overlapping() -> None:
    recognizer = CompanyLegalFormRecognizer()
    spans = recognizer.analyze("Vertragspartner: Acme GmbH & Co. KG.")
    assert len(spans) == 1
    assert spans[0].text.endswith("GmbH & Co. KG")


def test_finds_multiple_companies_in_text() -> None:
    recognizer = CompanyLegalFormRecognizer()
    spans = recognizer.analyze("Die Hofer GmbH und die Müller AG sind Partner.")
    forms = sorted(s.text for s in spans)
    assert forms == ["Hofer GmbH", "Müller AG"]


def test_detect_legal_form_suffix_known() -> None:
    assert detect_legal_form_suffix("Hofer Bau GmbH & Co. KG") == "GmbH & Co. KG"
    assert detect_legal_form_suffix("Müller AG") == "AG"
    assert detect_legal_form_suffix("Random Limited") == "Limited"


def test_detect_legal_form_suffix_unknown_returns_none() -> None:
    assert detect_legal_form_suffix("Hofer Bau") is None
    assert detect_legal_form_suffix("Etwas GmbH-Abteilung") is None  # kein Leerzeichen vor "GmbH"


def test_dedupe_longest_replaces_shorter() -> None:
    """Bei Überlappung gewinnt der längere Span — auch wenn der kürzere zuerst kommt."""
    spans = [
        Span(start=0, end=10, category="COMPANY", text="Hofer GmbH", score=0.8),
        Span(start=0, end=24, category="COMPANY", text="Hofer GmbH & Co. KG", score=0.8),
    ]
    deduped = CompanyLegalFormRecognizer._dedupe_longest(spans)
    assert len(deduped) == 1
    assert deduped[0].end == 24


def test_dedupe_longest_empty_input() -> None:
    assert CompanyLegalFormRecognizer._dedupe_longest([]) == []
