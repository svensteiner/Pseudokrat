"""Deutsche Umsatzsteuer-Identifikationsnummer (DE + 9 Ziffern)."""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

_DE_UST_RE = re.compile(r"\bDE\d{9}\b")


def is_valid_de_ust_id(candidate: str) -> bool:
    """ISO 7064 MOD 11, 10 Prüfung der letzten Ziffer."""
    cleaned = candidate.replace(" ", "").upper()
    if not re.fullmatch(r"DE\d{9}", cleaned):
        return False
    digits = cleaned[2:]
    product = 10
    for d in digits[:8]:
        s = (int(d) + product) % 10
        if s == 0:
            s = 10
        product = (s * 2) % 11
    check = (11 - product) % 10
    return check == int(digits[8])


class GermanUStIdNrRecognizer:
    """DE + 9 Ziffern, ISO 7064-Prüfziffer."""

    name = "de_ust_id"
    category = "UID"

    def analyze(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _DE_UST_RE.finditer(text):
            raw = match.group(0)
            if is_valid_de_ust_id(raw):
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
