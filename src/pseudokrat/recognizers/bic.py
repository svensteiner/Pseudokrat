"""BIC / SWIFT-Code-Recognizer (ISO 9362).

Format: ``AAAA BB CC [XXX]``

* 4 Buchstaben — Bank-Code (institutional code, A-Z)
* 2 Buchstaben — ISO-3166-1 Alpha-2 Country-Code
* 2 alphanumerisch — Location-Code (Stadt/Region; A-Z, 0-9, kein O/I am
  Position 1 nach Standard, aber wir akzeptieren der Robustheit halber)
* 3 alphanumerisch (optional) — Branch-Code

Gesamtlänge: 8 oder 11 Zeichen, **nicht 9 oder 10**.

Beispiele:

* ``DEUTDEFF``     — Deutsche Bank Frankfurt, 8 Zeichen
* ``DEUTDEFFXXX``  — selbe Bank, primary office, 11 Zeichen
* ``GIBAATWWXXX``  — Erste Bank Wien

Validierung in dieser Reihenfolge:

1. Strict-Regex über Wortgrenze.
2. Country-Code muss ein bekannter ISO-3166-1-Alpha-2-Code sein
   (Mini-Whitelist von ~250 Codes; siehe :data:`_ISO_3166_ALPHA2`).

False-Positive-Schutz: BIC-Format kollidiert mit beliebigen UPPER-CASE-
Sequenzen wie „SCHWEIZ", „MUSTER" etc. Country-Code-Check filtert die
groben Fehlmatches; ein endgültig falscher Match ist nur möglich, wenn
zufällig die Country-Stelle einem gültigen ISO-Code entspricht — in der
Praxis selten genug, um keinen False-Positive-Cluster zu erzeugen.
"""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

# ISO-3166-1 Alpha-2: ~250 Codes (Stand 2025).
# Statisch deklariert, damit Ruff SIM905 nicht meckert — und damit das
# Modul nicht bei jedem Import str.split() ausführt.
_ISO_3166_ALPHA2: frozenset[str] = frozenset(
    [
        "AD",
        "AE",
        "AF",
        "AG",
        "AI",
        "AL",
        "AM",
        "AO",
        "AQ",
        "AR",
        "AS",
        "AT",
        "AU",
        "AW",
        "AX",
        "AZ",
        "BA",
        "BB",
        "BD",
        "BE",
        "BF",
        "BG",
        "BH",
        "BI",
        "BJ",
        "BL",
        "BM",
        "BN",
        "BO",
        "BQ",
        "BR",
        "BS",
        "BT",
        "BV",
        "BW",
        "BY",
        "BZ",
        "CA",
        "CC",
        "CD",
        "CF",
        "CG",
        "CH",
        "CI",
        "CK",
        "CL",
        "CM",
        "CN",
        "CO",
        "CR",
        "CU",
        "CV",
        "CW",
        "CX",
        "CY",
        "CZ",
        "DE",
        "DJ",
        "DK",
        "DM",
        "DO",
        "DZ",
        "EC",
        "EE",
        "EG",
        "EH",
        "ER",
        "ES",
        "ET",
        "FI",
        "FJ",
        "FK",
        "FM",
        "FO",
        "FR",
        "GA",
        "GB",
        "GD",
        "GE",
        "GF",
        "GG",
        "GH",
        "GI",
        "GL",
        "GM",
        "GN",
        "GP",
        "GQ",
        "GR",
        "GS",
        "GT",
        "GU",
        "GW",
        "GY",
        "HK",
        "HM",
        "HN",
        "HR",
        "HT",
        "HU",
        "ID",
        "IE",
        "IL",
        "IM",
        "IN",
        "IO",
        "IQ",
        "IR",
        "IS",
        "IT",
        "JE",
        "JM",
        "JO",
        "JP",
        "KE",
        "KG",
        "KH",
        "KI",
        "KM",
        "KN",
        "KP",
        "KR",
        "KW",
        "KY",
        "KZ",
        "LA",
        "LB",
        "LC",
        "LI",
        "LK",
        "LR",
        "LS",
        "LT",
        "LU",
        "LV",
        "LY",
        "MA",
        "MC",
        "MD",
        "ME",
        "MF",
        "MG",
        "MH",
        "MK",
        "ML",
        "MM",
        "MN",
        "MO",
        "MP",
        "MQ",
        "MR",
        "MS",
        "MT",
        "MU",
        "MV",
        "MW",
        "MX",
        "MY",
        "MZ",
        "NA",
        "NC",
        "NE",
        "NF",
        "NG",
        "NI",
        "NL",
        "NO",
        "NP",
        "NR",
        "NU",
        "NZ",
        "OM",
        "PA",
        "PE",
        "PF",
        "PG",
        "PH",
        "PK",
        "PL",
        "PM",
        "PN",
        "PR",
        "PS",
        "PT",
        "PW",
        "PY",
        "QA",
        "RE",
        "RO",
        "RS",
        "RU",
        "RW",
        "SA",
        "SB",
        "SC",
        "SD",
        "SE",
        "SG",
        "SH",
        "SI",
        "SJ",
        "SK",
        "SL",
        "SM",
        "SN",
        "SO",
        "SR",
        "SS",
        "ST",
        "SV",
        "SX",
        "SY",
        "SZ",
        "TC",
        "TD",
        "TF",
        "TG",
        "TH",
        "TJ",
        "TK",
        "TL",
        "TM",
        "TN",
        "TO",
        "TR",
        "TT",
        "TV",
        "TW",
        "TZ",
        "UA",
        "UG",
        "UM",
        "US",
        "UY",
        "UZ",
        "VA",
        "VC",
        "VE",
        "VG",
        "VI",
        "VN",
        "VU",
        "WF",
        "WS",
        "YE",
        "YT",
        "ZA",
        "ZM",
        "ZW",
    ]
)

