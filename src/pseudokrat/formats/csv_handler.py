"""CSV/TSV-Handler.

Strategie: jede Zelle einzeln anonymisieren. Damit identische Werte in einer
Spalte denselben Platzhalter erhalten (der Mapping-Store ist konsistent).
Trennzeichen wird automatisch via ``csv.Sniffer`` erkannt, mit Fallback ``,``.
"""

from __future__ import annotations

import csv
from pathlib import Path

from pseudokrat.formats.base import (
    FormatProcessResult,
    TextTransform,
    derive_default_output,
)


class CSVHandler:
    name = "csv"
    suffixes: tuple[str, ...] = (".csv", ".tsv")

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in self.suffixes

    def default_output_path(self, input_path: Path, suffix: str = "anon") -> Path:
        return derive_default_output(input_path, suffix=suffix)

    def _sniff_dialect(self, sample: str) -> type[csv.Dialect] | csv.Dialect:
        if not sample.strip():
            return csv.excel
        try:
            return csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            return csv.excel

    def process(
        self,
        input_path: Path,
        output_path: Path,
        transform: TextTransform,
    ) -> FormatProcessResult:
        raw = input_path.read_text(encoding="utf-8-sig")
        dialect = self._sniff_dialect(raw[:4096])

        cells_processed = 0
        rows_out: list[list[str]] = []
        reader = csv.reader(raw.splitlines(), dialect=dialect)
        for row in reader:
            new_row = []
            for cell in row:
                if cell:
                    new_row.append(transform(cell))
                    cells_processed += 1
                else:
                    new_row.append(cell)
            rows_out.append(new_row)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, dialect=dialect)
            writer.writerows(rows_out)

        return FormatProcessResult(
            input_path=input_path,
            output_path=output_path,
            segments_processed=cells_processed,
            segments_skipped=0,
        )
