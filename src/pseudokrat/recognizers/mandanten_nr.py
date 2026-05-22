"""Konfigurierbarer Recognizer für Mandanten-/Kanzlei-spezifische Nummernkreise."""

from __future__ import annotations

import re
from re import Pattern

from pseudokrat.recognizers.base import Span


class MandantenNummerRecognizer:
    """Regex-basierter Recognizer, pro Profil konfigurierbar."""

    name = "mandanten_nr"
    category = "MANDANT_NR"

    def __init__(self, pattern: str | Pattern[str], score: float = 0.85) -> None:
        self._regex: Pattern[str] = re.compile(pattern) if isinstance(pattern, str) else pattern
        self._score = score

    def analyze(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in self._regex.finditer(text):
            spans.append(
                Span(
                    start=match.start(),
                    end=match.end(),
                    category=self.category,
                    text=match.group(0),
                    score=self._score,
                )
            )
        return spans
