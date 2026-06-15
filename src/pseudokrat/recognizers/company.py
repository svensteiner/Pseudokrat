"""Firmen-Recognizer auf Basis von Rechtsform-Suffixen.

Erkennt Spans der Form ``<Großbuchstabe...> <Rechtsform>``, z. B.
„Hofer Bau GmbH", „Müller & Söhne KG".

Regelwerk:

* 1–3 Tokens vor dem Rechtsform-Suffix.
* Tokens müssen mit Großbuchstabe oder „&" beginnen.
* Leading-Stoplist (deutsche Artikel/Präpositionen) wird abgeschnitten,
  z. B. „Die Hofer GmbH" → „Hofer GmbH".
* Bei Überlappung gewinnt der längere Span.
"""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

# Reihenfolge zählt: längere/zusammengesetzte Formen zuerst.
_LEGAL_FORMS_ORDERED: tuple[str, ...] = (
    "GmbH & Co. KG",
    "GmbH & Co KG",
    "GmbH und Co. KG",
    "GmbH und Co KG",
    "AG & Co. KG",
    "AG & Co KG",
    "AG & Co. KGaA",
    "Stiftung & Co. KG",
    "KGaA",
    "GmbH",
    "AöR",
    "OHG",
    "KG",
    "AG",
    "SE",
    "OG",
    "UG",
    "e.U.",
    "e.V.",
    "e.G.",
    "eG",
    "gAG",
    "S.A.R.L.",
    "SARL",
    "S.p.A.",
    "SpA",
    "Limited",
    "Ltd.",
    "Ltd",
    "LLC",
    "Inc.",
    "Inc",
    "Corp.",
    "Corp",
    # Internationale Rechtsformen (Beteiligungen, Komplementaer/Kommanditist).
    "S.P.R.L.",
    "SPRL",
    "S.R.L.",
    "SRL",
    "Sp. z o.o.",
    "d.o.o.",
    "B.V.",
    "N.V.",
    "S.L.",
    "S.A.",
    "plc",
    "PLC",
)

# Häufige deutsche Artikel/Präpositionen, die nicht Teil eines Firmennamens sein dürfen.
_LEADING_STOPWORDS: frozenset[str] = frozenset(
    {
        "der",
        "die",
        "das",
        "dem",
        "den",
        "des",
        "ein",
        "eine",
        "einer",
        "eines",
        "einem",
        "einen",
        "mit",
        "von",
        "vom",
        "zur",
        "zum",
        "im",
        "ins",
        "am",
        "an",
        "bei",
        "beim",
        "auf",
        "für",
        "fuer",
        "durch",
        "ohne",
        "um",
        "unser",
        "unsere",
        "unseren",
        "unserer",
        "unseres",
        "unserem",
        "dieser",
        "diese",
        "dieses",
        "diesen",
        "diesem",
        "jeder",
        "jede",
        "jedes",
        "jeden",
        "jedem",
        "alle",
        "allen",
        "aller",
        "alles",
        "kein",
        "keine",
        "keinen",
        "keiner",
        "keines",
        "mein",
        "meine",
        "meinen",
        "meiner",
        "meines",
        "meinem",
        "dein",
        "deine",
        "deinen",
        "sein",
        "seine",
        "seinen",
        "seiner",
        "seines",
        "ihr",
        "ihre",
        "ihren",
        "ihrer",
        "ihres",
        "ihrem",
        "wir",
        "sie",
        "er",
        "es",
        "und",
        "oder",
        "auch",
        "wie",
        "als",
    }
)


def _legal_form_alternation() -> str:
    return "|".join(re.escape(form) for form in _LEGAL_FORMS_ORDERED)


# Tokens vor der Rechtsform: 1–3 Wörter (das obere Limit kommt aus §7 des
# Megaprompts: „bis zu 4 Tokens vor dem Rechtsform-Suffix" wurde in der Praxis
# auf 3 reduziert — vier-Token-Firmennamen sind selten und der breitere Regex
# fängt regelmäßig falsche Präfixe wie „Vertrag mit Hofer Bau GmbH"). Korrekt
# geschriebene Firmennamen beginnen mit Großbuchstabe, aber wir akzeptieren
# auch lowercase, da die Rechtsform selbst (mit ihrer typischen Großschreibung
# „GmbH"/„AG"/…) das starke Signal liefert. Punkte im Namens-Token NICHT
# erlaubt, sonst frisst der Regex Satzgrenzen („Firma. Auch hofer bau GmbH").
# Punkte in Rechtsformen sind im Legal-Form-Alternation separat behandelt.
_NAME_TOKEN = r"(?:[A-Za-zÄÖÜäöüß&][\wäöüß&\-]*)"
_NAME_PART = rf"(?:{_NAME_TOKEN}(?:[ \-]+{_NAME_TOKEN}){{0,2}})"
_COMPANY_RE = re.compile(rf"\b{_NAME_PART}[ ](?:{_legal_form_alternation()})(?!\w)")


def detect_legal_form_suffix(text: str) -> str | None:
    """Welche Rechtsform endet diesen String? Längste zuerst."""
    for form in _LEGAL_FORMS_ORDERED:
        if text.endswith(form):
            preceding = text[: -len(form)]
            if not preceding or preceding[-1] in " \t":
                return form
    return None


def _trim_leading_stopwords(raw: str) -> str:
    """Schneide Artikel/Präpositionen am Anfang ab.

    „Die Hofer GmbH" → „Hofer GmbH", „Mit der Hofer GmbH" → „Hofer GmbH".
    """
    tokens = raw.split(" ")
    while len(tokens) > 2 and tokens[0].lower() in _LEADING_STOPWORDS:
        tokens = tokens[1:]
    return " ".join(tokens)


class CompanyLegalFormRecognizer:
    """Erkennt Firmen anhand Rechtsform-Suffix."""

    name = "company_legal_form"
    category = "COMPANY"

    def analyze(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _COMPANY_RE.finditer(text):
            raw = match.group(0)
            trimmed = _trim_leading_stopwords(raw)
            if not trimmed:
                continue
            # Neue Start-Position nach Trimm.
            offset = len(raw) - len(trimmed)
            start = match.start() + offset
            end = match.end()
            spans.append(
                Span(
                    start=start,
                    end=end,
                    category=self.category,
                    text=text[start:end],
                    score=0.8,
                )
            )
        return self._dedupe_longest(spans)

    @staticmethod
    def _dedupe_longest(spans: list[Span]) -> list[Span]:
        """Wenn zwei Spans überlappen, behalte den längeren."""
        if not spans:
            return []
        sorted_spans = sorted(spans, key=lambda s: (s.start, -(s.end - s.start)))
        result: list[Span] = []
        for span in sorted_spans:
            if result and span.start < result[-1].end:
                if (span.end - span.start) > (result[-1].end - result[-1].start):
                    result[-1] = span
                continue
            result.append(span)
        return result
