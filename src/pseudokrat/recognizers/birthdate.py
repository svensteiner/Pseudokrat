"""Geburtsdatum-Recognizer — kontext-gesteuert, kein blinder DATE-Regex.

Hintergrund (PRL Iter-5): Pure ``DD.MM.YYYY``-Erkennung produziert in
Kanzlei-Texten massive False-Positives (Eintrittsdatum, Berichts-
datum, Fälligkeit, ...). Im Eval-Korpus sind unter ``DATE`` ausschliess-
lich **Geburtsdaten** als PII annotiert. Diese Klasse trifft genau das:
sucht nach einem Geburts-Kontext-Label (``Geburtsdatum``, ``geboren am``,
``DOB``, ``Date of Birth``) und nimmt das nachfolgende Datum auf —
nichts anderes.

So bleibt die FP-Rate auf der ``false_positive_traps``-Fixture bei 0,
und Geburts-Daten in AT/DE/CH-Lohnkonten werden konsistent erkannt.
"""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

# Label-Trigger — vor dem eigentlichen Datum erwartet.
# Beispiele die hier matchen sollen:
#   "Geburtsdatum:   15.03.1985"
#   "geboren am 22.08.1972"
#   "DOB: 1985-03-15"
#   "Date of Birth — 07.11.1978"
_LABEL_RE = re.compile(
    r"""
    (?:
        \b geburtsdatum \b
        | \b geburtstag \b
        | \b geboren \s+ am \b
        | \b geb \.
        | \b date \s+ of \s+ birth \b
        | \b dob \b
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Datums-Pattern — nur unzweideutige Formate mit 4-stelligem Jahr.
#   DD.MM.YYYY   (z. B. 15.03.1985)  — DACH-Standard
#   YYYY-MM-DD   (z. B. 1985-03-15)  — ISO
# DD/MM/YYYY bewusst NICHT, weil im DACH-Raum mehrdeutig (auch
# US-Reihenfolge denkbar) und in unseren Fixtures nicht vorhanden.
_DATE_RE = re.compile(
    r"""(?x)
    (?<!\d)
    (?:
        (?P<d>0?[1-9]|[12]\d|3[01]) \. (?P<m>0?[1-9]|1[0-2]) \. (?P<y>19\d{2}|20\d{2})
        |
        (?P<yi>19\d{2}|20\d{2}) - (?P<mi>0[1-9]|1[0-2]) - (?P<di>0[1-9]|[12]\d|3[01])
    )
    (?!\d)
    """,
)

# Maximaler Abstand (in Zeichen) zwischen Label und Datum. Erlaubt
# typische Tabulator-Einrückungen in Lohnkonten ("Geburtsdatum:        "
# ist häufig 10-30 Whitespace-Chars).
_MAX_GAP = 40


class BirthDateRecognizer:
    """Findet Geburtsdaten anhand eines Kontext-Labels davor."""

    name = "birthdate"
    category = "DATE"

    def analyze(self, text: str) -> list[Span]:
        spans: list[Span] = []
        seen_ranges: set[tuple[int, int]] = set()
        for label_match in _LABEL_RE.finditer(text):
            window_start = label_match.end()
            window_end = min(len(text), window_start + _MAX_GAP)
            window = text[window_start:window_end]
            date_match = _DATE_RE.search(window)
            if date_match is None:
                continue
            # Nur akzeptieren, wenn zwischen Label-Ende und Datums-Start
            # ausschliesslich Whitespace / Trenner liegt — kein
            # Volltext-Satz dazwischen.
            gap = window[: date_match.start()]
            if not _is_pure_gap(gap):
                continue
            start = window_start + date_match.start()
            end = window_start + date_match.end()
            if (start, end) in seen_ranges:
                continue
            seen_ranges.add((start, end))
            spans.append(
                Span(
                    start=start,
                    end=end,
                    category=self.category,
                    text=text[start:end],
                    score=0.9,
                )
            )
        return spans


def _is_pure_gap(gap: str) -> bool:
    """Erlaubt nur Whitespace + typische Trenner (Doppelpunkt,
    Bindestrich, Em-Dash) zwischen Label und Datum. Sobald ein
    alphanumerisches Zeichen auftaucht, ist's kein Label-Datum-Paar."""
    return all(c.isspace() or c in ":-—–\t" for c in gap)
