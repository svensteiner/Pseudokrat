"""Tests für DE-Steuer-ID und DE-USt-IdNr."""

from __future__ import annotations

import pytest

from pseudokrat.recognizers.de_steuer_id import (
    GermanSteuerIdRecognizer,
    is_valid_de_steuer_id,
)
from pseudokrat.recognizers.de_ust_id import (
    GermanUStIdNrRecognizer,
    is_valid_de_ust_id,
)

# Offizielles BMF-Beispiel
VALID_STEUER_ID = "47036892816"

# Bekannte gültige USt-ID
VALID_UST_ID = "DE136695976"


@pytest.mark.parametrize("steuer_id", [VALID_STEUER_ID])
def test_valid_steuer_id(steuer_id: str) -> None:
    assert is_valid_de_steuer_id(steuer_id)


@pytest.mark.parametrize(
    "steuer_id",
    [
        "47036892815",  # Prüfziffer falsch
        "12345678901",  # Struktur passt nicht (keine Doppelziffer in den ersten 10)
        "00000000000",
    ],
)
def test_invalid_steuer_id(steuer_id: str) -> None:
    assert not is_valid_de_steuer_id(steuer_id)


def test_steuer_id_recognizer_finds_match() -> None:
    recognizer = GermanSteuerIdRecognizer()
    text = f"Steuer-ID: {VALID_STEUER_ID}."
    spans = recognizer.analyze(text)
    assert len(spans) == 1
    assert spans[0].category == "TAX_ID"


def test_valid_ust_id() -> None:
    assert is_valid_de_ust_id(VALID_UST_ID)


@pytest.mark.parametrize(
    "ust_id",
    [
        "DE136695977",
        "DE000000000",
        "AT136695976",
    ],
)
def test_invalid_ust_id(ust_id: str) -> None:
    assert not is_valid_de_ust_id(ust_id)


def test_ust_id_recognizer_finds_match() -> None:
    recognizer = GermanUStIdNrRecognizer()
    text = f"USt-IdNr: {VALID_UST_ID}"
    spans = recognizer.analyze(text)
    assert len(spans) == 1
    assert spans[0].category == "UID"
