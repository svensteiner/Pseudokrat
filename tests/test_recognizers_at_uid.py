"""Tests für die österreichische UID-Nummer."""

from __future__ import annotations

import pytest

from pseudokrat.recognizers.at_uid import AustrianUIDRecognizer, is_valid_at_uid

VALID_UID = "ATU12345675"  # offizielles Beispiel mit korrekter Prüfziffer


@pytest.mark.parametrize("uid", [VALID_UID, "ATU37675002"])
def test_valid_uid(uid: str) -> None:
    assert is_valid_at_uid(uid)


@pytest.mark.parametrize(
    "uid",
    [
        "ATU99999999",  # Prüfziffer falsch
        "ATU12345670",
        "ATU1234567",  # zu kurz
        "AT12345675",  # ohne U
        "ATU12345675X",  # zu lang
    ],
)
def test_invalid_uid(uid: str) -> None:
    assert not is_valid_at_uid(uid)


def test_recognizer_finds_uid_in_text() -> None:
    recognizer = AustrianUIDRecognizer()
    text = f"UID der Firma: {VALID_UID}, vielen Dank."
    spans = recognizer.analyze(text)
    assert len(spans) == 1
    assert spans[0].text == VALID_UID
    assert spans[0].category == "UID"


def test_recognizer_skips_invalid_uid() -> None:
    recognizer = AustrianUIDRecognizer()
    spans = recognizer.analyze("UID ATU99999999 ist eine fehlerhafte Nummer.")
    assert spans == []
