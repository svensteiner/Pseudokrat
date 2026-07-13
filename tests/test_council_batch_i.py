"""Tests fuer Council-Batch-I (#23): Datei-Stabilitaets-Check vor Verarbeitung."""

from __future__ import annotations

from pathlib import Path

from pseudokrat import watcher


def test_stable_file_is_stable(tmp_path: Path) -> None:
    p = tmp_path / "fertig.txt"
    p.write_text("hallo", encoding="utf-8")
    assert watcher._file_is_stable(p) is True


def test_missing_file_is_not_stable(tmp_path: Path) -> None:
    assert watcher._file_is_stable(tmp_path / "gibtsnicht.txt") is False
