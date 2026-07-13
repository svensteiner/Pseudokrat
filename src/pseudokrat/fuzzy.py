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


#: Kategorien, bei denen Fuzzy-Merging (Levenshtein ≤ N) zulässig ist.
#:
#: **Nur Firmen.** Bei Firmennamen ist der Schreibvarianten-Spielraum echt
#: (``Hofer Bau GmbH`` / ``Hofer-Bau GmbH`` / ``HoferBau GmbH``) und durch
#: die Rechtsform-Endung zusätzlich abgesichert — zwei Firmen mit gleicher
#: Rechtsform und Levenshtein-≤2-Kern sind praktisch dieselbe Firma.
#:
#: **PERSON und ADDRESS sind bewusst NICHT dabei** (geändert in D-048):
#: Nachnamen wie ``Maier`` / ``Mayer`` / ``Meier`` / ``Meyer`` oder Adressen
#: wie ``Hauptstraße 12`` / ``Hauptstraße 13`` liegen Levenshtein 1 auseinander,
#: sind aber **verschiedene** Personen bzw. Anschriften. Fuzzy-Merge würde sie
#: zu einem Platzhalter kollabieren → (a) Round-Trip-Bug (Deanonymisierung
#: liefert den falschen Originalnamen zurück) und (b) Datenschutz-Korrektheits-
#: fehler (zwei reale Mandanten verschmelzen in der KI-Eingabe).
#:
#: Echte Schreibvarianten DERSELBEN Person/Adresse (Umlaut, Groß/Klein,
#: Bindestrich, Mehrfach-Whitespace) werden bereits durch :func:`normalize`
#: gefaltet und matchen damit über den **Exact**-Pfad — Fuzzy ist dafür nicht
#: nötig. Die sichere Richtung ist Über-Segmentierung (ein Pseudonym zu viel,
#: voll reversibel) statt Falsch-Merge (irreversibel). Siehe D-032 + D-048.
_FUZZY_MERGE_CATEGORIES: frozenset[str] = frozenset({"COMPANY", "ORG"})


def is_fuzzy_merge_category(category: str) -> bool:
    """True für Kategorien, in denen Schreibvarianten zum selben Platzhalter
    zusammengeführt werden dürfen (nur Firmen — siehe D-048)."""
    return category in _FUZZY_MERGE_CATEGORIES


#: Mindestlänge des Firmen-Kerns, ab der ein 1-Zeichen-Tippfehler toleriert wird.
#: Kurze, distinktive Kerne (``maier`` / ``mayer``) bleiben bewusst getrennt.
_FUZZY_MIN_CORE_LEN = 10

_ALNUM_ONLY_RE = re.compile(r"[^a-z0-9]")


def should_merge(
    candidate_normalized: str,
    existing_normalized: str,
    category: str,
    max_distance: int = 1,
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

    # Reine Trenn-/Schreibvarianten DERSELBEN Firma zusammenführen:
    # „Hofer Bau" / „HoferBau" / „Hofer-Bau" → nach Entfernen aller
    # Nicht-Alnum-Zeichen identisch. Sicher, weil nur Trennung variiert.
    if _ALNUM_ONLY_RE.sub("", cand_core) == _ALNUM_ONLY_RE.sub("", exist_core):
        return True

    # Ein-Zeichen-Tippfehler NUR bei langen Kernen tolerieren. Kurze,
    # distinktive Namen (Maier/Mayer, verschiedene Firmen) bleiben getrennt —
    # Über-Segmentierung ist reversibel, ein Falsch-Merge nicht (D-048++).
    longer = max(len(cand_core), len(exist_core))
    if longer < _FUZZY_MIN_CORE_LEN:
        return False
    return Levenshtein.distance(cand_core, exist_core) <= max_distance
