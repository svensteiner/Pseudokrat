"""Real Excel tests are explicit opt-in; input gates run without Excel."""

import json
import os
import subprocess
from pathlib import Path

import pytest
from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule

from pseudokrat import native_excel
from pseudokrat.ki_office import ProjectError
from pseudokrat.native_excel import recalculate, validate_source


def test_unsafe_formula_never_reaches_excel(tmp_path):
    source = tmp_path / "input.xlsx"
    book = Workbook()
    book.active["A1"] = '=WEBSERVICE("https://example.invalid")'
    book.save(source)
    with pytest.raises(ProjectError):
        validate_source(source)


def test_unsafe_conditional_formula_never_reaches_excel(tmp_path):
    source = tmp_path / "conditional.xlsx"
    book = Workbook()
    book.active["A1"] = 1
    book.active.conditional_formatting.add("A1", FormulaRule(formula=['WEBSERVICE("https://example.invalid")']))
    book.save(source)
    with pytest.raises(ProjectError):
        validate_source(source)


@pytest.mark.parametrize("setting,value", [("iterate", True), ("fullPrecision", False)])
def test_calculation_semantics_are_not_silently_changed(tmp_path, setting, value):
    source = tmp_path / "special.xlsx"
    book = Workbook()
    book.active["A1"] = "=1+2"
    setattr(book.calculation, setting, value)
    book.save(source)
    with pytest.raises(ProjectError):
        validate_source(source)


@pytest.mark.skipif(os.environ.get("PSEUDOKRAT_TEST_EXCEL") != "1", reason="Requires explicit local Excel opt-in")
def test_real_excel_rebuild_returns_fresh_values_without_modifying_original(tmp_path):
    source = tmp_path / "input.xlsx"
    book = Workbook()
    book.active.title = "Daten"
    book.active["A1"] = 12.35
    book.active["A2"] = -2.15
    book.active["B1"] = "=SUM(A1:A2)"
    book.active["B2"] = "=ROUND(-0.125,2)"
    book.active["B3"] = '=IF(A1>0,"positiv","negativ")'
    hidden = book.create_sheet("Versteckt")
    hidden.sheet_state = "veryHidden"
    hidden["A1"] = "=Daten!A1*2"
    book.save(source)
    original = source.read_bytes()
    result = recalculate(source)
    assert result["engine"] == "Microsoft Excel"
    assert result["cells"]["Daten"]["B1"]["value"] == pytest.approx(10.2)
    assert result["cells"]["Daten"]["B2"]["value"] == pytest.approx(-0.13)
    assert result["cells"]["Daten"]["B3"]["value"] == "positiv"
    assert result["cells"]["Versteckt"]["A1"]["value"] == pytest.approx(24.7)
    assert source.read_bytes() == original


@pytest.mark.skipif(os.environ.get("PSEUDOKRAT_TEST_EXCEL") != "1", reason="Requires explicit local Excel opt-in")
def test_real_excel_error_cell_stops_result(tmp_path):
    source = tmp_path / "error.xlsx"
    book = Workbook()
    book.active["A1"] = "=1/0"
    book.save(source)
    with pytest.raises(ProjectError):
        recalculate(source)


@pytest.mark.skipif(os.environ.get("PSEUDOKRAT_TEST_EXCEL") != "1", reason="Requires explicit local Excel opt-in")
@pytest.mark.parametrize("formula", ["=A1+1", "=B1+1"])
def test_real_excel_circular_reference_stops_result(tmp_path, formula):
    source = tmp_path / "circular.xlsx"
    book = Workbook()
    book.active["A1"] = formula
    book.active["B1"] = "=A1+1"
    book.save(source)
    with pytest.raises(ProjectError):
        recalculate(source)


@pytest.mark.skipif(os.environ.get("PSEUDOKRAT_TEST_EXCEL") != "1", reason="Requires explicit local Excel opt-in")
def test_timeout_kills_owned_excel_and_removes_working_copy(tmp_path, monkeypatch):
    source = tmp_path / "timeout.xlsx"
    book = Workbook()
    book.active["A1"] = "=1+2"
    book.save(source)
    original = source.read_bytes()
    worker = Path(native_excel.__file__).with_suffix(".ps1").read_text()
    # Instrument a test-only worker after its owned Excel process opened the copy.
    marker = tmp_path / "owned.json"
    literal = str(marker).replace("'", "''")
    worker = worker.replace(
        " $excel.CalculateFullRebuild()",
        f" @{{ pid = $excelPid; directory = $Directory }} | ConvertTo-Json | Set-Content -LiteralPath '{literal}'\n Start-Sleep -Seconds 60\n $excel.CalculateFullRebuild()",
    )
    (tmp_path / "native_excel.ps1").write_text(worker)
    monkeypatch.setattr(native_excel, "__file__", str(tmp_path / "native_excel.py"))
    with pytest.raises(ProjectError):
        recalculate(source, timeout=15)
    ownership = json.loads(marker.read_text())
    probe = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         f"if (Get-Process -Id {int(ownership['pid'])} -ErrorAction SilentlyContinue) {{ exit 1 }}"],
        capture_output=True, timeout=10,
    )
    assert probe.returncode == 0
    assert not Path(ownership["directory"]).exists()
    assert source.read_bytes() == original


@pytest.mark.skipif(os.name != "nt", reason="Windows adapter")
@pytest.mark.parametrize("invalid", [None, [], {}, "", float("nan"), float("inf")])
def test_invalid_worker_values_are_never_released(tmp_path, monkeypatch, invalid):
    source = tmp_path / "input.xlsx"
    book = Workbook()
    book.active["A1"] = "=1+2"
    book.save(source)

    def worker(command, **kwargs):
        folder = Path(command[-1])
        (folder / "result.json").write_text(json.dumps({
            "engine": "Microsoft Excel", "cells": {"Sheet": {"A1": {"value": invalid}}},
        }))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(native_excel.subprocess, "run", worker)
    with pytest.raises(ProjectError):
        recalculate(source)


@pytest.mark.skipif(os.name != "nt", reason="Windows adapter")
def test_source_change_discards_worker_result(tmp_path, monkeypatch):
    source = tmp_path / "input.xlsx"
    book = Workbook()
    book.active["A1"] = "=1+2"
    book.save(source)

    def worker(command, **kwargs):
        (Path(command[-1]) / "result.json").write_text(json.dumps({
            "engine": "Microsoft Excel", "cells": {"Sheet": {"A1": {"value": 3}}},
        }))
        book.active["A1"] = "=10+20"
        book.save(source)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(native_excel.subprocess, "run", worker)
    with pytest.raises(ProjectError):
        recalculate(source)
