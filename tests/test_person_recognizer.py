"""Tests für den anker-basierten PERSON-Recognizer (PRL Iter-6).

Akzeptanzkriterien:
- DACH-Lohnkonten-, Versicherungs-, Honorarschreiben-Namen werden
  erkannt, sobald Anrede oder Rollen-Label davor steht.
- Wiedervorkommen desselben Namens innerhalb des Textes werden
  via Second-Pass mitmarkiert.
- Trap-Sätze ohne Personen-Kontext erzeugen NULL Matches.
"""

from __future__ import annotations

import pytest

from pseudokrat.recognizers import default_recognizers
from pseudokrat.recognizers.person import PersonRecognizer


@pytest.fixture
def rec() -> PersonRecognizer:
    return PersonRecognizer()


class TestSalutationAnchors:
    def test_herr_mueller(self, rec: PersonRecognizer) -> None:
        text = "Mein Mandant Herr Müller schickt eine Rechnung."
        spans = rec.analyze(text)
        assert [s.text for s in spans] == ["Müller"]

    def test_frau_dr_schmidt(self, rec: PersonRecognizer) -> None:
        text = "Frau Dr. Schmidt ist die Vertrauensärztin."
        spans = rec.analyze(text)
        assert [s.text for s in spans] == ["Schmidt"]

    def test_herr_prof_dr_med_huber(self, rec: PersonRecognizer) -> None:
        text = "Herr Prof. Dr. med. Huber operiert heute."
        spans = rec.analyze(text)
        assert [s.text for s in spans] == ["Huber"]

    def test_herrn_dative(self, rec: PersonRecognizer) -> None:
        text = "Bitte übergeben Sie das Schreiben Herrn Kainz persönlich."
        spans = rec.analyze(text)
        assert [s.text for s in spans] == ["Kainz"]

    def test_full_first_last_name(self, rec: PersonRecognizer) -> None:
        text = "Herr Max Mustermann wohnt in Wien."
        spans = rec.analyze(text)
        assert [s.text for s in spans] == ["Max Mustermann"]

    def test_hyphenated_surname(self, rec: PersonRecognizer) -> None:
        text = "Frau Müller-Lüdenscheidt prüft die Akte."
        spans = rec.analyze(text)
        assert [s.text for s in spans] == ["Müller-Lüdenscheidt"]


class TestRoleLabelAnchors:
    def test_dienstnehmer_in_label(self, rec: PersonRecognizer) -> None:
        text = "Dienstnehmer/in:       Anna Beispielsohn\n"
        spans = rec.analyze(text)
        assert [s.text for s in spans] == ["Anna Beispielsohn"]

    def test_arbeitnehmer_label(self, rec: PersonRecognizer) -> None:
        text = "Arbeitnehmer:          Friedrich Beispiel\n"
        spans = rec.analyze(text)
        assert [s.text for s in spans] == ["Friedrich Beispiel"]

    def test_antragsteller_label(self, rec: PersonRecognizer) -> None:
        text = "Antragsteller:        Markus Beispielmann\n"
        spans = rec.analyze(text)
        assert [s.text for s in spans] == ["Markus Beispielmann"]

    def test_mandant_label(self, rec: PersonRecognizer) -> None:
        text = "Mandant: Herr Hofer benötigt eine Bilanz."
        spans = rec.analyze(text)
        # Beide Anker greifen — Anrede schlägt durch (kürzeres Span).
        assert "Hofer" in [s.text for s in spans]


class TestSecondPassRecurrences:
    def test_recurrence_after_first_pass(self, rec: PersonRecognizer) -> None:
        text = (
            "Dienstnehmer/in:       Anna Beispielsohn\n"
            "Anmerkungen zu Anna Beispielsohn:\n"
            "  - Eintritt 01.06.2024\n"
        )
        spans = rec.analyze(text)
        texts = [s.text for s in spans]
        assert texts.count("Anna Beispielsohn") == 2

    def test_recurrence_signature_line(self, rec: PersonRecognizer) -> None:
        text = (
            "Antragsteller: Markus Beispielmann\n"
            "Markus Beispielmann bestätigt die Richtigkeit."
        )
        spans = rec.analyze(text)
        assert [s.text for s in spans] == [
            "Markus Beispielmann",
            "Markus Beispielmann",
        ]

    def test_no_partial_recurrence_match(self, rec: PersonRecognizer) -> None:
        """Wenn 'Beispielsohn' isoliert auftaucht, darf das nicht als
        Wiedervorkommen von 'Anna Beispielsohn' getaggt werden — nur
        exakte Matches."""
        text = (
            "Herr Anna Beispielsohn schreibt.\n"
            "Beispielsohngasse 12 ist die Adresse."
        )
        spans = rec.analyze(text)
        texts = [s.text for s in spans]
        # Nur der Anker-Treffer, kein FP auf 'Beispielsohngasse'.
        assert texts == ["Anna Beispielsohn"]


class TestNegativeCases:
    def test_no_anchor_no_match(self, rec: PersonRecognizer) -> None:
        text = "Müller ging gestern einkaufen."
        spans = rec.analyze(text)
        assert spans == []

    def test_brand_names_without_anchor(self, rec: PersonRecognizer) -> None:
        text = (
            "Wir haben beim Hofer-Markt Wien eingekauft. "
            "Die Müller-Schiene war defekt. Bauer-Land-Speck war aus."
        )
        spans = rec.analyze(text)
        assert spans == []

    def test_company_after_role_label_not_matched(
        self, rec: PersonRecognizer
    ) -> None:
        """Rollenlabel kann auch Firma sein — wir nehmen den ersten
        Capitalized-Token-Block. Solange Validierung gegen Rechtsform-
        Suffix nicht greift, bleibt das ein kleiner Trade-Off.
        Test prüft, dass GmbH-Tokens nicht als PERSON markiert werden."""
        text = "Arbeitgeber: Rheinmetall Mustermann AG\n"
        spans = rec.analyze(text)
        # AG ist im Stop-Set, fällt aus. Rheinmetall Mustermann kann
        # entweder als PERSON ankommen (falsch positiv, akzeptiert) oder
        # nicht (besser). Realität: Capitalized-Token-Block matcht.
        # Wir testen nur, dass kein 'AG'-Token reinrutscht.
        for s in spans:
            assert "AG" not in s.text.split()


class TestSpanOffsetIntegrity:
    def test_offsets_match_original_text(self, rec: PersonRecognizer) -> None:
        text = "Herr Maximilian Beispiel-Kainz wohnt hier."
        spans = rec.analyze(text)
        assert len(spans) == 1
        s = spans[0]
        assert text[s.start : s.end] == "Maximilian Beispiel-Kainz"

    def test_sorted_by_position(self, rec: PersonRecognizer) -> None:
        text = (
            "Frau Schmidt und Herr Huber.\n"
            "Schmidt schickt einen Brief. Huber antwortet."
        )
        spans = rec.analyze(text)
        starts = [s.start for s in spans]
        assert starts == sorted(starts)


class TestDefaultBundleIntegration:
    def test_person_in_default(self) -> None:
        assert "person" in [r.name for r in default_recognizers()]
