"""Validated, deterministic Excel facts for a locally reviewed Word mapping."""

from __future__ import annotations

import hashlib
import posixpath
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any

from openpyxl.styles.numbers import BUILTIN_FORMATS, is_date_format
from openpyxl.utils.cell import get_column_letter, range_boundaries

from pseudokrat.ki_office import (
    ProjectError,
    S,
    cell_text,
    read_local_template,
    read_office,
    shared_text,
)
from pseudokrat.native_excel import recalculate
from pseudokrat.native_libreoffice import recalculate as recalculate_with_libreoffice


def _require(condition: bool) -> None:
    if not condition:
        raise ProjectError("Berichtszuordnung unvollständig, verändert oder nicht unterstützt. Lokal prüfen.")


def _addresses(reference: str) -> list[str]:
    _require(isinstance(reference, str) and re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]{0,6}(?::[A-Z]{1,3}[1-9][0-9]{0,6})?", reference) is not None)
    c1, r1, c2, r2 = range_boundaries(reference)
    _require(1 <= c1 <= c2 <= 16384 and 1 <= r1 <= r2 <= 1048576)
    _require((c2 - c1 + 1) * (r2 - r1 + 1) <= 100_000)
    return [f"{get_column_letter(c)}{r}" for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)]


def resolve_mapping(excel: Path, template: Path, spec: dict[str, Any], *, recalculate_excel: bool = False, recalculate_libreoffice: bool = False) -> dict[str, Any]:
    """Resolve reviewed fields, optionally rebuilding formulas in local Excel.

    Results contain original facts and source references and must stay local.
    A reviewed mapping flag is a human assertion, not a production certificate.
    """
    try:
        with localcontext() as context:
            context.prec = 320
            _require(type(recalculate_excel) is bool and type(recalculate_libreoffice) is bool)
            _require(not (recalculate_excel and recalculate_libreoffice))
            return _resolve(excel, template, spec, recalculate_excel, recalculate_libreoffice)
    except ProjectError:
        raise
    except (OSError, KeyError, ValueError, TypeError, AttributeError, InvalidOperation, OverflowError) as exc:
        raise ProjectError("Berichtsquellen oder Zuordnung konnten nicht sicher ausgewertet werden.") from exc


