"""Tests für den DACH-Telefonnummern-Recognizer."""

from __future__ import annotations

import pytest

from pseudokrat.recognizers.phone import PhoneRecognizer


@pytest.fixture
def recognizer() -> PhoneRecognizer:
    return PhoneRecognizer()


@pytest.mark.parametrize(
    "phone",
    [
        "+49 30 12345678",
        "+43 1 1234567",
        "+41 44 123 45 67",
        "+49-89-12345678",
        "0049 30 12345678",
        "0043 1 1234567",
        "0041 44 1234567",
        "+49(30)12345678",
    ],
)
def test_international_formats(recognizer: PhoneRecognizer, phone: str) -> None:
    text = f"Rufen Sie uns an: {phone}, vielen Dank."
    spans = recognizer.analyze(text)
    assert len(spans) == 1
    assert spans[0].category == "PHONE"
    assert spans[0].text.strip() == phone.strip()


@pytest.mark.parametrize(
    "phone",
    [
        "0664 1234567",
        "030 12345678",
        "044/123 45 67",
    ],
)
def test_national_formats(recognizer: PhoneRecognizer, phone: str) -> None:
    text = f"Tel: {phone}"
    spans = recognizer.analyze(text)
    assert len(spans) == 1
    assert spans[0].category == "PHONE"


def test_ignores_short_or_unprefixed_numbers(recognizer: PhoneRecognizer) -> None:
    text = "Bestellnummer 12345 und Code 9876."
    assert recognizer.analyze(text) == []


def test_no_double_match_intl_and_national(recognizer: PhoneRecognizer) -> None:
    text = "Erreichbar unter +49 30 12345678"
    spans = recognizer.analyze(text)
    assert len(spans) == 1


def test_multiple_phones(recognizer: PhoneRecognizer) -> None:
    text = "AT: +43 1 1234567, DE: +49 30 12345678, CH: +41 44 1234567"
    spans = recognizer.analyze(text)
    assert len(spans) == 3
