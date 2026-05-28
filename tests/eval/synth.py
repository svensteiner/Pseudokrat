"""Generatoren für gültige (erfundene) DACH-PII-Werte.

Alle Funktionen liefern Werte, die zwar erfunden sind, aber das
**formal korrekte Checksum-Verfahren** durchlaufen — sonst würden die
Recognizer (IBAN-Mod-97, SVNR-Mod-11, Steuer-ID-Mod-11 etc.) die
Fixtures als „kein gültiger PII" einstufen und wir würden Recall
unterschätzen.

Diese Werte dürfen **nie** in produktiven Code oder als Defaults
landen — sie sind ausschließlich für `tests/eval/fixtures/` gedacht.
Reproduzierbar via Seed.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from dataclasses import dataclass


def iban_mod97_ok(iban: str) -> bool:
    """Validiere IBAN per Mod-97-Verfahren."""
    raw = iban.replace(" ", "").upper()
    rearranged = raw[4:] + raw[:4]
    numeric = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    return int(numeric) % 97 == 1


def generate_iban(country: str, bban_digits: int, rng: random.Random) -> str:
    """Erzeuge eine gültige IBAN für AT/DE/CH mit zufälligem BBAN.

    AT: 16 BBAN-Ziffern (4 Bank + 11 Konto + ggf. 1 Pad). Wir nehmen
    16 Ziffern und lassen IBAN-Generator-Algorithmus laufen.
    DE: 18 BBAN-Ziffern (8 Bank + 10 Konto).
    CH: 17 BBAN-Stellen.
    """
    bban = "".join(str(rng.randint(0, 9)) for _ in range(bban_digits))
    # IBAN-Generation: Country + "00" + BBAN → check, dann Checksum berechnen
    rearranged = bban + country + "00"
    numeric = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    checksum = 98 - (int(numeric) % 97)
    return f"{country}{checksum:02d}{bban}"


def generate_at_iban(rng: random.Random) -> str:
    return generate_iban("AT", 16, rng)


def generate_de_iban(rng: random.Random) -> str:
    return generate_iban("DE", 18, rng)


def generate_ch_iban(rng: random.Random) -> str:
    return generate_iban("CH", 17, rng)


# ---------- Österreichische SVNR ----------------------------------------

# 10-stellig: 4 laufende Stellen + 6 Geburtsdatums-Stellen (DDMMYY).
# Prüfziffer = Sum(d_i * w_i) % 11, w = [3, 7, 9, 5, 8, 4, 2, 1, 6]
# Prüfziffer = 10 → die laufende Nummer wird so gewählt, dass das nicht
# passiert (in der Praxis vergibt das HV keine SVNR mit Prüfziffer 10).
_SVNR_WEIGHTS = (3, 7, 9, 5, 8, 4, 2, 1, 6)


def _svnr_check_digit(digits9: str) -> int:
    """Berechne die SVNR-Prüfziffer (die 4. Stelle) aus den anderen 9 Stellen."""
    if len(digits9) != 9 or not digits9.isdigit():
        raise ValueError("digits9 muss exakt 9 Ziffern sein")
    total = sum(int(d) * w for d, w in zip(digits9, _SVNR_WEIGHTS, strict=True))
    return total % 11


def generate_at_svnr(rng: random.Random, *, birth_year: int = 1985) -> str:
    """Erzeuge eine gültige AT-SVNR.

    Layout: ``LLLP DDMMJJ`` (sichtbares Format: ``LLLLDDMMJJ``).
    L = 3 laufende Stellen (Sequenz), P = Prüfziffer, DDMMJJ = Geburtsdatum.
    """
    while True:
        seq = f"{rng.randint(100, 999)}"
        day = rng.randint(1, 28)
        month = rng.randint(1, 12)
        yy = birth_year % 100
        birth = f"{day:02d}{month:02d}{yy:02d}"
        # Reihenfolge in der Prüfung: seq (3) + Geburtsdatum (6) = 9 Stellen
        check = _svnr_check_digit(seq + birth)
        if check < 10:
            return f"{seq}{check}{birth}"
        # bei 10 → neuen Seq würfeln


# ---------- AT-UID (ATU + 8 Ziffern, Luhn-ähnlich) ----------------------

# Algorithmus: 7 Stellen + 1 Prüfziffer.
# Schritt 1: für i=1..7 Cn = digit, wenn i gerade dann *2 und summiere
# die Quersummen; sonst direkt summieren.
# Prüfziffer = (10 - (sum % 10)) % 10  → so dass Gesamt mod 10 = 0


def _at_uid_check_digit(digits7: str) -> int:
    """BMF-Algorithmus: S = d1 + qs(d2*2) + d3 + qs(d4*2) + d5 + qs(d6*2) + d7
    Prüfziffer = (10 - (S + 4) mod 10) mod 10. Konstante +4 ist BMF-spezifisch
    und unterscheidet die UID-Prüfung von normaler Luhn-Validierung."""
    if len(digits7) != 7 or not digits7.isdigit():
        raise ValueError("digits7 muss exakt 7 Ziffern sein")
    d = [int(c) for c in digits7]

    def qs(n: int) -> int:
        return n // 10 + n % 10

    s = d[0] + qs(d[1] * 2) + d[2] + qs(d[3] * 2) + d[4] + qs(d[5] * 2) + d[6]
    return (10 - (s + 4) % 10) % 10


def generate_at_uid(rng: random.Random) -> str:
    digits = "".join(str(rng.randint(0, 9)) for _ in range(7))
    check = _at_uid_check_digit(digits)
    return f"ATU{digits}{check}"


# ---------- DE Steuer-ID (11 Ziffern, § 139b AO) ------------------------

# Eine Ziffer 0-9 erscheint in den ersten 10 Stellen genau 2- oder 3-mal,
# eine andere Ziffer genau 1-mal, die restlichen 0-mal. Vereinfachung
# für unsere Synth-Daten: wir nehmen die "klassische" Form, in der wir
# nur das Pflicht-ISO-7064-Mod-11,10-Check-Digit-Verfahren anwenden,
# weil unser Recognizer das zentrale Validierungskriterium ist.


def _steuer_id_check_digit(digits10: str) -> int:
    """ISO-7064 MOD-11,10 Prüfziffer für die ersten 10 Stellen."""
    if len(digits10) != 10 or not digits10.isdigit():
        raise ValueError("digits10 muss exakt 10 Ziffern sein")
    product = 10
    for ch in digits10:
        s = (int(ch) + product) % 10
        if s == 0:
            s = 10
        product = (s * 2) % 11
    return (11 - product) % 10


def generate_de_steuer_id(rng: random.Random) -> str:
    """§ 139b AO: erste Stelle != 0; in Stellen 1-10 kommt **genau eine**
    Ziffer 2x oder 3x vor, alle anderen Ziffern höchstens 1x. Restliche
    Ziffern dürfen auch 0x vorkommen (damit max. 9 bzw. 8 verschiedene
    Ziffern auftreten). Wir konstruieren das aktiv, statt zu retry-würfeln —
    schneller und garantiert."""
    # Wähle die Wiederhol-Häufigkeit (2x oder 3x) und die wiederholte Ziffer.
    repeat_count = rng.choice([2, 3])
    repeated_digit = rng.randint(0, 9)
    # Wähle die anderen Ziffern: alle 10 möglich außer der wiederholten,
    # davon `10 - repeat_count` Stück, ohne Wiederholung.
    pool = [d for d in range(10) if d != repeated_digit]
    others = rng.sample(pool, 10 - repeat_count)
    # Mische die 10 Stellen.
    ten_digits = [repeated_digit] * repeat_count + others
    rng.shuffle(ten_digits)
    # Erste Stelle darf nicht 0 sein — bei Bedarf rotieren.
    if ten_digits[0] == 0:
        for i in range(1, 10):
            if ten_digits[i] != 0:
                ten_digits[0], ten_digits[i] = ten_digits[i], ten_digits[0]
                break
    digits10 = "".join(str(d) for d in ten_digits)
    check = _steuer_id_check_digit(digits10)
    return digits10 + str(check)


# ---------- CH AHV (Neue 13-stellige Form: 756.XXXX.XXXX.XX) ------------

# EAN-13 Checksum: Sum(d_i * w_i) % 10, w abwechselnd 1 und 3.


def _ahv_check_digit(digits12: str) -> int:
    if len(digits12) != 12 or not digits12.isdigit():
        raise ValueError("digits12 muss exakt 12 Ziffern sein")
    total = 0
    for i, ch in enumerate(digits12):
        d = int(ch)
        weight = 3 if i % 2 == 1 else 1
        total += d * weight
    return (10 - (total % 10)) % 10


def generate_ch_ahv(rng: random.Random) -> str:
    digits = "756" + "".join(str(rng.randint(0, 9)) for _ in range(9))
    check = _ahv_check_digit(digits)
    return f"{digits[:3]}.{digits[3:7]}.{digits[7:11]}.{digits[11:]}{check}"


# ---------- Generator-Coordinator ---------------------------------------


@dataclass(frozen=True)
class SyntheticEntity:
    """Eine synthetisch generierte PII-Entität samt ihres Kategorie-Labels."""

    text: str
    category: str  # entspricht den Pseudokrat-Kategorie-Namen aus den Recognizern


def synth_entities(seed: int) -> Iterator[SyntheticEntity]:
    """Liefert ein deterministisch reproduzierbares Set synthetischer
    Entitäten pro Seed. Praktisch für Eval-Fixture-Generatoren."""
    rng = random.Random(seed)
    yield SyntheticEntity(generate_at_iban(rng), "IBAN")
    yield SyntheticEntity(generate_de_iban(rng), "IBAN")
    yield SyntheticEntity(generate_ch_iban(rng), "IBAN")
    yield SyntheticEntity(generate_at_svnr(rng), "SVNR")
    yield SyntheticEntity(generate_at_uid(rng), "UID")
    yield SyntheticEntity(generate_de_steuer_id(rng), "STEUER_ID")
    yield SyntheticEntity(generate_ch_ahv(rng), "AHV")
