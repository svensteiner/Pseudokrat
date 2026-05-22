"""Tests für TXT- und CSV-Format-Handler."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from pseudokrat.formats import (
    CSVHandler,
    TextHandler,
    UnsupportedFormatError,
    handler_for,
    supported_suffixes,
)


def test_text_handler_roundtrip(tmp_path: Path) -> None:
    inp = tmp_path / "memo.txt"
    out = tmp_path / "memo.anon.txt"
    inp.write_text("Hofer Bau GmbH erhielt 4.300 €.", encoding="utf-8")
    handler = TextHandler()
    result = handler.process(inp, out, transform=lambda t: t.replace("Hofer Bau GmbH", "<X>"))
    assert result.output_path == out
    assert out.read_text(encoding="utf-8") == "<X> erhielt 4.300 €."
    assert result.segments_processed == 1


def test_text_handler_default_output() -> None:
    h = TextHandler()
    p = Path("foo.txt")
    assert h.default_output_path(p) == Path("foo.anon.txt")
    assert h.default_output_path(p, "deanon") == Path("foo.deanon.txt")


def test_text_handler_supports() -> None:
    h = TextHandler()
    assert h.supports(Path("a.txt"))
    assert h.supports(Path("a.MD"))
    assert not h.supports(Path("a.docx"))


def test_csv_handler_cells_consistent(tmp_path: Path) -> None:
    inp = tmp_path / "saldenliste.csv"
    out = tmp_path / "saldenliste.anon.csv"
    inp.write_text(
        "Mandant;Betrag\nHofer Bau GmbH;1000\nHofer Bau GmbH;2000\nMüller AG;5000\n",
        encoding="utf-8",
    )
    seen: dict[str, str] = {}

    def transform(text: str) -> str:
        if text in {"Hofer Bau GmbH", "Müller AG"}:
            return seen.setdefault(text, f"<COMPANY_{len(seen) + 1:03d}>")
        return text

    handler = CSVHandler()
    result = handler.process(inp, out, transform=transform)
    assert result.segments_processed > 0

    rows = list(csv.reader(out.read_text(encoding="utf-8").splitlines(), delimiter=";"))
    assert rows[0] == ["Mandant", "Betrag"]
    assert rows[1][0] == rows[2][0]  # konsistent
    assert rows[1][0] != rows[3][0]  # verschiedene Firmen verschieden


def test_csv_handler_empty_cells_skipped(tmp_path: Path) -> None:
    inp = tmp_path / "sparse.csv"
    out = tmp_path / "sparse.anon.csv"
    inp.write_text("a,,c\n", encoding="utf-8")
    calls: list[str] = []

    def transform(text: str) -> str:
        calls.append(text)
        return text.upper()

    CSVHandler().process(inp, out, transform=transform)
    # leere Zelle wird nicht transformiert
    assert calls == ["a", "c"]
    assert out.read_text(encoding="utf-8").startswith("A,,C")


def test_csv_handler_empty_file(tmp_path: Path) -> None:
    inp = tmp_path / "empty.csv"
    out = tmp_path / "empty.anon.csv"
    inp.write_text("", encoding="utf-8")
    result = CSVHandler().process(inp, out, transform=lambda t: t)
    assert result.segments_processed == 0
    assert out.exists()


def test_handler_for_picks_correct_class(tmp_path: Path) -> None:
    assert isinstance(handler_for(tmp_path / "a.txt"), TextHandler)
    assert isinstance(handler_for(tmp_path / "a.csv"), CSVHandler)
    # DOCX/XLSX werden nur registriert, wenn die Libs verfügbar sind —
    # das ist hier Pflicht.
    from pseudokrat.formats import DocxHandler, XlsxHandler

    assert DocxHandler is not None
    assert XlsxHandler is not None
    assert isinstance(handler_for(tmp_path / "a.docx"), DocxHandler)
    assert isinstance(handler_for(tmp_path / "a.xlsx"), XlsxHandler)


def test_handler_for_unsupported_raises(tmp_path: Path) -> None:
    # ``.pdf`` ist seit Phase 4 registriert — Test mit einer Endung,
    # die wir bewusst nicht unterstützen.
    with pytest.raises(UnsupportedFormatError):
        handler_for(tmp_path / "a.zip")
    with pytest.raises(UnsupportedFormatError):
        handler_for(tmp_path / "no_ext")


def test_supported_suffixes_lists_known() -> None:
    suffixes = supported_suffixes()
    assert ".txt" in suffixes
    assert ".csv" in suffixes
    assert ".docx" in suffixes
    assert ".xlsx" in suffixes
