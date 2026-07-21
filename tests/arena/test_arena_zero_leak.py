"""CI-Tor der Testarena.

Schreibt die heutige Anonymisierungs-Garantie fest:

* Das Leck-Tor erkennt eingebaute Lecks (Negativ-Kontrolle).
* Über alle NICHT-Personen-Kategorien (IBAN, SVNR, UID, Steuer-ID,
  USt-IdNr, AHV, BIC, E-Mail, Telefon, Geburtsdatum, Adresse, Firma)
  tritt **kein** Leck auf.
* Einfache Personennamen (ohne Adelsprädikat) lecken nicht.
* Adelsprädikat-Namen (von/zu/van der) lecken auch in schwachem Kontext
  nicht (unbekannter Titel wie ``DI``, Rollen-Label).
* Die Rückübersetzung stellt jedes Dokument exakt wieder her.

Hinweis: Die früher als ``xfail`` geführte Adelsprädikat-Lücke wurde in
PRL Iter-17 geschlossen (Titel-Liste erweitert + Gazetteer-Konnektor-Pfad
gehärtet). Der Test ist jetzt ein hartes Regressions-Gate.
"""

from __future__ import annotations

import re

import pytest

from tests.arena.runner import negative_control, run

_NOBILIARY = re.compile(r"\b(von|zu|van der)\b")

# Ein moderater Korpus genügt fürs Gate; der große Belastungslauf läuft
# über ``python -m tests.arena.runner``.
_GATE_COUNT = 180


@pytest.fixture(scope="module")
def summary():
    return run(_GATE_COUNT, seed=0)


def test_negative_control_detects_leaks() -> None:
    assert negative_control(seed=0), "Leck-Tor erkennt kein eingebautes Leck."


def test_roundtrip_is_lossless(summary) -> None:
    assert summary.roundtrip_failures == 0


def test_non_person_categories_are_leak_free(summary) -> None:
    offenders = [lk for lk in summary.leaks if lk.category != "PERSON"]
    assert not offenders, f"Unerwartete Lecks außerhalb PERSON: {offenders}"


def test_plain_person_names_are_leak_free(summary) -> None:
    plain = [
        lk for lk in summary.leaks if lk.category == "PERSON" and not _NOBILIARY.search(lk.value)
    ]
    assert not plain, f"Einfacher Personenname geleckt: {plain}"


def test_nobiliary_person_names_are_leak_free(summary) -> None:
    nobiliary = [
        lk for lk in summary.leaks if lk.category == "PERSON" and _NOBILIARY.search(lk.value)
    ]
    assert not nobiliary, f"Adelsprädikat-Name geleckt: {len(nobiliary)} Fälle"
