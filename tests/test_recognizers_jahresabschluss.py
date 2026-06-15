"""Tests fuer die Jahresabschluss-/Rechtsverhaeltnisse-Erkenner:

- FirmenbuchRecognizer (FN ...)
- AustrianSteuernummerRecognizer (FA NNN/NNNN)
- AddressRecognizer: umgekehrte Reihenfolge + Pipe-Trenner
- CompanyLegalFormRecognizer: auslaendische Rechtsformen (SRL/SPRL)
- PersonRecognizer: Rollen-Anker Kommanditist/Funktionstraeger/...

Alle Strings synthetisch.
"""

from __future__ import annotations

import pytest

from pseudokrat.recognizers import default_recognizers
from pseudokrat.recognizers.address import AddressRecognizer
from pseudokrat.recognizers.at_steuernummer import AustrianSteuernummerRecognizer
from pseudokrat.recognizers.firmenbuch import FirmenbuchRecognizer


def _cats(text: str) -> set[str]:
    cats: set[str] = set()
    for r in default_recognizers():
        for s in r.analyze(text):
            cats.add(s.category)
    return cats


class TestFirmenbuch:
    def test_fn_with_space(self) -> None:
        spans = FirmenbuchRecognizer().analyze("Handelsgericht Wien, FN 678901z")
        assert [s.text for s in spans] == ["FN 678901z"]
        assert spans[0].category == "FN"

    def test_fn_without_space(self) -> None:
        assert FirmenbuchRecognizer().analyze("FN12345a")[0].text == "FN12345a"

    def test_no_false_positive_plain_word(self) -> None:
        assert FirmenbuchRecognizer().analyze("Die Firma zahlt.") == []


class TestSteuernummer:
    def test_with_suffix(self) -> None:
        spans = AustrianSteuernummerRecognizer().analyze("StNr 12 345/6789-01 gemeldet")
        assert spans and spans[0].text == "12 345/6789-01"
        assert spans[0].category == "STEUERNR"

    def test_dash_separator(self) -> None:
        assert AustrianSteuernummerRecognizer().analyze("12-345/6789")[0].text == "12-345/6789"


class TestAddressOrders:
    def test_reversed_order(self) -> None:
        spans = AddressRecognizer().analyze("Sitz: 1234 Teststadt, Beispielplatz 5")
        assert any(s.text == "1234 Teststadt, Beispielplatz 5" for s in spans)

    def test_pipe_separator(self) -> None:
        spans = AddressRecognizer().analyze("Beispielgasse 8 | 1234 Teststadt")
        assert any(s.text == "Beispielgasse 8 | 1234 Teststadt" for s in spans)

    def test_normal_order_still_works(self) -> None:
        spans = AddressRecognizer().analyze("Beispielplatz 5, 1234 Teststadt")
        assert any(s.text == "Beispielplatz 5, 1234 Teststadt" for s in spans)


class TestForeignLegalForms:
    @pytest.mark.parametrize("suffix", ["SRL", "SPRL"])
    def test_foreign_company(self, suffix: str) -> None:
        assert "COMPANY" in _cats(f"Test Global Belgium {suffix}")


class TestRoleAnchors:
    def test_funktionstraeger_anchor(self) -> None:
        # Vorname nicht in der Gazetteer-Liste -> nur der Rollen-Anker greift.
        assert "PERSON" in _cats("Funktionsträger: Zalan Northrip")

    def test_kommanditist_anchor(self) -> None:
        assert _cats("Kommanditist: Quintus Falkenrath") >= {"PERSON"}
