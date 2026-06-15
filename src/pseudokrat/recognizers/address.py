"""ADDRESS-Recognizer für DACH-Postanschriften.

Hintergrund (PRL Iter-7): Privacy-Filter liefert ADDRESS, ist im Default
nicht geladen. DACH-Adressen sind hochregulär:

    <Strassenname> <Hausnummer>, <PLZ> <Ort>

* Strassennamen enden meist auf ``-strasse/-straße`` oder Variationen
  (``-gasse``, ``-allee``, ``-platz``, ``-weg``, ``-ring``,
  ``-promenade``); sie können aus 1-2 Tokens bestehen (``Mariahilfer
  Straße``, ``Königsallee``).
* PLZ ist 4-stellig (AT/CH) oder 5-stellig (DE).
* Ortsname beginnt gross.

Die FP-Trap ``Goethestraße 5 (ohne PLZ und Ort)`` wird dadurch
abgewehrt, dass die PLZ-Pflicht im Pattern verankert ist — eine
Strasse ohne nachfolgende PLZ wird **nicht** als vollständige Adresse
erkannt.
"""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

# Capitalized-Token (inkl. Umlaute), optional mit internem Bindestrich
# (``Hans-Brunner-Allee``).
_TOKEN = r"[A-ZÄÖÜ][a-zäöüß'-]+"

# Hausnummer: Ziffern + optional Buchstaben-Suffix (``12a``) und
# optional ``/N`` für Stiegen-/Tür-Notation (``12/3``, ``12a/4``).
_HOUSE_NUMBER = r"\d{1,4}[a-zA-Z]?(?:[/-]\d{1,4}[a-zA-Z]?)?"

# Strassen-Suffix kann TEIL eines Tokens sein (``Industriestraße``)
# oder ein eigenständiges Token (``Mariahilfer Straße``).
# Klein-Variante für eingebettete Suffixe, Gross-Variante für eigenständige.
_SUFFIX_INLINE = (
    r"(?:strasse|straße|gasse|allee|weg|platz|ring|promenade"
    r"|chaussee|ufer|damm|stieg)"
)
_SUFFIX_STANDALONE = (
    r"(?:Strasse|Straße|Gasse|Allee|Weg|Platz|Ring|Promenade"
    r"|Chaussee|Ufer|Damm|Stieg)"
)

# Volladresse: Strasse + Nummer + Komma + PLZ + Ort.
# Strassen-Variante 1: ``Industriestraße`` / ``Königsallee`` —
#   Suffix verschmolzen mit Token.
# Strassen-Variante 2: ``Mariahilfer Straße`` —
#   Suffix als eigenes Token, vorne ein Adjektiv-/Eigenname-Token.
# Trenner zwischen Strassen- und PLZ-Block: Komma ODER Pipe (Briefkopf:
# „Hegelgasse 8 | 1010 Wien"). Whitespace rundherum erlaubt.
_SEP = r"\s* [,|] \s*"

_STREET = rf"""
    (?P<street>
        {_TOKEN}{_SUFFIX_INLINE}
        |
        {_TOKEN}[ \t]+{_SUFFIX_STANDALONE}
    )
    [ \t]+
    (?P<num>{_HOUSE_NUMBER})
"""

# Normalform: „Strasse Nr , PLZ Ort".
_ADDRESS_RE = re.compile(
    rf"""
    {_STREET}
    {_SEP}
    (?P<plz>\d{{4,5}})
    [ \t]+
    (?P<city>{_TOKEN}(?:[ \t]+{_TOKEN}){{0,2}})
    """,
    re.VERBOSE,
)

# Umgekehrte Form: „PLZ Ort , Strasse Nr" (oesterr. Briefkoepfe, Stempel).
_ADDRESS_REVERSED_RE = re.compile(
    rf"""
    (?P<plz>\d{{4,5}})
    [ \t]+
    (?P<city>{_TOKEN})
    {_SEP}
    {_STREET}
    """,
    re.VERBOSE,
)


class AddressRecognizer:
    """DACH-Postanschriften (Strasse Nr, PLZ Ort) — beide Reihenfolgen."""

    name = "address"
    category = "ADDRESS"

    def analyze(self, text: str) -> list[Span]:
        spans: list[Span] = []
        seen: set[tuple[int, int]] = set()
        for regex in (_ADDRESS_RE, _ADDRESS_REVERSED_RE):
            for m in regex.finditer(text):
                key = (m.start(), m.end())
                if key in seen:
                    continue
                seen.add(key)
                spans.append(
                    Span(
                        start=m.start(),
                        end=m.end(),
                        category=self.category,
                        text=text[m.start() : m.end()],
                        score=0.85,
                    )
                )
        return spans
