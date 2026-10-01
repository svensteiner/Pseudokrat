"""Tests für den BIC/SWIFT-Recognizer (ISO 9362)."""

from __future__ import annotations

import pytest

from pseudokrat.recognizers.bic import BICRecognizer, is_valid_bic


@pytest.mark.parametrize(
    "bic",
    [
        "DEUTDEFF",  # Deutsche Bank Frankfurt — 8-stellig
        "DEUTDEFFXXX",  # Deutsche Bank Frankfurt — 11-stellig
        "GIBAATWWXXX",  # Erste Bank Wien
        "UBSWCHZH80A",  # UBS Zürich
        "INGBDEFFXXX",  # ING-DiBa
        "BKAUATWW",  # Bank Austria
        "POFICHBEXXX",  # PostFinance Bern
        "RBOSGB2L",  # NatWest London
        "CHASUS33",  # JP Morgan Chase
    ],
)
def test_valid_real_bic_accepted(bic: str) -> None:
    assert is_valid_bic(bic)


@pytest.mark.parametrize(
    "not_bic",
    [
        "DEUTDEFFX",  # 9 Zeichen — ungültige Länge
        "DEUTDEFFXX",  # 10 Zeichen — ungültige Länge
        "DEUT",  # zu kurz
        "DEUTDEFFXXXXX",  # zu lang
        "deutdeff",  # lowercase
        "1234DEFFXXX",  # erste 4 keine Buchstaben
        "DEUT99FFXXX",  # Country-Stellen mit Ziffern
        "DEUTZZFF",  # ZZ ist kein gültiger ISO-3166-1-Alpha-2
        "SCHWEIZ",  # echtes Wort (7 Zeichen, falsche Länge)
        "PROFISTART",  # zufälliges Wort
    ],
)
def test_invalid_bic_rejected(not_bic: str) -> None:
    assert not is_valid_bic(not_bic)


def test_recognizer_extracts_bic_from_text() -> None:
    text = "Bitte überweisen Sie auf IBAN DE89 3704 0044 0532 0130 00 (BIC DEUTDEFFXXX)."
    spans = BICRecognizer().analyze(text)
    assert len(spans) == 1
    span = spans[0]
    assert span.category == "BIC"
    assert text[span.start : span.end] == "DEUTDEFFXXX"


def test_recognizer_filters_invalid_country_code() -> None:
    """Auch wenn das Regex matcht, soll ZZ als Country-Code rausfliegen."""
    text = "Fake-BIC: ABCDZZ12XXX in einer Mail."
    spans = BICRecognizer().analyze(text)
    assert spans == []


def test_recognizer_extracts_multiple_bics() -> None:
    text = "Empfänger BIC: DEUTDEFFXXX. Absender BIC: UBSWCHZH80A. Vermittler BIC: BKAUATWW."
    spans = BICRecognizer().analyze(text)
    extracted = [text[s.start : s.end] for s in spans]
    assert set(extracted) == {"DEUTDEFFXXX", "UBSWCHZH80A", "BKAUATWW"}


def test_recognizer_rejects_format_match_without_context_keyword() -> None:
    """ISO-9362-Format-Match ohne 'BIC'/'SWIFT' im 40-Zeichen-Fenster
    davor → kein Span. Kollisions-Schutz gegen Groß-Wörter wie
    NEUERUNG, DEUTSCHLAND."""
    text = "Die NEUERUNG bringt für DEUTSCHLAND einen Vorteil."
    spans = BICRecognizer().analyze(text)
    assert spans == []


def test_recognizer_no_false_positives_in_paragraph() -> None:
    """Falle: Großbuchstaben-Cluster, die zufällig eine BIC-Länge haben."""
    text = (
        "Die ABTEILUNG für DATENSCHUTZ informiert: Unsere AGB enthalten "
        "Klauseln zu DSGVO und GDPR. Die NEUERUNG GILT AB JANUAR.\n"
        "Wichtig: SCHWEIZ und DEUTSCHLAND sind getrennt.\n"
    )
    spans = BICRecognizer().analyze(text)
    # Die 8-Zeichen-Wörter "ABTEILUN" (substring), etc. sollten nicht matchen,
    # weil der Country-Code nicht stimmt. "DSGVOJAN" o. ä. ebenfalls.
    extracted = [text[s.start : s.end] for s in spans]
    assert extracted == [], f"False Positives: {extracted}"


def test_recognizer_handles_word_boundary() -> None:
    """BIC am Anfang/Ende eines Wortes wird erkannt; verschmolzen nicht.
    Mit Kontext-Keyword 'BIC ' davor, damit der Context-Guard nicht greift."""
    text_a = "BIC DEUTDEFFXXX"  # nichts drumherum (außer Keyword)
    text_b = "BIC: DEUTDEFFXXX "  # mit Doppelpunkt
    text_c = "BIC DEUTDEFFXXXSUFFIX"  # angehängter Müll → soll NICHT matchen
    assert len(BICRecognizer().analyze(text_a)) == 1
    assert len(BICRecognizer().analyze(text_b)) == 1
    assert len(BICRecognizer().analyze(text_c)) == 0
