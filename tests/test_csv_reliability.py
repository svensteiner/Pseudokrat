"""Operational reliability regressions for the CSV file pipeline."""

from __future__ import annotations

import csv
import os
from pathlib import Path

import pytest

from pseudokrat.formats.csv_handler import CSVHandler


def _read_rows(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def test_multiline_quoted_cell_preserves_embedded_crlf(tmp_path: Path) -> None:
    source = tmp_path / "multiline.csv"
    output = tmp_path / "multiline.anon.csv"
    expected = [["id", "notes"], ["1", "first line\r\nsecond line"]]
    with source.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle, lineterminator="\r\n").writerows(expected)

    CSVHandler().process(source, output, transform=lambda value: value)

    assert _read_rows(output) == expected


def test_malformed_csv_is_rejected_without_publishing_output(tmp_path: Path) -> None:
    source = tmp_path / "malformed.csv"
    output = tmp_path / "malformed.anon.csv"
    source.write_text('name,value\n"unterminated,secret', encoding="utf-8")
    output.write_bytes(b"known-good-output")

    with pytest.raises(csv.Error):
        CSVHandler().process(source, output, transform=lambda value: value)

    assert output.read_bytes() == b"known-good-output"


def test_failed_atomic_replace_preserves_previous_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.csv"
    output = tmp_path / "source.anon.csv"
    source.write_text("name\nHofer Bau GmbH\n", encoding="utf-8")
    output.write_bytes(b"known-good-output")

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        CSVHandler().process(source, output, transform=str.upper)

    assert output.read_bytes() == b"known-good-output"
    assert list(tmp_path.glob(f".{output.name}.*.tmp")) == []


def test_same_input_and_output_is_rejected_without_modification(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    original = b"name\nHofer Bau GmbH\n"
    source.write_bytes(original)

    with pytest.raises(ValueError, match="nicht identisch"):
        CSVHandler().process(source, source, transform=str.upper)

    assert source.read_bytes() == original


def test_hardlinked_output_is_treated_as_same_file(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    linked_output = tmp_path / "linked.csv"
    original = b"name\nHofer Bau GmbH\n"
    source.write_bytes(original)
    os.link(source, linked_output)

    with pytest.raises(ValueError, match="nicht identisch"):
        CSVHandler().process(source, linked_output, transform=str.upper)

    assert source.read_bytes() == original
    assert linked_output.read_bytes() == original
