"""Österreichische UID-Nummer (ATU + 8 Ziffern, Luhn-ähnliche Prüfziffer)."""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

_AT_UID_RE = re.compile(r"\bATU\d{8}\b")


def is_valid_at_uid(candidate: str) -> bool:
    """Prüfziffer-Validierung gemäß BMF-Algorithmus.

    Mathematik (kurz):
      digits = d1..d8, Prüfziffer ist d8.
      S = d1
          + cross_sum(d2 * 2) + d3
          + cross_sum(d4 * 2) + d5
          + cross_sum(d6 * 2) + d7
      Prüfziffer = (10 - (S + 4) mod 10) mod 10 == d8
    """
    if not _AT_UID_RE.fullmatch(candidate):
        return False
    digits = [int(c) for c in candidate[3:]]

    def cross_sum(n: int) -> int:
        return n // 10 + n % 10

    s = (
        digits[0]
        + cross_sum(digits[1] * 2)
        + digits[2]
        + cross_sum(digits[3] * 2)
        + digits[4]
        + cross_sum(digits[5] * 2)
        + digits[6]
    )
    expected = (10 - (s + 4) % 10) % 10
    return expected == digits[7]


class AustrianUIDRecognizer:
    """ATU + 8 Ziffern mit Prüfziffer."""

    name = "at_uid"
    category = "UID"

    def analyze(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _AT_UID_RE.finditer(text):
            raw = match.group(0)
            if is_valid_at_uid(raw):
                spans.append(
                    Span(
                        start=match.start(),
                        end=match.end(),
                        category=self.category,
                        text=raw,
                        score=0.95,
                    )
                )
        return spans
