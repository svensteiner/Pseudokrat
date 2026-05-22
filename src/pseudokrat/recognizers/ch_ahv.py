"""Schweizer AHV-Nummer (756.XXXX.XXXX.XX, EAN-13-Prüfziffer)."""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

_CH_AHV_RE = re.compile(r"\b756[\.\- ]?\d{4}[\.\- ]?\d{4}[\.\- ]?\d{2}\b")


def is_valid_ch_ahv(candidate: str) -> bool:
    """EAN-13-Prüfung (Gewichte abwechselnd 1 und 3 von rechts)."""
    cleaned = re.sub(r"[^\d]", "", candidate)
    if len(cleaned) != 13 or not cleaned.startswith("756"):
        return False
    total = 0
    # EAN-13: Gewichte beginnen mit 1 für die erste Stelle (von links), dann 3, 1, 3, ...
    for idx, ch in enumerate(cleaned[:12]):
        weight = 1 if idx % 2 == 0 else 3
        total += int(ch) * weight
    check = (10 - (total % 10)) % 10
    return check == int(cleaned[12])


class SwissAHVRecognizer:
    """Schweizer Sozialversicherungsnummer."""

    name = "ch_ahv"
    category = "AHV"

    def analyze(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _CH_AHV_RE.finditer(text):
            raw = match.group(0)
            if is_valid_ch_ahv(raw):
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
