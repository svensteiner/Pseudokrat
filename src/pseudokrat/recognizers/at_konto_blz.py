"""Österreichische Kontonummer + Bankleitzahl (Alt-/Pre-SEPA-Format).

Viele Bestandsdokumente (Verträge, Lohnkonten, Altbelege) führen noch
Kontonummer und 5-stellige BLZ statt IBAN. Kontext-verankert (Anker „BLZ"
bzw. „Konto/Kto"), damit reine Zahlenspalten nicht getroffen werden.
"""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # BLZ: exakt 5-stellig, Anker "BLZ".
    (re.compile(r"\bBLZ[:\s]*\d{5}\b", re.IGNORECASE), "BLZ"),
    # Kontonummer: 4-11 Ziffern, Anker "Konto"/"Kto"/"Kontonummer".
    (
        re.compile(
            r"\b(?:Kontonummer|Kontonr\.?|Konto-Nr\.?|Konto|Kto\.?)[:\s]*\d{4,11}\b",
            re.IGNORECASE,
        ),
        "KONTO",
    ),
)


class AustrianKontoBlzRecognizer:
    """Alt-Bankverbindung (Kontonummer + BLZ), kontext-verankert."""

    name = "at_konto_blz"

    def analyze(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for pattern, category in _PATTERNS:
            for match in pattern.finditer(text):
                spans.append(
                    Span(
                        start=match.start(),
                        end=match.end(),
                        category=category,
                        text=match.group(0),
                        score=0.8,
                    )
                )
        return spans
