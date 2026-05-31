"""Recognizer für bereits im Quelltext vorhandene Platzhalter-Token.

Enthält ein Eingabetext eine Zeichenkette, die wie ein Pseudokrat-Platzhalter
aussieht (``<PERSON_001>``, ``<IBAN_042>`` …), würde die Deanonymisierung sie
fälschlich als echten Platzhalter auflösen und mit einem Originaltext
überschreiben — der Roundtrip wäre kaputt (siehe D-049).

Lösung: solche Token werden bei der Anonymisierung selbst erkannt und auf einen
eigenen, reservierten ``ESCAPED``-Platzhalter abgebildet. Beim Deanonymisieren
löst der Single-Pass die echten und die escapeten Token unabhängig auf, sodass
der ursprüngliche literale ``<PERSON_001>``-Text wiederhergestellt wird.
"""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

#: Gleiches Muster wie der Deanonymizer-Regex — alles, was dort als Platzhalter
#: aufgelöst würde, muss hier vorab escaped werden.
_PLACEHOLDER_RE = re.compile(r"<[A-Z_]+_\d{3,}>")


class EscapedPlaceholderRecognizer:
    """Erkennt platzhalter-förmige Literale im Quelltext und schützt sie."""

    name = "escaped_placeholder"
    category = "ESCAPED"

    def analyze(self, text: str) -> list[Span]:
        return [
            Span(
                start=match.start(),
                end=match.end(),
                category=self.category,
                text=match.group(0),
                score=1.0,  # höchste Priorität: gewinnt jeden Overlap
            )
            for match in _PLACEHOLDER_RE.finditer(text)
        ]
