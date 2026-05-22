"""E-Mail-Recognizer."""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

# RFC-konformere, aber pragmatische Regex.
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


class EmailRecognizer:
    """E-Mail-Adressen."""

    name = "email"
    category = "EMAIL"

    def analyze(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _EMAIL_RE.finditer(text):
            spans.append(
                Span(
                    start=match.start(),
                    end=match.end(),
                    category=self.category,
                    text=match.group(0),
                    score=0.95,
                )
            )
        return spans