# Strict-Form: 4 letters + 2 letters (country) + 2 alphanumeric (location)
# + optional 3 alphanumeric (branch). Gesamtlänge 8 oder 11.
_BIC_RE = re.compile(r"\b([A-Z]{4})([A-Z]{2})([A-Z0-9]{2})([A-Z0-9]{3})?\b")

#: Kontext-Schlüsselwörter, die VOR einem BIC-Kandidaten innerhalb eines
#: kleinen Fensters stehen müssen. ISO-9362-Format kollidiert mit
#: vielen deutschen Groß-Wörtern (NEUERUNG=NEUE+RU+NG, DEUTSCHLAND=
#: DEUT+SC+HL+AND, ...) — pure Formvalidierung produziert sonst False
#: Positives.
_BIC_CONTEXT_KEYWORDS: tuple[str, ...] = (
    "BIC",
    "SWIFT",
    "BANK-IDENTIFIER",
    "BANK IDENTIFIER",
)

#: Wieviele Zeichen VOR dem BIC-Kandidaten gescannt werden.
_BIC_CONTEXT_WINDOW = 40


def is_valid_bic(candidate: str) -> bool:
    """Validiere einen BIC-Kandidaten gemäß ISO-9362-Form und Country-Code.

    **Nur Format-Check**, keine Kontext-Anforderung — gedacht für Tests
    und für externe Anrufer, die einen Wert bereits als BIC ankündigen.
    """
    m = _BIC_RE.fullmatch(candidate)
    if m is None:
        return False
    country = m.group(2)
    return country in _ISO_3166_ALPHA2


def _has_context_keyword(text: str, match_start: int) -> bool:
    """Prüfe, ob VOR ``match_start`` (innerhalb ``_BIC_CONTEXT_WINDOW``
    Zeichen) eines der Kontext-Keywords steht."""
    window_start = max(0, match_start - _BIC_CONTEXT_WINDOW)
    window = text[window_start:match_start].upper()
    return any(kw in window for kw in _BIC_CONTEXT_KEYWORDS)


class BICRecognizer:
    """SWIFT-/BIC-Codes nach ISO 9362.

    Validierung in zwei Stufen:

    1. Format-Regex + ISO-3166-Country-Code-Whitelist.
    2. Kontext-Keyword (``BIC``, ``SWIFT`` u. ä.) innerhalb von
       ``_BIC_CONTEXT_WINDOW`` Zeichen VOR dem Match.

    Stufe 2 ist nötig, weil das ISO-9362-Format mit alltäglichen
    deutschen Groß-Wörtern kollidiert (z. B. ``NEUERUNG``,
    ``DEUTSCHLAND``). DACH-Banking-Dokumente labeln BICs in der
    Praxis fast immer mit ``BIC`` oder ``SWIFT`` davor — daher ist
    die Kontext-Anforderung in der Domäne robust.
    """

    name = "bic"
    category = "BIC"

    def analyze(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for match in _BIC_RE.finditer(text):
            country = match.group(2)
            if country not in _ISO_3166_ALPHA2:
                continue
            if not _has_context_keyword(text, match.start()):
                continue
            spans.append(
                Span(
                    start=match.start(),
                    end=match.end(),
                    category=self.category,
                    text=match.group(0),
                    score=0.95,
                )
            )
        return spans
