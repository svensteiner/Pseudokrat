"""Tests für den DACH-ADDRESS-Recognizer (PRL Iter-7)."""

from __future__ import annotations

import pytest

from pseudokrat.recognizers import default_recognizers
from pseudokrat.recognizers.address import AddressRecognizer


@pytest.fixture
def rec() -> AddressRecognizer:
    return AddressRecognizer()


class TestPositiveCases:
    def test_at_address_with_compound_street(self, rec: AddressRecognizer) -> None:
        text = "Wohnadresse: Mariahilfer Straße 88, 1070 Wien"
        spans = rec.analyze(text)
        assert len(spans) == 1
        assert spans[0].text == "Mariahilfer Straße 88, 1070 Wien"
        assert spans[0].category == "ADDRESS"

    def test_at_address_compound_street_word(self, rec: AddressRecognizer) -> None:
        text = "Industriestraße 12, 4020 Linz"
        spans = rec.analyze(text)
        assert [s.text for s in spans] == ["Industriestraße 12, 4020 Linz"]

    def test_de_address_5digit_plz(self, rec: AddressRecognizer) -> None:
        text = "Werftstraße 22, 40549 Düsseldorf"
        spans = rec.analyze(text)
        assert [s.text for s in spans] == ["Werftstraße 22, 40549 Düsseldorf"]

    def test_de_allee_suffix(self, rec: AddressRecognizer) -> None:
        text = "Königsallee 47, 40212 Düsseldorf"
        spans = rec.analyze(text)
        assert [s.text for s in spans] == ["Königsallee 47, 40212 Düsseldorf"]

    def test_ch_bahnhofstrasse_4digit_plz(self, rec: AddressRecognizer) -> None:
        text = "Bahnhofstrasse 14, 8001 Zürich"
        spans = rec.analyze(text)
        assert [s.text for s in spans] == ["Bahnhofstrasse 14, 8001 Zürich"]

    def test_house_number_with_letter(self, rec: AddressRecognizer) -> None:
        text = "Hauptplatz 12a, 4020 Linz"
        spans = rec.analyze(text)
        assert [s.text for s in spans] == ["Hauptplatz 12a, 4020 Linz"]

    def test_at_stiege_notation(self, rec: AddressRecognizer) -> None:
        text = "Mariahilfer Straße 12/3, 1070 Wien"
        spans = rec.analyze(text)
        assert [s.text for s in spans] == ["Mariahilfer Straße 12/3, 1070 Wien"]


class TestNegativeCases:
    def test_incomplete_address_no_plz(self, rec: AddressRecognizer) -> None:
        """Goethestraße 5 ohne PLZ und Ort darf nicht matchen."""
        text = "Goethestraße 5 (ohne PLZ und Ort)"
        spans = rec.analyze(text)
        assert spans == []

    def test_street_only_no_match(self, rec: AddressRecognizer) -> None:
        text = "Die Mariahilfer Straße ist eine Einkaufsmeile."
        spans = rec.analyze(text)
        assert spans == []

    def test_plain_text_no_match(self, rec: AddressRecognizer) -> None:
        text = "Lieber Mandant, anbei die Auswertung."
        spans = rec.analyze(text)
        assert spans == []

    def test_fp_traps_fixture_clean(self, rec: AddressRecognizer) -> None:
        text = (
            "Wir haben heute beim Hofer-Markt Wien eingekauft.\n"
            "Eine IBAN-Anleitung ohne konkrete IBAN.\n"
            "DE12 ist keine Steuer-ID.\n"
            "Ein Test mit Goethestraße 5 (ohne PLZ und Ort) sollte nicht "
            "als vollständige Adresse durchgehen.\n"
        )
        spans = rec.analyze(text)
        assert spans == []


class TestSpanOffsetIntegrity:
    def test_offsets_match_original_text(self, rec: AddressRecognizer) -> None:
        text = "Adresse: Werftstraße 22, 40549 Düsseldorf — bitte zustellen."
        spans = rec.analyze(text)
        assert len(spans) == 1
        s = spans[0]
        assert text[s.start : s.end] == "Werftstraße 22, 40549 Düsseldorf"


class TestDefaultBundleIntegration:
    def test_address_in_default(self) -> None:
        assert "address" in [r.name for r in default_recognizers()]
