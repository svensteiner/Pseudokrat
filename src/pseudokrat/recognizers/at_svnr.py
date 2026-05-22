"""Österreichische Sozialversicherungsnummer (10 Ziffern, Mod-11-Prüfziffer)."""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

# 4 lfd. Ziffern (Prüfziffer ist die 4. Stelle) + 6 Geburtsdatum DDMMYY
_AT_SVNR_RE = re.compile(r"(?<!\d)(\d{4})[ ]?(\d{6})(?!\d)")

_WEIGHTS: tuple[int, ...] = (3, 7, 9, 5, 8, 4, 2, 1, 6)  # 9 Gewichte für Stellen 1,2,3,5..10


def is_valid_at_svnr(candidate: str) -> bool:
    """Prüfziffer ist die 4. Stelle, berechnet aus den anderen 9 Stellen.

    Reihenfolge der gewichteten Stellen: lfd1, lfd2, lfd3, geb1..geb6.
    """
    cleaned = candidate.replace(" ", "")
    if len(cleaned) != 10 or not cleaned.isdigit():
        return False
    digits = [int(c) for c in cleaned]
    check = digits[3]
    weighted = (
        digits[0] * _WEIGHTS[0]
        + digits[1] * _WEIGHTS[1]
        + digits[2] * _WEIGHTS[2]
        + digits[4] * _WEIGHTS[3]
        + digits[5] * _WEIGHTS[4]
        + digits[6] * _WEIGHTS[5]
        + digits[7] * _WEIGHTS[6]
        + digits[8] * _WEIGHTS[7]
        + digits[9] * _WEIGHTS[8]
    )
    expected = weighted % 11
    if expected == 10:
        return False  # Bei 10 wird die Nummer nicht vergeben
    return expected == check


class AustrianSVNRRecognizer:
    """Findet AT-SVNR (10-stellig mit Mod-11-Prüfung)."""

    name = "at_svnr"
    category = "SVNR"

    def analyze(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _AT_SVNR_RE.finditer(text):
            raw = match.group(0)
            if is_valid_at_svnr(raw):
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
