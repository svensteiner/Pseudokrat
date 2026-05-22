"""Tests für die Schweizer AHV-Nummer."""

from __future__ import annotations

import pytest

from pseudokrat.recognizers.ch_ahv import SwissAHVRecognizer, is_valid_ch_ahv

VALID_AHV_WITH_DOTS = "756.9217.0769.85"
VALID_AHV_PLAIN = "7569217076985"


@pytest.mark.parametrize("ahv", [VALID_AHV_WITH_DOTS, VALID_AHV_PLAIN])
def test_valid_ahv(ahv: str) -> None:
    assert is_valid_ch_ahv(ahv)


@pytest.mark.parametrize(
    "ahv",
    [
        "756.9217.0769.84",  # Prüfziffer falsch
        "123.4567.8901.23",  # falscher Präfix
        "756.0000.0000.00",
    ],
)
def test_invalid_ahv(ahv: str) -> None:
    assert not is_valid_ch_ahv(ahv)


def test_recognizer_finds_ahv() -> None:
    recognizer = SwissAHVRecognizer()
    text = f"AHV: {VALID_AHV_WITH_DOTS}, Vielen Dank."
    spans = recognizer.analyze(text)
    assert len(spans) == 1
    assert spans[0].category == "AHV"
