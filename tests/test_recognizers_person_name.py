"""Tests für den Vornamen-Listen-PERSON-Recognizer (Gazetteer, ML-frei).

Akzeptanzkriterien:
- Nackte 'Vorname Nachname' (z. B. in Tabellenzellen) werden erkannt.
- Unbekannte Vornamen erzeugen keinen Match (konservativ).
- Klein geschriebene Funktionswörter werden nicht maskiert.
"""

from __future__ import annotations

import pytest

from pseudokrat.recognizers.person_name import FIRST_NAMES, GazetteerNameRecognizer


@pytest.fixture
def rec() -> GazetteerNameRecognizer:
    return GazetteerNameRecognizer()


class TestGazetteerName:
    def test_bare_firstname_lastname(self, rec: GazetteerNameRecognizer) -> None:
        spans = rec.analyze("Thomas Bauer")
        assert [s.text for s in spans] == ["Thomas Bauer"]
        assert spans[0].category == "PERSON"

    def test_in_table_cell_context(self, rec: GazetteerNameRecognizer) -> None:
        spans = rec.analyze("Ansprechpartner Eva Eder ist zustaendig.")
        assert any(s.text == "Eva Eder" for s in spans)

    def test_double_surname_or_middle_name(self, rec: GazetteerNameRecognizer) -> None:
        spans = rec.analyze("Anna Maria Huber")
        assert spans and spans[0].text == "Anna Maria Huber"

    def test_hyphenated_surname(self, rec: GazetteerNameRecognizer) -> None:
        spans = rec.analyze("Julia Müller-Lüdenscheidt")
        assert spans and spans[0].text == "Julia Müller-Lüdenscheidt"

    def test_unknown_firstname_no_match(self, rec: GazetteerNameRecognizer) -> None:
        assert rec.analyze("Xyzzy Bauer") == []

    def test_lowercase_not_a_name(self, rec: GazetteerNameRecognizer) -> None:
        assert rec.analyze("die rechnung wurde bezahlt") == []

    def test_score_is_low_priority(self, rec: GazetteerNameRecognizer) -> None:
        spans = rec.analyze("Markus Gruber")
        assert spans[0].score == pytest.approx(0.6)

    def test_first_names_are_lowercase(self) -> None:
        assert all(n == n.lower() for n in FIRST_NAMES)
        assert len(FIRST_NAMES) > 200
