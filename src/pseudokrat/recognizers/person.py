"""PERSON-Recognizer — anker-basiert, ohne ML.

Hintergrund (PRL Iter-6): Der Privacy-Filter liefert PERSON, ist im
Default-Modus aber nicht geladen (3 GB Download). Im echten Kanzlei-
Alltag sind Personennamen nahezu immer von einem **Kontext-Anker**
umgeben — entweder einer **Anrede** (``Herr``, ``Frau``, ``Dr.``) oder
einem **Rollen-Label** (``Dienstnehmer/in``, ``Antragsteller``,
``Mandant``, ``Arbeitnehmer``). Diese Anker erlauben hohe Precision
ohne ML.

Strategie:

1. **First-Pass** — Anker-Match (Anrede oder Rollen-Label),
   anschliessend optionale akademische Titel (``Dr.``, ``Prof.``,
   ``Mag.``, ``Dipl.-Ing.``, ``MMag.`` …), dann 1-3 Capitalized-Tokens
   als Namensfeld.
2. **Second-Pass** — jedes im First-Pass gefundene Namensfeld wird im
   Resttext exakt gesucht und ebenfalls als PERSON markiert.
   Sichert die häufige Konstruktion „X bestätigt …" / „Anmerkungen zu X".

False-Positive-Risiko: vollständig durch Anker gesteuert. Bare
Namen ohne Kontext (z. B. ``Müller ging.``) bleiben unangetastet —
für diese Fälle ist das ML-Modell zuständig.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pseudokrat.recognizers.base import Span

# Anreden — exakte Wortgrenzen.
_SALUTATIONS = r"Herr|Herrn|Frau"

# Rollen-Label aus Lohnkonten, Versicherungs- und Honorarschriftverkehr.
# Trailing ``/in`` und ``/innen`` werden mitgenommen.
_ROLE_LABELS = (
    r"Dienstnehmer|Arbeitnehmer|Arbeitgeber|Antragsteller|Mandant|Klient"
    r"|Versicherter|Versicherte|Bevollmächtigter|Bevollmächtigte"
    r"|Geschäftsführer|Geschäftsführerin|Inhaber|Inhaberin"
    r"|Vertragspartner|Patient|Patientin|Auftraggeber|Auftragnehmer"
)

# Akademische Titel — können sich stapeln (``Frau Prof. Dr. med.``).
# ``DDr.``/``MMag.`` für österreichische Doppelpromotionen.
_TITLES = (
    r"Dr\.|Prof\.|Mag\.|MMag\.|DDr\.|Hon\.-Prof\.|Bakk\.|MSc\.|MA\.|BA\."
    r"|Dipl\.-Ing\.|Dipl\.-Kfm\.|Dipl\.-Kffr\.|Univ\.-Prof\.|Mag\.\(FH\)"
    r"|med\.|jur\.|techn\.|rer\.\s?nat\.|phil\."
)

# Namens-Token: beginnt mit Grossbuchstabe (inkl. Umlaute), erlaubt
# interne Bindestriche (``Müller-Lüdenscheidt``) und Apostrophe
# (``O'Brien``). Mindestens 2 Buchstaben — schliesst „K." als Initial aus.
_NAME_TOKEN = r"[A-ZÄÖÜ][a-zäöüß']+(?:-[A-ZÄÖÜ][a-zäöüß']+)*"

# 1-3 Namens-Tokens — typisch ``Vorname Nachname`` oder
# ``Vorname Zweitname Nachname``.
_NAME_FIELD = rf"{_NAME_TOKEN}(?:[ \t]+{_NAME_TOKEN}){{0,2}}"

# Anrede-Anker: ``Herr <Titel>* <Name>`` — Whitespace reicht als Trenner.
_SALUTATION_RE = re.compile(
    rf"""
    \b (?: {_SALUTATIONS} ) \b
    \s+
    (?: (?: {_TITLES} ) \s+ )*
    (?P<name> {_NAME_FIELD} )
    """,
    re.VERBOSE,
)

# Rollen-Label-Anker: ``Antragsteller: <Titel>* <Name>`` —
# erzwungener ``:``/Dash-Trenner, sonst gleitet der Rollen-Begriff in
# den umgebenden Satz ("Mein Mandant Herr Müller …") und produziert
# unsinnige Namensfelder.
_ROLE_RE = re.compile(
    rf"""
    \b (?: {_ROLE_LABELS} ) (?: / [a-zäöü]+ )? \b
    \s* [:\-—–] \s*
    (?: (?: {_TITLES} ) \s+ )*
    (?P<name> {_NAME_FIELD} )
    """,
    re.VERBOSE,
)

# Stop-Wörter — sehen wie Namen aus, sind aber Funktionswörter.
# Wenn ein gematchtes Namensfeld nur aus Stop-Wörtern besteht,
# verwerfen wir es.
_STOPWORDS = frozenset(
    {
        "Der",
        "Die",
        "Das",
        "Ein",
        "Eine",
        "Einer",
        "Eines",
        "Und",
        "Oder",
        "Aber",
        "Sehr",
        "Geehrte",
        "Geehrter",
        "Damen",
        "Herren",
        "Gmbh",
        "AG",
        "KG",
    }
)


@dataclass(frozen=True)
class _PersonHit:
    start: int
    end: int
    text: str


class PersonRecognizer:
    """Kontext-basierter PERSON-Recognizer (ML-frei)."""

    name = "person"
    category = "PERSON"

    def analyze(self, text: str) -> list[Span]:
        first_pass = list(self._first_pass(text))
        # Second-Pass: bekannte Namensfelder im Resttext wiederfinden.
        all_hits: list[_PersonHit] = list(first_pass)
        seen_names = {hit.text for hit in first_pass}
        for known in seen_names:
            all_hits.extend(self._second_pass(text, known, first_pass))
        # Deduplizieren + nach Position sortieren.
        unique = _dedupe_by_range(all_hits)
        return [
            Span(
                start=hit.start,
                end=hit.end,
                category=self.category,
                text=hit.text,
                score=0.85,
            )
            for hit in unique
        ]

    @staticmethod
    def _first_pass(text: str) -> list[_PersonHit]:
        hits: list[_PersonHit] = []
        for pattern in (_SALUTATION_RE, _ROLE_RE):
            for match in pattern.finditer(text):
                name = match.group("name")
                if _is_stopword_only(name):
                    continue
                start = match.start("name")
                end = match.end("name")
                hits.append(_PersonHit(start=start, end=end, text=name))
        return hits

    @staticmethod
    def _second_pass(
        text: str, known: str, first_pass: list[_PersonHit]
    ) -> list[_PersonHit]:
        """Exakte Vorkommen des bekannten Namens ausserhalb der bereits
        gefundenen Spans."""
        existing_ranges = {(hit.start, hit.end) for hit in first_pass}
        out: list[_PersonHit] = []
        pattern = re.compile(rf"\b{re.escape(known)}\b")
        for m in pattern.finditer(text):
            if (m.start(), m.end()) in existing_ranges:
                continue
            out.append(_PersonHit(start=m.start(), end=m.end(), text=known))
        return out


def _is_stopword_only(name: str) -> bool:
    tokens = re.split(r"[\s\-]+", name)
    return all(tok in _STOPWORDS for tok in tokens)


def _dedupe_by_range(hits: list[_PersonHit]) -> list[_PersonHit]:
    seen: set[tuple[int, int]] = set()
    out: list[_PersonHit] = []
    for hit in sorted(hits, key=lambda h: (h.start, h.end)):
        key = (hit.start, hit.end)
        if key in seen:
            continue
        seen.add(key)
        out.append(hit)
    return out
