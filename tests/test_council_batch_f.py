"""Tests fuer Council-Batch-F: AT-Register (GISA/DVR/Grundbuch), Konto+BLZ,
HTML data:-URI-Entfernung."""

from __future__ import annotations

from pathlib import Path

from pseudokrat.formats.html_handler import HtmlHandler
from pseudokrat.recognizers.at_konto_blz import AustrianKontoBlzRecognizer
from pseudokrat.recognizers.at_register import AustrianRegisterRecognizer


class TestRegister:
    def test_gisa(self) -> None:
        cats = {s.category for s in AustrianRegisterRecognizer().analyze("GISA-Zahl: 12345678")}
        assert "GISA" in cats

    def test_dvr(self) -> None:
        cats = {s.category for s in AustrianRegisterRecognizer().analyze("DVR: 1234567")}
        assert "DVR" in cats

    def test_grundbuch_ez_and_kg(self) -> None:
        r = AustrianRegisterRecognizer()
        assert any(s.category == "GRUNDBUCH" for s in r.analyze("Einlagezahl 123"))
        assert any(s.category == "GRUNDBUCH" for s in r.analyze("KG 12345"))

    def test_legal_form_kg_not_matched(self) -> None:
        # „Hofer KG" (Rechtsform) darf NICHT als Grundbuch-KG greifen.
        assert AustrianRegisterRecognizer().analyze("Hofer Bau KG") == []


class TestKontoBlz:
    def test_blz(self) -> None:
        cats = {s.category for s in AustrianKontoBlzRecognizer().analyze("BLZ: 12345")}
        assert "BLZ" in cats

    def test_konto(self) -> None:
        cats = {s.category for s in AustrianKontoBlzRecognizer().analyze("Kontonummer: 1234567")}
        assert "KONTO" in cats

    def test_bare_number_not_matched(self) -> None:
        assert AustrianKontoBlzRecognizer().analyze("Die Zahl 1234567 steht dort") == []


class TestHtmlDataUri:
    def test_data_uri_removed(self, tmp_path: Path) -> None:
        src = tmp_path / "in.html"
        src.write_text(
            '<img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB">',
            encoding="utf-8",
        )
        out = tmp_path / "out.html"
        HtmlHandler().process(src, out, transform=lambda t: t)
        result = out.read_text(encoding="utf-8")
        assert "iVBORw0KGgo" not in result
        assert "data:removed" in result