def _resolve(excel: Path, template: Path, spec: dict[str, Any], recalculate_excel: bool, recalculate_libreoffice: bool) -> dict[str, Any]:
    _require(excel.suffix.lower() == ".xlsx" and template.suffix.lower() == ".docx")
    _require(set(spec) == {"version", "reviewed", "template_sha256", "headers", "fields"})
    _require(type(spec["version"]) is int and spec["version"] == 1 and spec["reviewed"] is True)
    _require(spec["template_sha256"] == hashlib.sha256(template.read_bytes()).hexdigest())
    _require(isinstance(spec["headers"], dict) and isinstance(spec["fields"], dict) and 1 <= len(spec["fields"]) <= 10_000)
    source_hash = hashlib.sha256(excel.read_bytes()).hexdigest()
    roots = read_office(excel)
    read_local_template(template)
    strings = shared_text(roots)
    rels = roots["xl/_rels/workbook.xml.rels"]
    targets = {r.get("Id"): posixpath.normpath(posixpath.join("xl", r.get("Target", ""))).lstrip("/") for r in rels}
    sheets = {}
    for sheet in roots["xl/workbook.xml"].iter(f"{{{S}}}sheet"):
        target = targets[sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")]
        name = sheet.get("name")
        _require(name not in sheets)
        cells = list(roots[target].iter(f"{{{S}}}c"))
        sheets[name] = {c.get("r"): c for c in cells}
        _require(len(sheets[name]) == len(cells))
    styles = roots.get("xl/styles.xml")
    formats = dict(BUILTIN_FORMATS)
    xfs = []
    if styles is not None:
        formats.update({int(e.get("numFmtId")): e.get("formatCode", "") for e in styles.iter(f"{{{S}}}numFmt")})
        cell_xfs = styles.find(f"{{{S}}}cellXfs")
        xfs = list(cell_xfs) if cell_xfs is not None else []
    for sheet, headers in spec["headers"].items():
        _require(sheet in sheets and isinstance(headers, dict) and bool(headers))
        for address, expected in headers.items():
            _require(len(_addresses(address)) == 1 and isinstance(expected, str))
            cell = sheets[sheet].get(address)
            _require(cell is not None and cell.find(f"{{{S}}}f") is None)
            _require(cell_text(cell, strings) == expected)
    result = {}
    calculation = None
    referenced_cells = 0
    for name, field in spec["fields"].items():
        _require(isinstance(name, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,99}", name) is not None)
        _require(isinstance(field, dict) and set(field) <= {"sheet", "range", "operation", "format", "decimals"})
        sheet, reference, operation, formatting = (field[k] for k in ("sheet", "range", "operation", "format"))
        _require(sheet in spec["headers"] and operation in {"cell", "sum"} and formatting in {"text", "decimal", "integer", "percent"})
        addresses = _addresses(reference)
        referenced_cells += len(addresses)
        _require(referenced_cells <= 100_000)
        _require(operation != "cell" or len(addresses) == 1)
        numbers = []
        formulas = {}
        text = ""
        for address in addresses:
            cell = sheets[sheet].get(address)
            if cell is None:
                raise ProjectError("Pflichtquelle fehlt. Berichtszuordnung lokal prüfen.")
            value = cell_text(cell, strings)
            cell_type = cell.get("t", "n")
            formula = cell.find(f"{{{S}}}f")
            if formula is not None:
                if not (recalculate_excel or recalculate_libreoffice):
                    raise ProjectError("Formelquelle benötigt nachgewiesene lokale Neuberechnung; Cache allein wird nicht freigegeben.")
                if calculation is None:
                    calculation = recalculate(excel) if recalculate_excel else recalculate_with_libreoffice(excel)
                    _require(calculation["source_sha256"] == source_hash)
                fresh = calculation["cells"][sheet][address]["value"]
                _require(type(fresh) in {str, int, float})
                cell_type = "str" if type(fresh) is str else "n"
                value = str(fresh)
                formulas[address] = {"formula": "=" + (formula.text or ""), "value": value}
            _require(bool(value))
            if formatting == "text":
                _require(operation == "cell" and cell_type in {"s", "inlineStr", "str"} and "decimals" not in field)
                text = value
            else:
                _require(cell_type == "n" and len(value) <= 64)
                style = int(cell.get("s", "0"))
                _require(style >= 0 and (style < len(xfs) or (style == 0 and not xfs)))
                format_id = int(xfs[style].get("numFmtId", "0")) if xfs else 0
                _require(format_id in formats and bool(formats[format_id]))
                code = formats[format_id]
                _require(not is_date_format(code))
                number = Decimal(value)
                _require(number.is_finite() and abs(number.adjusted()) <= 100)
                numbers.append(number)
        exact = None
        if numbers:
            value_number = sum(numbers, Decimal(0))
            exact = str(value_number)
            if formatting == "integer":
                _require("decimals" not in field and value_number == value_number.to_integral_value())
                text = format(value_number, ".0f")
            else:
                decimals = field.get("decimals")
                _require(type(decimals) is int and 0 <= decimals <= 8)
                display = value_number * (100 if formatting == "percent" else 1)
                rounded = display.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
                text = format(rounded, f".{decimals}f").replace(".", ",") + (" %" if formatting == "percent" else "")
        result[name] = {"text": text, "exact_value": exact,
                        "source": {"sheet": sheet, "range": reference, "operation": operation}}
        if formulas and calculation is not None:
            result[name]["calculation"] = {"engine": calculation["engine"], "version": calculation["version"],
                                           "source_sha256": source_hash, "formulas": formulas}
    _require(hashlib.sha256(excel.read_bytes()).hexdigest() == source_hash)
    return result
