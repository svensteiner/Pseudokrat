"""Tests für den URL-Recognizer."""

from __future__ import annotations

import pytest

from pseudokrat.recognizers.url import UrlRecognizer


@pytest.fixture
def recognizer() -> UrlRecognizer:
    return UrlRecognizer()


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://example.com/path",
        "https://www.example.com/path?query=1&other=2",
        "https://sub.domain.example.com:8443/x/y",
        "ftp://files.example.com/archive.zip",
    ],
)
def test_scheme_urls(recognizer: UrlRecognizer, url: str) -> None:
    text = f"Siehe {url} für Details."
    spans = recognizer.analyze(text)
    assert len(spans) == 1
    assert spans[0].text == url
    assert spans[0].category == "URL"


def test_www_without_scheme(recognizer: UrlRecognizer) -> None:
    text = "Mehr Info auf www.example.com/bereich."
    spans = recognizer.analyze(text)
    assert len(spans) == 1
    assert spans[0].text == "www.example.com/bereich"


def test_trailing_punctuation_trimmed(recognizer: UrlRecognizer) -> None:
    text = "Siehe https://example.com/page, das ist Pflicht."
    spans = recognizer.analyze(text)
    assert spans[0].text == "https://example.com/page"


def test_does_not_match_bare_word(recognizer: UrlRecognizer) -> None:
    text = "Das ist kein link, nur Text."
    assert recognizer.analyze(text) == []


def test_does_not_match_https_without_dot(recognizer: UrlRecognizer) -> None:
    # Defensive: keine TLD → kein Match
    text = "https://localhost"
    assert recognizer.analyze(text) == []


def test_multiple_urls(recognizer: UrlRecognizer) -> None:
    text = "A: https://example.org. B: www.foo.bar/path. C: http://baz.de/x?y=1."
    spans = recognizer.analyze(text)
    assert len(spans) == 3
