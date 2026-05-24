"""IBAN-Recognizer mit MOD-97-Validierung für AT, DE, CH und LI."""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

# Pflichtlängen für DACH-IBANs.
_IBAN_LENGTHS: dict[str, int] = {"AT": 20, "DE": 22, "CH": 21, "LI": 21}

# Länderspezifische Patterns. Jede Variante endet mit Negative-Lookahead
# (?![A-Z0-9]), damit der Regex nicht über die korrekte IBAN-Länge hinaus
# in nachfolgende alphanumerische Zeichen läuft und der MOD-97-Validator
# dann fälschlich rejected — siehe Hypothesis-Regression D-033.
_IBAN_REGEX = re.compile(
    r"\b("
    # AT: 2 Buchst. + 18 Ziffern = 4 Gruppen à 4 Ziffern (mit optionalen Spaces)
    r"AT\d{2}(?:[ ]?\d{4}){3}[ ]?\d{4}"
    # DE: 2 Buchst. + 20 Ziffern = 4 Gruppen à 4 + 2-Ziffern-Rest
    r"|DE\d{2}(?:[ ]?\d{4}){4}[ ]?\d{2}"
    # CH/LI: 2 Buchst. + 19 alphanumerisch = 4 Gruppen à 4 + 1 Zeichen
    r"|(?:CH|LI)\d{2}(?:[ ]?[A-Z0-9]{4}){3}[ ]?[A-Z0-9]{4}[ ]?[A-Z0-9]"
    r")(?![A-Z0-9])"
)


def _strip(iban: str) -> str:
    return iban.replace(" ", "").upper()


def _mod97(iban: str) -> int:
    """ISO 13616 / IBAN-Prüfsumme."""
    rearranged = iban[4:] + iban[:4]
    digits: list[str] = []
    for ch in rearranged:
        if ch.isalpha():
            digits.append(str(ord(ch) - 55))  # A=10 … Z=35
        else:
            digits.append(ch)
    return int("".join(digits)) % 97


def is_valid_iban(candidate: str) -> bool:
    """Prüfe IBAN auf Länge, Zeichensatz und MOD-97."""
    iban = _strip(candidate)
    if len(iban) < 5:
        return False
    cc = iban[:2]
    expected = _IBAN_LENGTHS.get(cc)
    if expected is None or len(iban) != expected:
        return False
    if not iban[2:4].isdigit():
        return False
    if not all(c.isalnum() for c in iban[4:]):
        return False
    try:
        return _mod97(iban) == 1
    except ValueError:
        return False


class IBANDachRecognizer:
    """Findet AT/DE/CH/LI-IBANs inkl. Prüfsumme."""

    name = "iban_dach"
    category = "IBAN"

    def analyze(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _IBAN_REGEX.finditer(text):
            raw = match.group(0)
            if is_valid_iban(raw):
                spans.append(
                    Span(
                        start=match.start(),
                        end=match.end(),
                        category=self.category,
                        text=raw,
                        score=0.99,
                    )
                )
        return spans
