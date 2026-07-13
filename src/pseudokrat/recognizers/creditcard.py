"""Kreditkartennummern-Recognizer mit Luhn-Prüfung (mod 10).

Kreditkartennummern (13-19 Ziffern, ggf. durch Leerzeichen/Bindestriche
gruppiert) sind hochsensibel. Die Luhn-Prüfsumme filtert zufällige Ziffern-
folgen zuverlässig, sodass kaum False Positives entstehen.
"""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

# Kandidat: 13-19 Ziffern, optional durch je ein Leerzeichen/Bindestrich
# getrennt. Beginnt/endet auf einer Ziffer (kein Teil einer längeren Zahl).
_CANDIDATE_RE = re.compile(r"(?<![\d/])(?:\d[ -]?){13,19}(?<=\d)")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for index, ch in enumerate(reversed(digits)):
        value = int(ch)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


class CreditCardRecognizer:
    """Findet Kreditkartennummern (13-19 Ziffern, Luhn-validiert)."""

    name = "creditcard"
    category = "CREDITCARD"

    def analyze(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _CANDIDATE_RE.finditer(text):
            raw = match.group(0)
            digits = re.sub(r"[ -]", "", raw)
            if 13 <= len(digits) <= 19 and _luhn_ok(digits):
                spans.append(
                    Span(
                        start=match.start(),
                        end=match.end(),
                        category=self.category,
                        text=raw,
                        score=0.9,
                    )
                )
        return spans
