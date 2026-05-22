"""Telefonnummern-Recognizer für DACH-Formate (AT/DE/CH/LI).

Erkennt international präfixierte Nummern (`+49…`, `0049…`) und nationale
DACH-Schreibweisen (`0664 …`, `030 …`, `044 …`). Bewusst konservativ:
Nummern ohne erkennbares DACH-Präfix werden ignoriert, um false positives
auf langen Zahlenfolgen (Rechnungsnummern, Ordnungsbegriffe) zu vermeiden.
"""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

_INTL_RE = re.compile(
    r"(?<![\w+])"
    r"(?P<num>(?:\+|00)(?:41|43|49)(?:[\s./()\-]?\d){6,17})"
    r"(?!\w)"
)

_NATIONAL_RE = re.compile(
    r"(?<![\w+./\d])"
    r"(?P<num>0\d{2,4}[\s./()\-/]\d(?:[\s./()\-/]?\d){5,14})"
    r"(?!\w)"
)


def _digit_count(text: str) -> int:
    return sum(1 for ch in text if ch.isdigit())


class PhoneRecognizer:
    """DACH-Telefonnummern (international und national)."""

    name = "phone"
    category = "PHONE"

    def analyze(self, text: str) -> list[Span]:
        spans: list[Span] = []
        seen_ranges: list[tuple[int, int]] = []

        for match in _INTL_RE.finditer(text):
            number = match.group("num")
            digits = _digit_count(number)
            if 8 <= digits <= 18:
                spans.append(
                    Span(
                        start=match.start("num"),
                        end=match.end("num"),
                        category=self.category,
                        text=number,
                        score=0.85,
                    )
                )
                seen_ranges.append((match.start("num"), match.end("num")))

        for match in _NATIONAL_RE.finditer(text):
            start, end = match.start("num"), match.end("num")
            if any(start < e and end > s for s, e in seen_ranges):
                continue
            number = match.group("num")
            digits = _digit_count(number)
            if 8 <= digits <= 14:
                spans.append(
                    Span(
                        start=start,
                        end=end,
                        category=self.category,
                        text=number,
                        score=0.65,
                    )
                )
        return spans
