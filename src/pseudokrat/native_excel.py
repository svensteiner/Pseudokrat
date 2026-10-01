"""Opt-in Excel calculation on a validated disposable copy, never the original."""

from __future__ import annotations

import hashlib
import json
import math
import os
import posixpath
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from openpyxl.utils.cell import coordinate_to_tuple

from pseudokrat.ki_office import (
    MAX_BYTES,
    ProjectError,
    S,
    read_office,
    transform_formula,
    write_office,
)


def _validated(path: Path) -> tuple[dict[str, Any], dict[str, list[str]]]:
    if path.suffix.lower() != ".xlsx":
        raise ProjectError("Neuberechnung unterstützt nur geprüfte XLSX-Dateien.")
    roots = read_office(path)
    targets = {
        r.get("Id"): posixpath.normpath(posixpath.join("xl", r.get("Target", ""))).lstrip("/")
        for r in roots["xl/_rels/workbook.xml.rels"]
    }
    sheets = list(roots["xl/workbook.xml"].iter(f"{{{S}}}sheet"))
    names = {s.get("name"): s.get("name") for s in sheets}
    if len(names) != len(sheets) or None in names:
        raise ProjectError("Ungültige Tabellenstruktur.")
    for root in roots.values():
        for element in root.iter():
            if element.tag in {
                f"{{{S}}}{tag}" for tag in ("f", "formula", "formula1", "formula2", "definedName")
            }:
                transform_formula(
                    "=" + (element.text or "").lstrip("="), lambda value: value, names
                )
    calculation = roots["xl/workbook.xml"].find(f"{{{S}}}calcPr")
    if calculation is not None:
        if calculation.get("iterate", "0") not in {"0", "false"} or calculation.get(
            "fullPrecision", "1"
        ) not in {"1", "true"}:
            raise ProjectError(
                "Iterative Berechnung oder Genauigkeit wie angezeigt benötigt gesonderte Unterstützung."
            )
        calculation.set("iterate", "0")
    requests: dict[str, list[str]] = {}
    count = 0
    for sheet in sheets:
        name = sheet.get("name")
        target = targets[
            sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        ]
        addresses: set[str] = set()
        requests[name] = []
        for cell in roots[target].iter(f"{{{S}}}c"):
            address = cell.get("r", "")
            if not re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]{0,6}", address):
                raise ProjectError("Ungültige Zelladresse.")
            row, col = coordinate_to_tuple(address)
            if address in addresses or row > 1048576 or col > 16384:
                raise ProjectError("Ungültige oder doppelte Zelladresse.")
            addresses.add(address)
            formula = cell.find(f"{{{S}}}f")
            if formula is not None:
                transform_formula("=" + (formula.text or ""), lambda value: value, names)
                requests[name].append(address)
                count += 1
    if count > 50_000:
        raise ProjectError("Zu viele Formelzellen für die lokale Neuberechnung.")
    return roots, requests


def validate_source(path: Path) -> None:
    """Reject unsupported OOXML and unsafe formulas before starting Excel."""
    try:
        _validated(path)
    except (OSError, KeyError, TypeError, AttributeError) as exc:
        raise ProjectError("Excel-Quelle konnte nicht sicher geprüft werden.") from exc


def recalculate(path: Path, *, timeout: int = 120) -> dict[str, Any]:
    """Return confidential fresh formula values; this does not certify a report.

    Windows and installed Excel are required. The worker assigns its new Excel
    process to a kill-on-close Windows job before opening the disposable copy.
    """
    try:
        if os.name != "nt" or type(timeout) is not int or not 1 <= timeout <= 600:
            raise ProjectError(
                "Lokale Excel-Neuberechnung benötigt Windows und ein gültiges Zeitlimit."
            )
        if path.suffix.lower() != ".xlsx":
            raise ProjectError("Neuberechnung unterstützt nur geprüfte XLSX-Dateien.")
        with path.open("rb") as source:
            snapshot = source.read(MAX_BYTES + 1)
        if len(snapshot) > MAX_BYTES:
            raise ProjectError("Datei überschreitet die unterstützte Größenbegrenzung.")
        before = hashlib.sha256(snapshot).hexdigest()
        with tempfile.TemporaryDirectory(prefix="pseudokrat-calc-") as directory:
            folder = Path(directory)
            # Parse exactly the bytes whose hash will bind the result, rather
            # than independently reopening a potentially changing source.
            snapshot_path = folder / "source.xlsx"
            snapshot_path.write_bytes(snapshot)
            roots, requests = _validated(snapshot_path)
            snapshot_path.unlink()
            (folder / "input.xlsx").write_bytes(write_office(roots))
            (folder / "request.json").write_text(json.dumps(requests), encoding="utf-8")
            shell = (
                Path(os.environ["SYSTEMROOT"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
            )
            process = subprocess.run(
                [
                    str(shell),
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    str(Path(__file__).with_name("native_excel.ps1")),
                    "-Directory",
                    str(folder),
                ],
                capture_output=True,
                timeout=timeout,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,  # type: ignore[attr-defined]  # Windows-only adapter
            )
            if process.returncode != 0:
                raise ProjectError("Excel-Neuberechnung fehlgeschlagen; keine Werte freigegeben.")
            result: dict[str, Any] = json.loads(
                (folder / "result.json").read_text(encoding="utf-8-sig")
            )
        if hashlib.sha256(path.read_bytes()).hexdigest() != before:
            raise ProjectError("Excel-Quelle hat sich während der Berechnung verändert.")
        if result.get("engine") != "Microsoft Excel" or set(result.get("cells", {})) != set(
            requests
        ):
            raise ProjectError("Unvollständiger Berechnungsnachweis.")
        for sheet, addresses in requests.items():
            if set(result["cells"][sheet]) != set(addresses):
                raise ProjectError("Unvollständiger Berechnungsnachweis.")
            for cell in result["cells"][sheet].values():
                if not isinstance(cell, dict) or set(cell) != {"value"}:
                    raise ProjectError("Ungültiges Berechnungsergebnis.")
                value = cell["value"]
                if type(value) not in {str, int, float, bool} or value == "":
                    raise ProjectError("Ungültiges Berechnungsergebnis.")
                if type(value) is float and not math.isfinite(value):
                    raise ProjectError("Ungültiges Berechnungsergebnis.")
        result["source_sha256"] = before
        return result
    except ProjectError:
        raise
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        subprocess.SubprocessError,
    ) as exc:
        raise ProjectError("Lokale Excel-Neuberechnung konnte nicht abgeschlossen werden.") from exc
