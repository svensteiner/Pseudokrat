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
        # weiblich (erweitert)
        "agnes", "amelie", "annemarie", "antonia", "astrid", "beate", "bianca",
        "carmen", "caroline", "charlotte", "christa", "clara", "claudia", "diana",
        "edith", "elena", "elfriede", "elke", "emilia", "ella", "erika", "esther",
        "evelyn", "franziska", "frieda", "gisela", "gudrun", "hanna", "hedwig",
        "heidi", "heike", "helene", "henriette", "hermine", "hildegard", "ilse",
        "ines", "irene", "iris", "jana", "janine", "jennifer", "jessica", "josefine",
        "judith", "jutta", "kathrin", "klara", "kristina", "lara", "larissa",
        "laurin", "lilly", "lina", "linda", "lotte", "luisa", "luise", "marianne",
        "marlene", "mathilde", "melissa", "mira", "miriam", "nadja", "nadine",
        "nora", "olga", "paula", "pia", "regina", "rosa", "roswitha", "ruth",
        "selina", "sieglinde", "sofia", "sonja", "stephanie", "susanne", "tamara",
        "teresa", "ulrike", "ute", "waltraud", "yvonne",
        # maennlich (erweitert)
        "achim", "adam", "adrian", "albert", "albin", "alfred", "armin", "arnold",
        "arthur", "august", "axel", "bastian", "benedikt", "bernd", "bernhardt",
        "carl", "christian", "clemens", "constantin", "cornelius", "damian",
        "denis", "detlef", "diethard", "dietmar", "dirk", "edgar", "eduard",
        "egon", "emanuel", "emil", "engelbert", "enrico", "erich", "ferdinand",
        "frank", "fritz", "gabriel", "günter", "guido", "hannes", "hartmut",
        "heinrich", "heinz", "hellmuth", "holger", "horst", "hubert", "ignaz",
        "ingo", "jan", "joachim", "joel", "joerg", "jörg", "jonathan", "jürgen",
        "juergen", "kaspar", "konrad", "konstantin", "leopold", "lorenz", "marc",
        "mario", "matteo", "matthäus", "maurice", "max", "meinrad", "nikolaus",
        "olaf", "oskar", "pascal", "patric", "raimund", "rainer", "ralf", "ralph",
        "reinhard", "reinhold", "remo", "rolf", "ruben", "siegfried", "sigmund",
        "sven", "theodor", "theo", "tim", "timo", "tom", "ulrich", "urban",
        "valentin", "viktor", "vincent", "volker", "willibald", "xaver",
        # international / in Oesterreich gebraeuchlich
        "aleksandar", "ali", "amir", "ana", "ante", "denis", "dragan", "emir",
        "fatima", "filip", "goran", "hasan", "ivan", "ivana", "luka", "marko",
        "mehmet", "milan", "mohammed", "murat", "nina", "petar", "sara",
        "stefano", "tobias", "vladimir", "zoran",
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
