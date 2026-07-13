"""HTML-Handler — anonymisiert HTML als Text.

Der gesamte HTML-Quelltext laeuft durch die Anonymisierungs-Pipeline. Damit
werden Firmenname/E-Mails/URLs nicht nur im Fliesstext erfasst, sondern auch
im **Seitentitel** (``<title>``) und in **Attributen** (``href``, ``src``,
``content`` …) — typische Leck-Stellen bei Viewer-/Report-Exporten
(z. B. ``name@firma.example.com`` in einer Viewer-URL).

Gedacht als Texteingabe fuer die Cloud-KI: Platzhalter haben die Form
``<KAT_nnn>``; im Quelltext ist der Originalname damit weg und ueber das
Profil-Mapping reversibel.
"""

from __future__ import annotations

import re
from pathlib import Path

from pseudokrat.formats.base import (
    FormatProcessResult,
    TextTransform,
    derive_default_output,
)

#: Eingebettete data:-URIs (v. a. base64-Bilder) — Nutzlast wird entfernt.
_DATA_URI_RE = re.compile(r"data:[^\s;,'\"]+;base64,[A-Za-z0-9+/=]+")


class HtmlHandler:
    """Liest HTML als Text, anonymisiert Titel/Attribute/Inhalt, schreibt UTF-8."""

    name = "html"
    suffixes: tuple[str, ...] = (".html", ".htm")

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
        try:
            text = input_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Exotische/alte HTML-Exporte (latin-1 o. ae.) nicht scheitern lassen.
            text = input_path.read_text(encoding="utf-8", errors="replace")
        # Eingebettete Bilder (data:-URIs) entfernen — koennen Logos/Scans mit
        # Mandantendaten sein, die die Text-Anonymisierung nicht sieht.
        text = _DATA_URI_RE.sub("data:removed", text)
        result = transform(text)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result, encoding="utf-8")
        return FormatProcessResult(
            input_path=input_path,
            output_path=output_path,
            segments_processed=1,
            segments_skipped=0,
        )
