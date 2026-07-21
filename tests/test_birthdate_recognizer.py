"""Tests für den kontext-gesteuerten Geburtsdatum-Recognizer.

Kerngedanke: ``BirthDateRecognizer`` darf nur dann ein Datum melden,
wenn unmittelbar davor ein Geburts-Kontext-Label steht. Datums-
Vorkommen ohne Kontext (Eintrittsdatum, Bericht-Datum, Erstellungs-
Datum) bleiben **unangetastet** — andernfalls würden Kanzleien mit
FP-Schwemme begraben.
"""

from __future__ import annotations

import pytest

from pseudokrat.recognizers import default_recognizers
from pseudokrat.recognizers.birthdate import BirthDateRecognizer


@pytest.fixture
def recognizer() -> BirthDateRecognizer:
    return BirthDateRecognizer()


class TestBirthDateRecognizer:
    """Positive Cases — Datum MUSS erkannt werden."""

    def test_geburtsdatum_label_dd_mm_yyyy_at(self, recognizer: BirthDateRecognizer) -> None:
        text = "Geburtsdatum:          15.03.1985"
        spans = recognizer.analyze(text)
        assert len(spans) == 1
        assert spans[0].text == "15.03.1985"
        assert spans[0].category == "DATE"

    def test_geburtsdatum_label_dd_mm_yyyy_de(self, recognizer: BirthDateRecognizer) -> None:
        text = "Geburtsdatum:          07.11.1978"
        spans = recognizer.analyze(text)
        assert [s.text for s in spans] == ["07.11.1978"]

    def test_geburtsdatum_label_dd_mm_yyyy_ch(self, recognizer: BirthDateRecognizer) -> None:
        text = "Geburtsdatum:         22.08.1972"
        spans = recognizer.analyze(text)
        assert [s.text for s in spans] == ["22.08.1972"]

    def test_geboren_am_variant(self, recognizer: BirthDateRecognizer) -> None:
        text = "Der Mandant ist geboren am 12.06.1990 in München."
        spans = recognizer.analyze(text)
        assert [s.text for s in spans] == ["12.06.1990"]

    def test_dob_label(self, recognizer: BirthDateRecognizer) -> None:
        text = "DOB: 1985-03-15"
        spans = recognizer.analyze(text)
        assert [s.text for s in spans] == ["1985-03-15"]

    def test_date_of_birth_with_em_dash(self, recognizer: BirthDateRecognizer) -> None:
        text = "Date of Birth — 07.11.1978"
        spans = recognizer.analyze(text)
        assert [s.text for s in spans] == ["07.11.1978"]

    def test_iso_format_after_label(self, recognizer: BirthDateRecognizer) -> None:
        text = "Geburtsdatum: 1990-01-31"
        spans = recognizer.analyze(text)
        assert [s.text for s in spans] == ["1990-01-31"]

    def test_geb_punkt_short_label(self, recognizer: BirthDateRecognizer) -> None:
        text = "geb. 01.02.1980 in Wien"
        spans = recognizer.analyze(text)
        assert [s.text for s in spans] == ["01.02.1980"]


class TestBirthDateRecognizerNegativeCases:
    """Negative Cases — Datum darf NICHT erkannt werden ohne Kontext."""

    def test_eintrittsdatum_is_not_birth(self, recognizer: BirthDateRecognizer) -> None:
        text = "Eintrittsdatum: 01.06.2024 — Pendlerpauschale aktiv."
        spans = recognizer.analyze(text)
        assert spans == []

    def test_erstellungsdatum_is_not_birth(self, recognizer: BirthDateRecognizer) -> None:
        text = "Erstellt am 31.01.2026 von der Lohnverrechnung."
        spans = recognizer.analyze(text)
        assert spans == []

    def test_bare_date_in_text(self, recognizer: BirthDateRecognizer) -> None:
        text = "Der Bericht wurde am 15.05.2025 abgeschlossen."
        spans = recognizer.analyze(text)
        assert spans == []

    def test_label_with_intervening_words(self, recognizer: BirthDateRecognizer) -> None:
        """Wenn ein Volltextsatz zwischen Label und Datum steht — kein Match."""
        text = "Geburtsdatum ist nicht relevant. Stattdessen 15.03.1985 als Stichtag."
        spans = recognizer.analyze(text)
        assert spans == []

    def test_invalid_day_rejected(self, recognizer: BirthDateRecognizer) -> None:
        text = "Geburtsdatum: 32.01.1985"
        spans = recognizer.analyze(text)
        assert spans == []

    def test_invalid_month_rejected(self, recognizer: BirthDateRecognizer) -> None:
        text = "Geburtsdatum: 15.13.1985"
        spans = recognizer.analyze(text)
        assert spans == []

    def test_two_digit_year_rejected(self, recognizer: BirthDateRecognizer) -> None:
        """Zwei-stelliges Jahr ist mehrdeutig — wir matchen nur 4-stellig."""
        text = "Geburtsdatum: 15.03.85"
        spans = recognizer.analyze(text)
        assert spans == []

    def test_label_too_far_away(self, recognizer: BirthDateRecognizer) -> None:
        """Über >40 Zeichen Abstand vertrauen wir der Zuordnung nicht."""
        gap = " " * 50
        text = f"Geburtsdatum:{gap}15.03.1985"
        spans = recognizer.analyze(text)
        assert spans == []

    def test_no_label_no_match(self, recognizer: BirthDateRecognizer) -> None:
        text = "15.03.1985 ist ein Datum."
        spans = recognizer.analyze(text)
        assert spans == []


class TestSpanOffsets:
    """Span-Offsets müssen 1:1 in den Originaltext zurückgreifen."""

    def test_offsets_match_original_text(self, recognizer: BirthDateRecognizer) -> None:
        text = "Geburtsdatum: 15.03.1985 — Steuerberater"
        spans = recognizer.analyze(text)
        assert len(spans) == 1
        s = spans[0]
        assert text[s.start : s.end] == "15.03.1985"

    def test_multiple_birthdates_in_one_text(self, recognizer: BirthDateRecognizer) -> None:
        text = "Ehefrau: Geburtsdatum 01.02.1985.\nEhemann: Geburtsdatum 03.04.1980."
        spans = recognizer.analyze(text)
        texts = [s.text for s in spans]
        assert texts == ["01.02.1985", "03.04.1980"]


class TestDefaultBundleIntegration:
    """Recognizer ist im Default-Bundle enthalten."""

    def test_birthdate_recognizer_in_default(self) -> None:
        names = [r.name for r in default_recognizers()]
        assert "birthdate" in names
