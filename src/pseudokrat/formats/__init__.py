"""Format-aware Dateiverarbeitungs-Pipelines.

Jeder Handler kann eine Datei in einen Strom von "Textsegmenten" zerlegen,
dem Anonymizer übergeben und das Ergebnis wieder formatgetreu zurückschreiben.
TXT/CSV behandeln den ganzen Inhalt als einen Stream. DOCX/XLSX iterieren über
Absätze bzw. Zellen, sodass Strukturen und Formeln erhalten bleiben.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pseudokrat.formats.base import (
    FormatHandler,
    FormatProcessResult,
    UnsafeArchiveError,
    UnsupportedFormatError,
    validate_office_archive,
)
from pseudokrat.formats.csv_handler import CSVHandler
from pseudokrat.formats.html_handler import HtmlHandler
from pseudokrat.formats.txt_handler import TextHandler

# Optionale Handler — importiere defensiv, damit fehlende Extras nicht
# das Hauptpaket brechen. python-docx und openpyxl sind aber Standard-Deps
# in Phase 2 ff., daher kommen sie in der Praxis immer mit.
try:  # pragma: no cover - rein opportunistischer Import
    from pseudokrat.formats.docx_handler import DocxHandler
except ImportError:  # pragma: no cover - Fallback bei fehlendem python-docx
    DocxHandler = None  # type: ignore[assignment,misc]

try:  # pragma: no cover - rein opportunistischer Import
    from pseudokrat.formats.xlsx_handler import XlsxHandler
except ImportError:  # pragma: no cover - Fallback bei fehlendem openpyxl
    XlsxHandler = None  # type: ignore[assignment,misc]

try:  # pragma: no cover - PDF-Extra
    from pseudokrat.formats.pdf_handler import PdfHandler
except ImportError:  # pragma: no cover - pypdf/reportlab nicht installiert
    PdfHandler = None  # type: ignore[assignment,misc]


_HANDLERS_BY_SUFFIX: dict[str, Callable[[], FormatHandler]] = {
    ".txt": TextHandler,
    ".text": TextHandler,
    ".log": TextHandler,
    ".md": TextHandler,
    ".csv": CSVHandler,
    ".tsv": CSVHandler,
    ".html": HtmlHandler,
    ".htm": HtmlHandler,
}

if DocxHandler is not None:  # pragma: no branch
    _HANDLERS_BY_SUFFIX[".docx"] = DocxHandler

if XlsxHandler is not None:  # pragma: no branch
    _HANDLERS_BY_SUFFIX[".xlsx"] = XlsxHandler

if PdfHandler is not None:  # pragma: no branch
    _HANDLERS_BY_SUFFIX[".pdf"] = PdfHandler


def handler_for(path: Path) -> FormatHandler:
    """Wähle den passenden Handler anhand der Dateiendung."""
    suffix = path.suffix.lower()
    factory = _HANDLERS_BY_SUFFIX.get(suffix)
    if factory is None:
        raise UnsupportedFormatError(
            f"Kein Handler für {suffix or '(ohne Endung)'} — unterstützt: "
            f"{sorted(_HANDLERS_BY_SUFFIX)}"
        )
    return factory()


def supported_suffixes() -> list[str]:
    return sorted(_HANDLERS_BY_SUFFIX)


__all__ = [
    "CSVHandler",
    "DocxHandler",
    "FormatHandler",
    "FormatProcessResult",
    "HtmlHandler",
    "PdfHandler",
    "TextHandler",
    "UnsafeArchiveError",
    "UnsupportedFormatError",
    "XlsxHandler",
    "handler_for",
    "supported_suffixes",
    "validate_office_archive",
]
