"""Tests fuer Council-Batch-C (UX/Robustheit): Trefferbericht, Fehler-Text,
Kollisions-Umbenennung, Marker-Skip."""

from __future__ import annotations

from pathlib import Path

from pseudokrat import watcher
from pseudokrat.formats import UnsupportedFormatError


class TestFormatCounts:
    def test_sorted_and_labelled(self) -> None:
        s = watcher._format_counts({"IBAN": 3, "COMPANY": 2, "EMAIL": 1})
        assert s == "3x IBAN, 2x Firma, 1x E-Mail"

    def test_empty(self) -> None:
        assert watcher._format_counts({}) == "0 Treffer"


class TestFriendlyError:
    def test_residual(self) -> None:
        msg = watcher._friendly_error(watcher.ResidualPIIError(2))
        assert "nicht sicher geschwaerzt" in msg or "NICHT" in msg

    def test_permission(self) -> None:
        assert "geoeffnet" in watcher._friendly_error(PermissionError("busy"))

    def test_unsupported(self) -> None:
        msg = watcher._friendly_error(UnsupportedFormatError(".xyz"))
        assert "Dateiformat" in msg and "unterstuetzt" in msg


class TestUniqueTarget:
    def test_no_collision_returns_same(self, tmp_path: Path) -> None:
        t = tmp_path / "a.pdf"
        assert watcher._unique_target(t) == t

    def test_collision_gets_suffix(self, tmp_path: Path) -> None:
        t = tmp_path / "a.pdf"
        t.write_text("x", encoding="utf-8")
        assert watcher._unique_target(t) == tmp_path / "a (2).pdf"


class TestScanSkipsMarkers:
    def test_underscore_files_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "echt.txt").write_text("x", encoding="utf-8")
        (tmp_path / "_Hinweis.txt").write_text("x", encoding="utf-8")
        names = {p.name for p in watcher._scan(tmp_path)}
        assert names == {"echt.txt"}
