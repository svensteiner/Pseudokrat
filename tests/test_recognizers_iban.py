"""Tests für den IBAN-Recognizer."""

from __future__ import annotations

import pytest

from pseudokrat.recognizers.iban import IBANDachRecognizer, is_valid_iban

# Bekannte Test-IBANs (öffentlich publiziert).
VALID_AT = "AT611904300234573201"
VALID_DE = "DE89370400440532013000"
VALID_CH = "CH9300762011623852957"


@pytest.mark.parametrize("iban", [VALID_AT, VALID_DE, VALID_CH])
def test_is_valid_iban_accepts_canonical_examples(iban: str) -> None:
    assert is_valid_iban(iban)


@pytest.mark.parametrize(
    "iban",
    [
        "AT611904300234573200",  # Prüfziffer zerstört
        "DE89370400440532013001",
        "CH0000000000000000000",
        "XX12345678901234567890",  # Falsches Länderkürzel
        "AT12 1200",  # Zu kurz
    ],
)
def test_is_valid_iban_rejects_invalid(iban: str) -> None:
    assert not is_valid_iban(iban)


def test_recognizer_finds_iban_in_text() -> None:
    recognizer = IBANDachRecognizer()
    text = f"Bitte überweise auf {VALID_AT} (Hauptkonto)."
    spans = recognizer.analyze(text)
    assert len(spans) == 1
    assert spans[0].text == VALID_AT
    assert spans[0].category == "IBAN"


def test_recognizer_handles_iban_with_spaces() -> None:
    recognizer = IBANDachRecognizer()
    # Banking-typische Gruppierung von vier Zeichen
    spaced = "AT61 1904 3002 3457 3201"
    spans = recognizer.analyze(f"Konto: {spaced} ")
    assert len(spans) == 1
    assert spans[0].text == spaced


def test_recognizer_skips_invalid_iban_in_text() -> None:
    recognizer = IBANDachRecognizer()
    bad = "AT99 9999 9999 9999 9999"
    spans = recognizer.analyze(f"Falsche IBAN {bad}")
    assert spans == []
