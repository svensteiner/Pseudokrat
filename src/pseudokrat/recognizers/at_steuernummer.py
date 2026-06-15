"""STEUERNR-Recognizer — oesterreichische Steuernummer (Finanzamt/Abgabenkonto).

Format: 2-stellige Finanzamtsnummer + 3 Ziffern + ``/`` + 4 Ziffern, optional
gefolgt von ``-NN``. Beispiele: ``03 018/0574``, ``03 018/0574-24``,
``03-018/0574``. Trennzeichen zwischen FA-Nr und Block ist Leerzeichen oder ``-``.

Hoher Score, damit die Steuernummer bei Ueberlappung den Telefon-Recognizer
schlaegt (der nur den ``018/0574``-Teil als Nummer sieht).
"""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

_STNR_RE = re.compile(r"\b\d{2}[\s-]\d{3}/\d{4}(?:-\d{1,2})?\b")


class AustrianSteuernummerRecognizer:
    """Erkennt oesterreichische Steuernummern (FA NNN/NNNN)."""

    name = "at_steuernummer"
    category = "STEUERNR"

    def analyze(self, text: str) -> list[Span]:
        return [
            Span(
                start=m.start(),
                end=m.end(),
                category=self.category,
                text=m.group(0),
                score=0.92,
            )
            for m in _STNR_RE.finditer(text)
        ]
