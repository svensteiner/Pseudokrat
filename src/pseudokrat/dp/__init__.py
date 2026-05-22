"""Differential-Privacy-Hilfen für Beträge in tabellarischen Daten.

Aktuell implementiert: **rangbewahrende Permutation** innerhalb einer
Spalte. Die Permutation lässt Mittelwert, Median, Standardabweichung,
Summe und Min/Max bit-genau erhalten — der Auditor sieht dieselben
statistischen Kennzahlen, kann aber **nicht** mehr ableiten, welcher
Mandant welchen konkreten Betrag bekommt.

Optional aktivierbar ist Laplace-Noise (deterministisch über einen
Profil-Seed) für stärkere DP-Garantien — bewusst NICHT default, weil
es Summen verändert (relevant für ``SUMIF``-basierte Pivots).
"""

from pseudokrat.dp.numeric_permute import (
    PermutationKey,
    permutation_key_from_secret,
    shuffle_numeric_columns,
)

__all__ = [
    "PermutationKey",
    "permutation_key_from_secret",
    "shuffle_numeric_columns",
]
