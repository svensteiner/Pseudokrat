"""Tests für die Ordner-Schiene (pseudokrat.watcher) und die CLI-Befehle
``watch`` / ``setup``.

Schwerpunkt: die ML-freien Bausteine (Begriffe-Laden, TermRecognizer) sowie
ein vollstaendiger Anonymisieren->Rueckuebersetzen-Roundtrip. PDF-spezifische
Tests werden uebersprungen, wenn PyMuPDF nicht installiert ist.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pseudokrat import watcher

# Eine im README dokumentierte, MOD-97-gueltige AT-IBAN.
VALID_IBAN = "AT611904300234573201"


class TestLoadTerms:
    def test_missing_file(self, tmp_path: Path) -> None:
        assert watcher.load_terms(tmp_path / "fehlt.txt") == []

    def test_reads_terms_and_skips_comments(self, tmp_path: Path) -> None:
        p = tmp_path / "Begriffe.txt"
        p.write_text("# Kommentar\nM&D\n\n  Dunkin  \n", encoding="utf-8")
        assert watcher.load_terms(p) == ["M&D", "Dunkin"]


class TestTermRecognizer:
    def test_matches_case_insensitive(self) -> None:
        rec = watcher.TermRecognizer(["M&D", "Dunkin"])
        spans = rec.analyze("Die m&d laut DUNKIN Auswertung")
        assert {s.category for s in spans} == {"BEGRIFF"}
        assert sorted(s.text.lower() for s in spans) == ["dunkin", "m&d"]

    def test_empty_terms(self) -> None:
        assert watcher.TermRecognizer([]).analyze("egal") == []


class TestRoundtrip:
    def test_anonymize_then_deanonymize_restores_original(
        self, store_and_audit: tuple[object, object]
    ) -> None:
        from pseudokrat.anonymizer import Anonymizer
        from pseudokrat.deanonymizer import Deanonymizer
        from pseudokrat.recognizers import recognizers_for_store

        store, audit = store_and_audit
        anon = Anonymizer(
            store=store,
            recognizers=recognizers_for_store(store),
            detector=None,
            audit_log=audit,
            model_version="disabled",
        )
        de = Deanonymizer(store=store, audit_log=audit, model_version="disabled")

        text = f"Hofer Bau GmbH zahlt auf {VALID_IBAN}."
        anonymized = anon.anonymize(text).text
        assert "Hofer Bau GmbH" not in anonymized
        assert VALID_IBAN not in anonymized
        assert "<COMPANY_" in anonymized and "<IBAN_" in anonymized

        restored = de.deanonymize(anonymized).text
        assert restored == text


class TestRedactPdf:
    def test_pdf_redaction_roundtrip(
        self, tmp_path: Path, store_and_audit: tuple[object, object]
    ) -> None:
        pymupdf = pytest.importorskip("pymupdf")
        from pseudokrat.anonymizer import Anonymizer
        from pseudokrat.deanonymizer import Deanonymizer
        from pseudokrat.recognizers import recognizers_for_store

        store, audit = store_and_audit
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hofer Bau GmbH zahlt heute.")
        src = tmp_path / "in.pdf"
        doc.save(str(src))
        doc.close()

        anon = Anonymizer(
            store=store,
            recognizers=recognizers_for_store(store),
            detector=None,
            audit_log=audit,
            model_version="disabled",
        )
        out = tmp_path / "out.pdf"
        hits = watcher.redact_pdf(
            src, out, anon, store, remove_logos=True, ocr=None, log=lambda _m: None
        )
        assert hits >= 1

        text = "".join(p.get_text() for p in pymupdf.open(str(out)))
        assert "Hofer Bau GmbH" not in text
        assert "<COMPANY_" in text

        # Rueckuebersetzung der PDF stellt den Originalnamen wieder her.
        de = Deanonymizer(store=store, audit_log=audit, model_version="disabled")
        back = tmp_path / "back.pdf"
        watcher.deanon_pdf(out, back, de)
        back_text = "".join(p.get_text() for p in pymupdf.open(str(back)))
        assert "Hofer Bau GmbH" in back_text


class TestCliParsing:
    def test_watch_command_parses(self) -> None:
        from pseudokrat.cli import _build_parser

        args = _build_parser().parse_args(["watch", "--no-ocr", "--folder", "X"])
        assert args.command == "watch"
        assert args.no_ocr is True
        assert str(args.folder) == "X"

    def test_setup_command_parses(self) -> None:
        from pseudokrat.cli import _build_parser

        args = _build_parser().parse_args(["setup"])
        assert args.command == "setup"
