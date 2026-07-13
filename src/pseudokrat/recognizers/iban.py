"""IBAN-Recognizer mit MOD-97-Validierung — DACH-Kern + gängige SEPA-Länder.

WP-Mandate haben regelmässig ausländische Bankverbindungen (Beteiligungen,
Lieferanten, Rechnungen). Diese IBANs sind hochsensible Daten und dürfen nicht
ungeschwärzt in den Cloud-Prompt gelangen. Der MOD-97-Validator ist ohnehin
länderunabhängig — es genügt, die Pflichtlängen-Tabelle zu erweitern und ein
generisches Kandidaten-Pattern zu verwenden; ``is_valid_iban`` (Länge + MOD-97)
filtert Falschtreffer zuverlässig.
"""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

# Pflichtlängen je Land (ISO 13616). DACH zuerst, dann gängige SEPA-Länder.
_IBAN_LENGTHS: dict[str, int] = {
    "AT": 20, "DE": 22, "CH": 21, "LI": 21,
    "IT": 27, "FR": 27, "NL": 18, "LU": 20, "BE": 16, "ES": 24, "PT": 25,
    "SK": 24, "CZ": 24, "HU": 28, "SI": 19, "HR": 21, "PL": 28, "RO": 24,
    "BG": 22, "GB": 22, "IE": 22, "DK": 18, "SE": 24, "FI": 18, "NO": 15,
    "EE": 20, "LV": 21, "LT": 20, "GR": 27, "CY": 28, "MT": 31, "IS": 26,
    "MC": 27, "SM": 27, "AD": 24, "RS": 22, "TR": 26,
}

# Generisches Kandidaten-Pattern: 2 Buchstaben (Land) + 2 Prüfziffern + 11-30
# alphanumerische Zeichen, optional 4er-gruppiert. Negative-Lookahead (?![A-Z0-9])
# verhindert Überlaufen in Folgezeichen (Hypothesis-Regression D-033); die
# eigentliche Filterung macht is_valid_iban (Land/Länge/MOD-97).
_IBAN_REGEX = re.compile(
    r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}(?![A-Z0-9])"
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
