"""Plain-Text-Handler (UTF-8)."""

from __future__ import annotations

from pathlib import Path

from pseudokrat.formats.base import (
    FormatProcessResult,
    TextTransform,
    derive_default_output,
)


class TextHandler:
    """Liest und schreibt UTF-8-codierten Klartext."""

    name = "text"
    suffixes: tuple[str, ...] = (".txt", ".text", ".log", ".md")

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
        text = input_path.read_text(encoding="utf-8")
        result = transform(text)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result, encoding="utf-8")
        return FormatProcessResult(
            input_path=input_path,
            output_path=output_path,
            segments_processed=1,
            segments_skipped=0,
        )
