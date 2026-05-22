"""Tests für die AT-Sozialversicherungsnummer."""

from __future__ import annotations

import pytest

from pseudokrat.recognizers.at_svnr import AustrianSVNRRecognizer, is_valid_at_svnr

# Hergeleitete gültige Test-Nummer (4-stell. lfd.Nr. inkl. Prüfziffer + DDMMYY).
VALID_SVNR = "1242050195"  # Prüfziffer 2, geboren 05.01.95
VALID_SVNR_SPACED = "1242 050195"


@pytest.mark.parametrize("svnr", [VALID_SVNR, VALID_SVNR_SPACED])
def test_valid_svnr(svnr: str) -> None:
    assert is_valid_at_svnr(svnr)


@pytest.mark.parametrize(
    "svnr",
    [
        "1240050195",  # falsche Prüfziffer
        "1234567890",
        "123405019",  # zu kurz
    ],
)
def test_invalid_svnr(svnr: str) -> None:
    assert not is_valid_at_svnr(svnr)


def test_recognizer_finds_svnr() -> None:
    recognizer = AustrianSVNRRecognizer()
    text = f"SVNR: {VALID_SVNR}. Bitte für die Kammerumlage merken."
    spans = recognizer.analyze(text)
    assert len(spans) == 1
    assert spans[0].text == VALID_SVNR


def test_recognizer_finds_svnr_with_space() -> None:
    recognizer = AustrianSVNRRecognizer()
    text = f"SVNR {VALID_SVNR_SPACED} ist gespeichert."
    spans = recognizer.analyze(text)
    assert len(spans) == 1
    assert spans[0].text.replace(" ", "") == VALID_SVNR
