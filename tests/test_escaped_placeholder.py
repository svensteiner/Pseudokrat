"""Tests für den EscapedPlaceholderRecognizer (D-049)."""

from __future__ import annotations

import pytest

from pseudokrat.recognizers.escaped_placeholder import EscapedPlaceholderRecognizer


@pytest.fixture
def recognizer() -> EscapedPlaceholderRecognizer:
    return EscapedPlaceholderRecognizer()


@pytest.mark.parametrize(
    "token",
    ["<PERSON_001>", "<IBAN_042>", "<COMPANY_999>", "<ESCAPED_001>", "<TAX_ID_123>"],
)
def test_matches_placeholder_shaped_tokens(
    recognizer: EscapedPlaceholderRecognizer, token: str
) -> None:
    spans = recognizer.analyze(f"vorher {token} nachher")
    assert len(spans) == 1
    assert spans[0].text == token
    assert spans[0].category == "ESCAPED"
    assert spans[0].score == 1.0


@pytest.mark.parametrize(
    "text",
    [
        "kein platzhalter hier",
        "<person_001>",  # lowercase → kein Match
        "<PERSON_1>",  # zu wenige Ziffern (Regex verlangt >= 3)
        "<PERSON>",  # keine Nummer
        "PERSON_001",  # keine spitzen Klammern
        "",
    ],
)
def test_ignores_non_placeholders(
    recognizer: EscapedPlaceholderRecognizer, text: str
) -> None:
    assert recognizer.analyze(text) == []


def test_finds_multiple_tokens(recognizer: EscapedPlaceholderRecognizer) -> None:
    spans = recognizer.analyze("<PERSON_001> und <IBAN_002>")
    assert [s.text for s in spans] == ["<PERSON_001>", "<IBAN_002>"]
