"""Vorschau-Editor mit farbigem PII-Highlighting (§9 Megaprompt).

Stellt :class:`PIIPreviewWidget` bereit, einen ``QTextEdit``-basierten,
read-only Editor, der einen Klartext zusammen mit den vom
:class:`pseudokrat.gui.controller.GuiController.preview` gelieferten
:class:`PreviewSpan`-Einträgen anzeigt. Spans werden pro Kategorie mit einer
eigenen Hintergrundfarbe hinterlegt; ein Tooltip pro Span zeigt Kategorie
und Confidence-Score.

Das Modul kennt die Pseudokrat-Public-API ``PreviewSpan`` und Qt — sonst
nichts. Tests laden es headless via ``QT_QPA_PLATFORM=offscreen``.
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit, QWidget

from pseudokrat.gui.controller import PreviewSpan

# Hex-Farb-Tabelle pro PII-Kategorie. Pastelltöne, damit der unterliegende
# Text bei dunkler Schrift gut lesbar bleibt. Unbekannte Kategorien fallen
# auf den letzten Eintrag (DEFAULT) zurück.
CATEGORY_COLORS: dict[str, str] = {
    "PERSON": "#FFD6A5",
    "COMPANY": "#FFADAD",
    "IBAN": "#A0C4FF",
    "BIC": "#A0E7E5",
    "UID": "#BDB2FF",
    "TAX_ID": "#CAFFBF",
    "SVNR": "#FFC6FF",
    "AHV": "#FDFFB6",
    "EMAIL": "#9BF6FF",
    "PHONE": "#FDFFB6",
    "URL": "#D0BFFF",
    "SECRET": "#FFB4A2",
    "ADDRESS": "#B5EAD7",
    "DATE": "#E2F0CB",
    "ACCOUNT": "#A0C4FF",
    "MANDANT_NR": "#FFC8DD",
}
DEFAULT_COLOR = "#E0E0E0"


def color_for_category(category: str) -> QColor:
    """Liefert die Hintergrundfarbe für eine PII-Kategorie."""
    return QColor(CATEGORY_COLORS.get(category, DEFAULT_COLOR))


class PIIPreviewWidget(QTextEdit):
    """Read-only ``QTextEdit``, der Klartext mit PII-Highlight anzeigt."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setObjectName("preview_edit")
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(mono)
        self.setPlaceholderText(
            "Vorschau erscheint hier nach Klick auf 'Vorschau'."
        )

    def set_preview(self, text: str, spans: Iterable[PreviewSpan]) -> None:
        """Befüllt den Editor mit ``text`` und färbt die übergebenen Spans.

        Überlappungen werden vom Controller bereits aufgelöst (per
        :func:`pseudokrat.anonymizer._resolve_overlaps`), wir vertrauen
        darauf, dass die Eingangs-Spans disjunkt sind.
        """
        self.clear()
        self.setPlainText(text)

        cursor = self.textCursor()
        for span in sorted(spans, key=lambda s: s.start):
            if span.start < 0 or span.end > len(text) or span.start >= span.end:
                continue
            cursor.setPosition(span.start)
            cursor.setPosition(span.end, QTextCursor.MoveMode.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setBackground(color_for_category(span.category))
            fmt.setToolTip(self._tooltip_for(span))
            cursor.setCharFormat(fmt)

    @staticmethod
    def _tooltip_for(span: PreviewSpan) -> str:
        return f"{span.category} · Confidence {span.score:.0%}"

    def clear_preview(self) -> None:
        """Leert die Vorschau und entfernt alle Highlights."""
        self.clear()
