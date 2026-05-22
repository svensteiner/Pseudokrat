"""Deutsche Steuer-Identifikationsnummer (11 Ziffern, § 139b AO)."""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

_DE_STEUER_ID_RE = re.compile(r"(?<!\d)\d{11}(?!\d)")


def is_valid_de_steuer_id(candidate: str) -> bool:
    """Prüfung gemäß ISO 7064 Mod 11, 10.

    Strukturregel: Unter den ersten 10 Stellen kommt genau eine Ziffer
    entweder zweimal oder dreimal vor; alle anderen genau einmal.
    """
    cleaned = candidate.replace(" ", "")
    if len(cleaned) != 11 or not cleaned.isdigit():
        return False
    first_ten = cleaned[:10]
    counts: dict[str, int] = {}
    for d in first_ten:
        counts[d] = counts.get(d, 0) + 1
    repeats = sorted(counts.values(), reverse=True)
    if repeats[0] not in (2, 3):
        return False
    # Wenn 3-fach: muss genau 8 verschiedene Ziffern geben, restliche je 1x
    # Wenn 2-fach: muss genau 9 verschiedene Ziffern geben, restliche je 1x
    if repeats[0] == 3 and len(counts) != 8:
        return False
    if repeats[0] == 2 and len(counts) != 9:
        return False

    # ISO 7064 Mod 11, 10
    product = 10
    for digit in first_ten:
        s = (int(digit) + product) % 10
        if s == 0:
            s = 10
        product = (s * 2) % 11
    check = (11 - product) % 10
    return check == int(cleaned[10])


class GermanSteuerIdRecognizer:
    """11-stellige deutsche Steuer-ID mit Prüfziffer."""

    name = "de_steuer_id"
    category = "TAX_ID"

    def analyze(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _DE_STEUER_ID_RE.finditer(text):
            raw = match.group(0)
            if is_valid_de_steuer_id(raw):
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
