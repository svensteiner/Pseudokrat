"""Tests für den PDF-Format-Handler (Phase 4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pseudokrat.formats.pdf_handler import PdfHandler


def _make_pdf(path: Path, pages: list[str]) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen.canvas import Canvas

    canvas = Canvas(str(path), pagesize=A4)
    width, height = A4
    for idx, text in enumerate(pages):
        if idx > 0:
            canvas.showPage()
        canvas.setFont("Helvetica", 11)
        y = height - 72
        for line in text.splitlines() or [""]:
            canvas.drawString(72, y, line)
            y -= 14
    canvas.save()


def _extract_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def test_pdf_handler_supports_and_default_output() -> None:
    h = PdfHandler()
    assert h.supports(Path("foo.pdf"))
    assert h.supports(Path("FOO.PDF"))
    assert not h.supports(Path("foo.docx"))
    assert h.default_output_path(Path("/tmp/foo.pdf")) == Path("/tmp/foo.anon.pdf")


def test_pdf_handler_anonymizes_text_layer(tmp_path: Path) -> None:
    inp = tmp_path / "in.pdf"
    out = tmp_path / "out.pdf"
    _make_pdf(
        inp,
        pages=[
            "Schreiben an Hofer Bau GmbH.",
            "IBAN AT611904300234573201 — Frist 30 Tage.",
        ],
    )

    def transform(text: str) -> str:
        return text.replace("Hofer Bau GmbH", "<COMPANY_001>").replace(
            "AT611904300234573201", "<IBAN_001>"
        )

    result = PdfHandler().process(inp, out, transform=transform)
    assert result.segments_processed == 2
    assert out.exists()

    extracted = _extract_text(out)
    assert "<COMPANY_001>" in extracted
    assert "<IBAN_001>" in extracted
    assert "Hofer Bau GmbH" not in extracted
    assert "AT611904300234573201" not in extracted


def test_pdf_handler_skips_empty_pages(tmp_path: Path) -> None:
    inp = tmp_path / "in.pdf"
    out = tmp_path / "out.pdf"
    _make_pdf(inp, pages=["Mandant Müller GmbH.", "", "Schluss."])

    captured: list[str] = []

    def transform(text: str) -> str:
        captured.append(text)
        return text.replace("Müller GmbH", "<COMPANY_001>")

    result = PdfHandler().process(inp, out, transform=transform)
    assert result.segments_processed == 2
    assert result.segments_skipped == 1
    # Leere Seite wurde nicht durch die Transform-Funktion geschickt.
    assert all(line.strip() for line in captured)


def test_pdf_handler_via_handler_for(tmp_path: Path) -> None:
    from pseudokrat.formats import handler_for

    inp = tmp_path / "x.pdf"
    out = tmp_path / "x.anon.pdf"
    _make_pdf(inp, pages=["Mandant Hofer Bau GmbH."])

    handler = handler_for(inp)
    result = handler.process(
        inp,
        out,
        transform=lambda t: t.replace("Hofer Bau GmbH", "<COMPANY_001>"),
    )
    assert result.segments_processed == 1
    assert "<COMPANY_001>" in _extract_text(out)


def test_pdf_handler_long_line_wrapping(tmp_path: Path) -> None:
    """Lange Zeilen (z. B. lange Anonymisat-Tokens) müssen sauber umbrechen."""
    inp = tmp_path / "long.pdf"
    out = tmp_path / "long.anon.pdf"
    body = "Mandant Hofer Bau GmbH " * 50
    _make_pdf(inp, pages=[body])

    result = PdfHandler().process(
        inp,
        out,
        transform=lambda t: t.replace("Hofer Bau GmbH", "<COMPANY_001>"),
    )
    assert result.segments_processed == 1
    extracted = _extract_text(out)
    assert "<COMPANY_001>" in extracted


def test_pdf_handler_empty_input_produces_valid_pdf(tmp_path: Path) -> None:
    """Eine PDF ohne extrahierbaren Text erzeugt eine gültige (leere) PDF."""
    inp = tmp_path / "blank.pdf"
    out = tmp_path / "blank.anon.pdf"
    _make_pdf(inp, pages=[""])

    result = PdfHandler().process(inp, out, transform=lambda t: t)
    assert out.exists()
    # Eine vollständig leere Eingabe wird als "skipped" gezählt.
    assert result.segments_processed == 0


def test_pdf_listed_in_supported_suffixes() -> None:
    from pseudokrat.formats import supported_suffixes

    assert ".pdf" in supported_suffixes()


def test_pdf_handler_missing_input_raises(tmp_path: Path) -> None:
    out = tmp_path / "out.pdf"
    with pytest.raises(FileNotFoundError):
        PdfHandler().process(tmp_path / "missing.pdf", out, transform=lambda t: t)
