"""Conservative additional property signals for the reviewed KI-project workflow.

These patterns are suggestions, not a claim of anonymity. Area/rent/year
fingerprints are deliberately flagged separately from direct identifiers.
"""

from __future__ import annotations

import re
from typing import Literal

from pseudokrat.recognizers.base import Span

FieldKind = Literal["identity", "quasi_identifier", "value"]

_IDENTITY = re.compile(
    r"^(?:top|wohnung(?:s?(?:nummer|nr|id))?|objekt(?:nummer|nr|id)?|"
    r"einheit(?:nummer|nr|id)?|adresse|anschrift|strasse|strassenname|hausnummer|"
    r"plz|postleitzahl|ort|lage|stiege|tuer|etage|stock(?:werk)?|grundbuch|"
    r"katastralgemeinde|einlagezahl|ez|kg|mieter|eigentuemer|vermieter|"
    r"kunde(?:nnummer|nnr|nid)?|personalnummer|kontonummer|name|vorname|nachname)$"
)
_QUASI = re.compile(r"flaeche|miete|baujahr|zimmer|geschoss|koordinat|latitude|longitude")
_PROPERTY = re.compile(
    r"\b(?:Top|Wohnung|Objekt|Einheit|Stiege|Tür|Tuer)"
    r"(?:[ -]?(?:Nr\.?|Nummer|ID))?\s*[:#]?\s+"
    r"(?:[A-Z][/-]?)?[0-9]+(?:[/-][A-Z0-9]+)*[A-Z]?\b"
    r"(?![\d.,]|\s*(?:m[²2]|qm|EUR|€|%))",
    re.IGNORECASE,
)
_STREET = re.compile(
    r"\b(?:[A-ZÄÖÜ][a-zäöüß'-]+[ -])?"
    r"(?:[A-ZÄÖÜ][a-zäöüß'-]*(?:straße|strasse|gasse|allee|weg|platz|ring|ufer)|"
    r"Straße|Strasse|Gasse|Allee|Weg|Platz|Ring|Ufer)"
    r"\s+\d{1,4}[a-zA-Z]?(?:[/-]\d{1,4}[a-zA-Z]?)?\b"
)


def field_kind(header: str) -> FieldKind:
    """Classify a header; unknown headers remain values requiring local review."""
    normalized = header.lower().strip()
    for original, replacement in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        normalized = normalized.replace(original, replacement)
    normalized = re.sub(r"[^a-z0-9]", "", normalized)
    if _IDENTITY.fullmatch(normalized):
        return "identity"
    if _QUASI.search(normalized):
        return "quasi_identifier"
    return "value"


class PropertyIdentityRecognizer:
    """Detect labelled unit identifiers and street fragments, including without ZIP."""

    name = "property_identity"

    def analyze(self, text: str) -> list[Span]:
        return [
            Span(match.start(), match.end(), category, match.group(), 0.85)
            for pattern, category in ((_PROPERTY, "PROPERTY"), (_STREET, "ADDRESS"))
            for match in pattern.finditer(text)
        ]
