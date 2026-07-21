"""CSV/TSV-Handler.

Strategie: jede Zelle einzeln anonymisieren. Damit identische Werte in einer
Spalte denselben Platzhalter erhalten (der Mapping-Store ist konsistent).
Trennzeichen wird automatisch via ``csv.Sniffer`` erkannt, mit Fallback ``,``.
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
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
        # ``Path.read_text`` performs universal-newline translation.  That
        # silently changes CR/LF characters inside quoted multiline cells, so
        # open with ``newline=""`` and let the csv module handle newlines.
        with input_path.open("r", encoding="utf-8-sig", newline="") as fh:
            raw = fh.read()
        dialect = self._sniff_dialect(raw[:4096])

        cells_processed = 0
        rows_out: list[list[str]] = []
        # ``splitlines()`` drops record separators, including embedded
        # newlines in quoted fields.  StringIO preserves them.  Strict mode is
        # deliberate: malformed CSV must fail before any output is published
        # instead of being silently reinterpreted and potentially corrupted.
        reader = csv.reader(io.StringIO(raw, newline=""), dialect=dialect, strict=True)
        for row in reader:
            new_row = []
            for cell in row:
                if cell:
                    new_row.append(transform(cell))
                    cells_processed += 1
                else:
                    new_row.append(cell)
            rows_out.append(new_row)

        if _same_file(input_path, output_path):
            raise ValueError("Ein- und Ausgabedatei dürfen nicht identisch sein.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
        )
        os.close(fd)
        temporary_path = Path(temporary_name)
        try:
            with temporary_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh, dialect=dialect)
                writer.writerows(rows_out)
                fh.flush()
                os.fsync(fh.fileno())
            # Atomic on one filesystem: a previous known-good result stays in
            # place until the complete new CSV has been written successfully.
            temporary_path.replace(output_path)
        finally:
            temporary_path.unlink(missing_ok=True)

        return FormatProcessResult(
            input_path=input_path,
            output_path=output_path,
            segments_processed=cells_processed,
            segments_skipped=0,
        )


def _same_file(input_path: Path, output_path: Path) -> bool:
    """Return whether both paths address the same file, including links.

    ``Path.samefile`` needs both paths to exist.  The normalized fallback also
    catches an explicit output path that does not exist yet but resolves to the
    input spelling (including Windows case folding).
    """
    try:
        if input_path.samefile(output_path):
            return True
    except (FileNotFoundError, OSError):
        pass
    input_resolved = os.path.normcase(str(input_path.resolve(strict=False)))
    output_resolved = os.path.normcase(str(output_path.resolve(strict=False)))
    return input_resolved == output_resolved
