"""FN-Recognizer — oesterreichische Firmenbuchnummer.

Format: ``FN`` + 1–6 Ziffern + ein Pruefzeichen (Kleinbuchstabe),
z. B. ``FN 30633z``, ``FN 519768s``, ``FN123456a``. Das Leerzeichen
zwischen ``FN`` und der Zahl ist optional.
"""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

_FN_RE = re.compile(r"\bFN\s?\d{1,6}\s?[a-z]\b")


class FirmenbuchRecognizer:
    """Erkennt oesterreichische Firmenbuchnummern (FN …)."""

    name = "firmenbuch"
    category = "FN"

    def analyze(self, text: str) -> list[Span]:
        return [
            Span(
                start=m.start(),
                end=m.end(),
                category=self.category,
                text=m.group(0),
                score=0.95,
            )
            for m in _FN_RE.finditer(text)
        ]
