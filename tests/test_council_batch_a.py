"""Tests fuer Council-Batch-A: ausl. IBAN, Kreditkarte, SVNR-Plausibilitaet,
Fuzzy-Merge-Schranke, Adress-FP.
"""

from __future__ import annotations

import pytest

from pseudokrat.fuzzy import normalize, should_merge
from pseudokrat.recognizers.creditcard import CreditCardRecognizer
from pseudokrat.recognizers.iban import IBANDachRecognizer, is_valid_iban


class TestForeignIBAN:
    @pytest.mark.parametrize(
        "iban",
        [
            "AT61 1904 3002 3457 3201",  # DACH-Kern bleibt
            "GB82 WEST 1234 5698 7654 32",
            "NL91 ABNA 0417 1643 00",
            "FR14 2004 1010 0505 0001 3M02 606",
        ],
    )
    def test_valid_iban_detected(self, iban: str) -> None:
        assert is_valid_iban(iban)
        spans = IBANDachRecognizer().analyze(f"Konto {iban} bitte")
        assert any(s.category == "IBAN" for s in spans)

    def test_invalid_iban_rejected(self) -> None:
        # falsche Pruefsumme
        assert not is_valid_iban("GB82 WEST 1234 5698 7654 33")


class TestCreditCard:
    def test_luhn_valid_visa(self) -> None:
        spans = CreditCardRecognizer().analyze("Karte 4111 1111 1111 1111 belastet")
        assert [s.category for s in spans] == ["CREDITCARD"]

    def test_luhn_invalid_rejected(self) -> None:
        assert CreditCardRecognizer().analyze("Nummer 1234 5678 9012 3456") == []


class TestFuzzyMerge:
    def _merge(self, a: str, b: str) -> bool:
        return should_merge(normalize(a), normalize(b), "COMPANY")

    def test_separator_variant_merges(self) -> None:
        assert self._merge("Hofer Bau GmbH", "HoferBau GmbH")
        assert self._merge("Hofer Bau GmbH", "Hofer-Bau GmbH")

    def test_different_companies_stay_separate(self) -> None:
        # Maier vs Mayer: verschiedene Firmen, duerfen NICHT kollabieren.
        assert not self._merge("Maier Bau GmbH", "Mayer Bau GmbH")

    def test_long_core_typo_merges(self) -> None:
        assert self._merge("Donauindustrieanlagen GmbH", "Donauindustrieanlgen GmbH")

    def test_different_legal_form_no_merge(self) -> None:
        assert not self._merge("Hofer Bau GmbH", "Hofer Bau KG")
