"""Tests fuer Council-Batch-H: Begriffe.txt (Auto-Anlage + robustes Laden)
und doctor-Checks fuer PDF/OCR/LLM."""

from __future__ import annotations

from pathlib import Path

from pseudokrat import watcher
from pseudokrat.doctor import Status, check_ocr_stack, check_ollama, check_pdf_stack


class TestTerms:
    def test_template_created_when_missing(self, tmp_path: Path) -> None:
        p = tmp_path / "Begriffe.txt"
        assert watcher.ensure_terms_template(p) is True
        assert p.exists()
        # Zweiter Aufruf ueberschreibt NICHT.
        assert watcher.ensure_terms_template(p) is False

    def test_existing_not_overwritten(self, tmp_path: Path) -> None:
        p = tmp_path / "Begriffe.txt"
        p.write_text("Hankook\n", encoding="utf-8")
        assert watcher.ensure_terms_template(p) is False
        assert p.read_text(encoding="utf-8") == "Hankook\n"

    def test_load_skips_comments_and_short(self, tmp_path: Path) -> None:
        p = tmp_path / "Begriffe.txt"
        p.write_text("# Kommentar\nHankook\nX\nM&D\n", encoding="utf-8")
        terms = watcher.load_terms(p)
        assert "Hankook" in terms
        assert "M&D" in terms
        assert "X" not in terms  # Ein-Zeichen-Begriff verworfen
        assert all(not t.startswith("#") for t in terms)

    def test_load_cp1252_fallback(self, tmp_path: Path) -> None:
        p = tmp_path / "Begriffe.txt"
        p.write_bytes("Müller GmbH\n".encode("cp1252"))  # ANSI statt UTF-8
        terms = watcher.load_terms(p)
        assert "Müller GmbH" in terms


class TestDoctorChecks:
    def test_pdf_stack(self) -> None:
        c = check_pdf_stack()
        assert c.name == "PDF-Stack"
        assert c.status in (Status.OK, Status.WARN)

    def test_ocr_stack(self) -> None:
        c = check_ocr_stack()
        assert c.name == "OCR-Stack"
        assert c.status in (Status.OK, Status.WARN)

    def test_ollama(self) -> None:
        c = check_ollama()
        assert c.name == "LLM (Ollama)"
        assert c.status in (Status.OK, Status.WARN)  # optional -> nie FAIL
