"""Normalisierung + Fuzzy-Match-Logik für Pseudonym-Konsistenz."""

from __future__ import annotations

import re
import unicodedata

from rapidfuzz.distance import Levenshtein

_LEGAL_FORMS: tuple[str, ...] = (
    "gmbh & co. kg",
    "gmbh & co kg",
    "gmbh und co. kg",
    "gmbh und co kg",
    "ag & co. kg",
    "ag & co kg",
    "ag und co kg",
    "kgaa",
    "gmbh",
    "ohg",
    "kg",
    "ag",
    "se",
    "og",
    "ug",
    "eu",
    "e.u.",
    "ev",
    "e.v.",
    "eg",
    "e.g.",
    "gag",
    "stiftung",
    "limited",
    "ltd",
    "llc",
    "sarl",
    "s.a.r.l.",
    "spa",
    "s.p.a.",
)

_WHITESPACE_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Normalisiere Text für Fuzzy-Vergleich.

    - lowercase
    - Unicode NFKD + Diakritika entfernen (aber deutsche Umlaute bleiben durch
      bewusste Vor-Transformation lesbar: ä→ae, ö→oe, ü→ue, ß→ss)
    - Sonderzeichen → Leerzeichen
    - Whitespace konsolidieren
    """
    lower = text.lower().strip()
    lower = lower.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    decomposed = unicodedata.normalize("NFKD", lower)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = re.sub(r"[^\w\s&.]", " ", stripped)
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def extract_legal_form(normalized: str) -> str | None:
    """Extrahiere die zugehörige Rechtsform (oder None)."""
    for form in _LEGAL_FORMS:  # längste zuerst
        if normalized.endswith(" " + form) or normalized == form:
            return form
    return None


def core_company_name(normalized: str) -> str:
    """Entferne die Rechtsform-Endung."""
    form = extract_legal_form(normalized)
    if form is None:
        return normalized
    if normalized.endswith(" " + form):
        return normalized[: -(len(form) + 1)].strip()
    return ""


#: Kategorien, bei denen Fuzzy-Merging zulässig ist. Alle anderen müssen exakt
#: matchen — sonst kollabieren z. B. zwei UIDs, die sich nur in zwei Ziffern
#: unterscheiden, zu einem Platzhalter und die Reverse-Auflösung liefert die
#: falsche Original-ID zurück (Round-Trip-Bug). Siehe D-032.
_FUZZY_MERGE_CATEGORIES: frozenset[str] = frozenset(
    {"COMPANY", "ORG", "PERSON", "ADDRESS"}
)


def is_fuzzy_merge_category(category: str) -> bool:
    """True für Kategorien, in denen Schreibvarianten zum selben Platzhalter
    zusammengeführt werden dürfen (Firmen, Personen, Adressen)."""
    return category in _FUZZY_MERGE_CATEGORIES


def should_merge(
    candidate_normalized: str,
    existing_normalized: str,
    category: str,
    max_distance: int = 2,
) -> bool:
    """Sollen die zwei Einträge zum gleichen Platzhalter zusammengeführt werden?

    Regel:
      - identische Kategorie ist Pflicht (wird vom Caller geprüft)
      - Exact-Match nach Normalisierung gilt immer
      - Fuzzy-Merge (Levenshtein ≤ ``max_distance``) NUR für
        :data:`_FUZZY_MERGE_CATEGORIES` — numerische IDs wie IBAN, UID, SVNR,
        TAX_ID, AHV verlangen Exact-Match, sonst kollabieren ähnliche Nummern
        und die Reverse-Auflösung wird falsch.
      - Bei ORG/COMPANY zusätzlich: Rechtsform-Endung MUSS identisch sein
    """
    if candidate_normalized == existing_normalized:
        return True
    if category not in _FUZZY_MERGE_CATEGORIES:
        return False

    cand_form = extract_legal_form(candidate_normalized)
    exist_form = extract_legal_form(existing_normalized)
    if cand_form != exist_form:
        return False

    cand_core = core_company_name(candidate_normalized) or candidate_normalized
    exist_core = core_company_name(existing_normalized) or existing_normalized
    distance = Levenshtein.distance(cand_core, exist_core)
    return distance <= max_distance
