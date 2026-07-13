"""Österreichische Register-Kennungen — kontext-verankert (niedrige FP-Rate).

Erfasst: GISA-Zahl (Gewerberegister), DVR-Nummer (Datenverarbeitungsregister)
sowie Grundbuch (Einlagezahl EZ + Katastralgemeinde KG). Alle Muster verlangen
ein sprechendes Anker-Label, damit zufällige Zahlenfolgen nicht getroffen
werden. ``KG`` als Grundbuch-Kürzel wird nur mit 5-stelliger Nummer akzeptiert
(unterscheidet es von der Rechtsform „KG").
"""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # GISA-Zahl: 8-stellig, Anker "GISA".
    (re.compile(r"\bGISA[-\s]?(?:Zahl|Nr\.?|Nummer)?[:\s]*\d{8}\b", re.IGNORECASE), "GISA"),
    # DVR-Nummer: 7-stellig, Anker "DVR".
    (re.compile(r"\bDVR[:\s-]*\d{7}\b", re.IGNORECASE), "DVR"),
    # Grundbuch — Einlagezahl.
    (re.compile(r"\b(?:Einlagezahl|EZ)\s*\d{1,5}\b", re.IGNORECASE), "GRUNDBUCH"),
    # Grundbuch — Katastralgemeinde (5-stellig, grenzt gegen Rechtsform „KG" ab).
    (re.compile(r"\b(?:Katastralgemeinde|KG)\s*\d{5}\b", re.IGNORECASE), "GRUNDBUCH"),
)


class AustrianRegisterRecognizer:
    """GISA / DVR / Grundbuch (EZ, KG) — kontext-verankert."""

    name = "at_register"

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
                        score=0.85,
                    )
                )
        return spans
