"""PDF-Handler (pypdf zum Lesen, reportlab zum Schreiben).

Phase-4-Pipeline: Text-Layer pro Seite via ``pypdf`` extrahieren, an die
Transform-Funktion übergeben, und das anonymisierte Ergebnis als **neue** PDF
schreiben. Original-Datei bleibt unangetastet.

Trade-off (siehe DECISIONS D-020): Wir schreiben einen reinen Text-PDF —
Layout, Bilder, Tabellen-Geometrie, Schriftarten und eingebettete Objekte
gehen verloren. Das ist bewusst: PDFs werden zur Anonymisierung verarbeitet
und anschließend mit einer Cloud-KI geteilt; layouttreue Redaktion ist Sache
einer späteren Phase.
"""

from __future__ import annotations

from pathlib import Path

from pseudokrat.formats.base import (
    FormatProcessResult,
    TextTransform,
    derive_default_output,
)

# Margins und Schrift bewusst klein, um lange Zeilen zu vermeiden und mehr
# Originalinhalt pro Seite zu erhalten.
_MARGIN_PT = 36.0  # 0.5 inch
_FONT_NAME = "Helvetica"
_FONT_SIZE = 10.0
_LINE_LEADING = 12.0


class PdfHandler:
    """Liest die Text-Schicht aus einer PDF und schreibt eine neu erzeugte
    Text-PDF mit dem anonymisierten Inhalt."""

    name = "pdf"
    suffixes: tuple[str, ...] = (".pdf",)

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in self.suffixes

    def default_output_path(self, input_path: Path, suffix: str = "anon") -> Path:
        return derive_default_output(input_path, suffix=suffix)

    def process(
        self,
        input_path: Path,
        output_path: Path,
        transform: TextTransform,
    ) -> FormatProcessResult:
        from pypdf import PdfReader
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen.canvas import Canvas

        reader = PdfReader(str(input_path))
        page_width, page_height = A4

        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas = Canvas(str(output_path), pagesize=A4)
        canvas.setFont(_FONT_NAME, _FONT_SIZE)

        processed = 0
        skipped = 0
        notes: list[str] = []

        for page_no, page in enumerate(reader.pages, start=1):
            try:
                original = page.extract_text() or ""
            except Exception as exc:  # pragma: no cover - defensiv
                notes.append(f"Seite {page_no}: Text-Extraktion fehlgeschlagen ({exc})")
                original = ""
            if not original.strip():
                skipped += 1
                canvas.showPage()
                canvas.setFont(_FONT_NAME, _FONT_SIZE)
                continue

            transformed = transform(original)
            processed += 1
            _render_page(canvas, transformed, page_width, page_height)
            canvas.showPage()
            canvas.setFont(_FONT_NAME, _FONT_SIZE)

        if processed == 0 and skipped == 0:
            # Eine leere PDF wäre ungültig; mindestens eine Seite muss erzeugt
            # werden.
            canvas.drawString(_MARGIN_PT, page_height - _MARGIN_PT - _FONT_SIZE, "")
            canvas.showPage()
            notes.append("Eingabe enthielt keinen extrahierbaren Text — leere Seite erzeugt.")

        canvas.save()

        return FormatProcessResult(
            input_path=input_path,
            output_path=output_path,
            segments_processed=processed,
            segments_skipped=skipped,
            notes=tuple(notes),
        )


def _render_page(canvas: object, text: str, page_width: float, page_height: float) -> None:
    """Render ``text`` auf eine A4-Seite, einfache Word-Wrap-Logik."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    max_width = page_width - 2 * _MARGIN_PT
    y = page_height - _MARGIN_PT - _FONT_SIZE
    bottom = _MARGIN_PT

    for raw_line in text.splitlines():
        if not raw_line.strip():
            y -= _LINE_LEADING
            if y < bottom:
                canvas.showPage()  # type: ignore[attr-defined]
                canvas.setFont(_FONT_NAME, _FONT_SIZE)  # type: ignore[attr-defined]
                y = page_height - _MARGIN_PT - _FONT_SIZE
            continue
        for wrapped in _wrap_line(raw_line, max_width, stringWidth):
            if y < bottom:
                canvas.showPage()  # type: ignore[attr-defined]
                canvas.setFont(_FONT_NAME, _FONT_SIZE)  # type: ignore[attr-defined]
                y = page_height - _MARGIN_PT - _FONT_SIZE
            canvas.drawString(_MARGIN_PT, y, wrapped)  # type: ignore[attr-defined]
            y -= _LINE_LEADING


def _wrap_line(
    line: str,
    max_width: float,
    width_of: object,
) -> list[str]:
    """Greedy Word-Wrap, der überlange Tokens unverändert lässt (z. B.
    lange Platzhalter oder IBANs werden nicht hart umgebrochen)."""
    words = line.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if width_of(candidate, _FONT_NAME, _FONT_SIZE) <= max_width:  # type: ignore[operator]
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]
