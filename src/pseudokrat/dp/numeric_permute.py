"""Numerische Spalten-Permutation für XLSX-Anonymisierung.

Die Permutation ist:

* **In-Place pro Spalte**: jede Spalte wird unabhängig durchmischt.
* **Deterministisch über einen Schlüssel**: Aus dem Profil-Master-Key
  + Sheet-Name + Spalten-Buchstaben wird ein 32-Byte-Seed abgeleitet.
  Damit erzeugt derselbe Input + dasselbe Profil identische Output —
  Reproduzierbarkeit für nachträgliche Verifikation.
* **Sum-preserving**: Die Menge der Werte bleibt identisch, nur die
  Zuordnung zu Zeilen ändert sich. Mittelwert, Median, Summe, Min/Max,
  Standardabweichung sind vor und nach der Permutation gleich.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from random import Random
from typing import TypeAlias

NumericValue: TypeAlias = int | float


@dataclass(frozen=True)
class PermutationKey:
    """Geheimer Seed für die Spalten-Shuffle.

    Wird beim Profil-Setup einmalig generiert und im Profil-Metadaten-
    Store gehalten. Kommt der Schlüssel weg, kann niemand (auch nicht
    der Profil-Inhaber) die ursprüngliche Zeilen-Zuordnung wiederherstellen.
    """

    key_bytes: bytes

    @classmethod
    def random(cls) -> PermutationKey:
        return cls(key_bytes=secrets.token_bytes(32))

    def seed_for(self, *parts: str) -> int:
        """Subkey-Ableitung. Liefert einen 64-Bit-Int für `random.Random`."""
        hasher = hashlib.sha256(self.key_bytes)
        for part in parts:
            hasher.update(b"\x00")
            hasher.update(part.encode("utf-8"))
        digest = hasher.digest()
        return int.from_bytes(digest[:8], "big")


def permutation_key_from_secret(secret: bytes) -> PermutationKey:
    """Leite einen Permutations-Schlüssel aus einem bestehenden Master-Secret ab.

    Wird vom MappingStore aufgerufen — der Permutation-Schlüssel
    ist domain-separated von Fernet/HMAC/SQLCipher-Schlüsseln durch
    den eigenen SHA-256-Tag.
    """
    derived = hashlib.sha256(b"pseudokrat-dp-permute-v1" + secret).digest()
    return PermutationKey(key_bytes=derived)


def _shuffle_in_place(values: list[int], rng: Random) -> None:
    """Fisher-Yates auf einer Index-Liste — deterministisch unter `rng`."""
    n = len(values)
    for i in range(n - 1, 0, -1):
        j = rng.randrange(i + 1)
        if i != j:
            values[i], values[j] = values[j], values[i]


def shuffle_column(values: Sequence[NumericValue | None], seed: int) -> list[NumericValue | None]:
    """Permutiere alle numerischen Werte einer Spalte; ``None`` bleibt am Platz.

    None-Zellen (leere Zeilen) werden NICHT in die Permutation
    einbezogen — das vermeidet, dass leere Tabellenzellen plötzlich
    Werte enthalten und Pivot-Tabellen kaputtgehen.
    """
    rng = Random(seed)
    numeric_positions = [i for i, v in enumerate(values) if v is not None]
    if len(numeric_positions) <= 1:
        return list(values)
    permutation = list(range(len(numeric_positions)))
    _shuffle_in_place(permutation, rng)
    out: list[NumericValue | None] = list(values)
    for src, dst in zip(numeric_positions, permutation, strict=True):
        out[numeric_positions[dst]] = values[src]
    return out


def shuffle_numeric_columns(
    workbook: object,  # openpyxl.Workbook — lazy-typed to keep import light
    key: PermutationKey,
) -> int:
    """Shuffle alle numerischen Spalten **außer** Header-Zeile (Row 1).

    Liefert die Gesamtzahl permutierter Spalten zurück. Formel-Zellen
    werden nicht angefasst; nur Zellen mit ``data_type == 'n'``.

    **Heuristik Header-Zeile**: Zeile 1 wird als Header behandelt und
    bleibt unangetastet (häufiges Excel-Schema). Wenn der Nutzer das
    nicht will, soll er die Daten mit Header in Row 2 organisieren.
    """
    permuted_columns = 0
    for sheet in workbook.worksheets:  # type: ignore[attr-defined]
        max_col = sheet.max_column
        max_row = sheet.max_row
        if max_row <= 1:
            continue
        for col_idx in range(1, max_col + 1):
            col_letter = sheet.cell(row=1, column=col_idx).column_letter
            cells = [sheet.cell(row=r, column=col_idx) for r in range(2, max_row + 1)]
            values: list[NumericValue | None] = []
            for c in cells:
                if c.data_type == "n" and isinstance(c.value, (int, float)):
                    values.append(c.value)
                else:
                    values.append(None)
            if sum(1 for v in values if v is not None) < 2:
                continue
            seed = key.seed_for(sheet.title, col_letter)
            shuffled = shuffle_column(values, seed=seed)
            for cell, new_val in zip(cells, shuffled, strict=True):
                if new_val is not None:
                    cell.value = new_val
            # Eine Spalte zählt als „permutiert", sobald wir sie behandelt
            # haben — auch wenn die zufällig gezogene Permutation die
            # Identität war (kleine Spalten: P=1/n!). Das entspricht der
            # DP-Semantik „die Spalte ist anonymisiert worden".
            permuted_columns += 1
    return permuted_columns


def column_stats(values: Iterable[NumericValue]) -> dict[str, float]:
    """Sanity-Stats für Tests: Summe, Mittelwert, Min, Max, Anzahl."""
    seq = list(values)
    if not seq:
        return {"count": 0, "sum": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0}
    s = float(sum(seq))
    return {
        "count": len(seq),
        "sum": s,
        "mean": s / len(seq),
        "min": float(min(seq)),
        "max": float(max(seq)),
    }
