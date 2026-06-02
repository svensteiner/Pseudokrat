"""PERSON-Recognizer per Vornamen-Liste (Gazetteer) — ML-frei.

Ergaenzt den anker-basierten :class:`PersonRecognizer`: dieser erkennt Namen
nur mit Kontext-Anker (``Herr``/``Frau``/Titel/Rollen-Label). In Tabellen
(z. B. einer Excel-Spalte „Ansprechpartner") steht der Name aber **nackt**
in der Zelle (``Thomas Bauer``) — ohne Anker.

Dieser Recognizer matcht ``Vorname Nachname`` (optional Zweitname), wenn der
erste Token ein bekannter Vorname aus der eingebauten Liste ist. Der/die
Nachname(n) muessen Gross geschrieben sein. Score 0.6 — strukturierte
Recognizer (IBAN, Firma …) und der anker-basierte PersonRecognizer (0.85)
gewinnen bei Ueberlappung.

Bewusst konservativ: ohne bekannten Vornamen kein Match (verhindert, dass
Gross geschriebene Funktionswoerter als Name maskiert werden).
"""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

#: Bekannte Vornamen (Oesterreich/DACH), lowercase. Bewusst breit gehalten.
FIRST_NAMES: frozenset[str] = frozenset(
    {
        # weiblich
        "anna", "maria", "julia", "sandra", "birgit", "eva", "petra", "elisabeth",
        "katharina", "barbara", "sabine", "claudia", "andrea", "christine",
        "monika", "martina", "daniela", "nicole", "stefanie", "tanja", "jasmin",
        "lisa", "laura", "lena", "sarah", "hannah", "lea", "marie", "sophie",
        "johanna", "theresa", "verena", "carina", "melanie", "michaela",
        "gabriele", "renate", "brigitte", "ingrid", "ursula", "helga", "gertrude",
        "angelika", "cornelia", "bettina", "manuela", "doris", "silvia", "karin",
        "isabella", "victoria", "valentina", "magdalena", "emma", "mia", "leonie",
        "alexandra", "natalie", "vanessa", "denise", "kerstin", "simone",
        # maennlich
        "lukas", "florian", "stefan", "markus", "thomas", "andreas", "christoph",
        "michael", "daniel", "david", "patrick", "martin", "alexander", "johannes",
        "sebastian", "philipp", "matthias", "manuel", "dominik", "fabian",
        "tobias", "simon", "felix", "maximilian", "paul", "jakob", "elias",
        "jonas", "moritz", "raphael", "benjamin", "leon", "noah", "samuel",
        "georg", "franz", "josef", "johann", "peter", "hans", "wolfgang",
        "gerhard", "helmut", "herbert", "karl", "walter", "ernst", "friedrich",
        "rudolf", "anton", "alois", "robert", "richard", "klaus", "dieter",
        "guenther", "günther", "werner", "norbert", "harald", "roland", "bernhard",
        "gregor", "rene", "rené", "marcel", "kevin", "nico", "julian", "oliver",
        "roman", "wilhelm", "ludwig", "otto", "bruno", "kurt", "erwin", "gustav",
    }
)

#: Nachname-Token: Gross-Anfang (inkl. Umlaute), Bindestriche erlaubt.
_SURNAME = r"[A-ZÄÖÜ][a-zäöüß']+(?:-[A-ZÄÖÜ][a-zäöüß']+)*"
#: Vorname-Token (wird gegen FIRST_NAMES geprueft).
_FIRST = r"[A-ZÄÖÜ][a-zäöüß']+"

#: Vorname + 1-2 weitere Gross-Tokens (Zweitname/Nachname).
_FULLNAME_RE = re.compile(rf"\b(?P<first>{_FIRST})(?P<rest>(?:[ \t]+{_SURNAME}){{1,2}})\b")


class GazetteerNameRecognizer:
    """Erkennt ``Vorname Nachname`` anhand einer Vornamen-Liste (ML-frei)."""

    name = "person_gazetteer"
    category = "PERSON"

    def analyze(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _FULLNAME_RE.finditer(text):
            if match.group("first").lower() not in FIRST_NAMES:
                continue
            spans.append(
                Span(
                    start=match.start(),
                    end=match.end(),
                    category=self.category,
                    text=match.group(0),
                    score=0.6,
                )
            )
        return spans
