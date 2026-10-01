"""Expand reviewed row mappings and clone plain Word table rows deterministically."""

from __future__ import annotations

import re
from copy import deepcopy
from functools import partial
from typing import Any

from lxml import etree

from pseudokrat.ki_office import ProjectError, W, rewrite_runs
from pseudokrat.word_fields import inspect_fields, text_segments

FIELD_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_.]{0,99})\s*\}\}")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,23}")


def _render_fields(text: str, *, values: dict[str, str]) -> str:
    return FIELD_PATTERN.sub(lambda match: values[match[1]], text)


def compile_tables(spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, list[dict[str, str]]]]:
    """Compile version 2 into a bounded version-1 cell map; preserve row order."""
    if not isinstance(spec, dict):
        raise ProjectError("Ungültige Berichtszuordnung.")
    if spec.get("version") != 2:
        return spec, {}
    if type(spec["version"]) is not int:
        raise ProjectError("Ungültige Zuordnungsversion.")
    if set(spec) != {"version", "reviewed", "template_sha256", "headers", "fields", "tables"}:
        raise ProjectError("Unbekannte Tabellenzuordnung.")
    if not isinstance(spec["fields"], dict) or not isinstance(spec["tables"], dict) or not 1 <= len(spec["tables"]) <= 50:
        raise ProjectError("Tabellenzuordnung fehlt oder überschreitet die Begrenzung.")
    fields = dict(spec["fields"])
    if any(not isinstance(k, str) or k.startswith("__tbl_") for k in fields):
        raise ProjectError("Reservierter Feldname.")
    groups = {}
    for name, table in spec["tables"].items():
        if not isinstance(name, str) or not _NAME.fullmatch(name) or not isinstance(table, dict):
            raise ProjectError("Ungültige Tabellenkennung.")
        if set(table) != {"sheet", "first_row", "last_row", "columns"}:
            raise ProjectError("Unbekannte Tabelleneinstellung.")
        first, last, columns = table["first_row"], table["last_row"], table["columns"]
        if (type(first) is not int or type(last) is not int or not 1 <= first <= last <= 1048576
            or last - first + 1 > 1000 or not isinstance(columns, dict) or not 1 <= len(columns) <= 50):
            raise ProjectError("Tabellenbereich ungültig oder zu groß.")
        if any(k.startswith(name + ".") for k in fields):
            raise ProjectError("Tabellen- und Einzelfelder überschneiden sich.")
        rows = []
        for row in range(first, last + 1):
            targets = {}
            for column_name, definition in columns.items():
                if (not isinstance(column_name, str) or not _NAME.fullmatch(column_name)
                    or not isinstance(definition, dict)
                    or not {"column", "format"} <= set(definition) <= {"column", "format", "decimals"}
                    or not isinstance(definition["column"], str)
                    or not re.fullmatch(r"[A-Z]{1,3}", definition["column"])):
                    raise ProjectError("Ungültige Tabellenspalte.")
                key = f"__tbl_{len(fields):05d}"
                fields[key] = {k: v for k, v in definition.items() if k != "column"}
                fields[key].update({"sheet": table["sheet"], "range": f"{definition['column']}{row}", "operation": "cell"})
                targets[column_name] = key
                if len(fields) > 10_000:
                    raise ProjectError("Zu viele Berichts- und Tabellenfelder.")
            rows.append(targets)
        groups[name] = rows
    compiled = {k: v for k, v in spec.items() if k != "tables"}
    compiled.update({"version": 1, "fields": fields})
    return compiled, groups


def render_tables(roots: dict[str, Any], groups: dict[str, list[dict[str, str]]], facts: dict[str, Any]) -> dict[str, Any]:
    """Require one complete prototype row per table; never silently drop rows."""
    evidence = {}
    _, protected = inspect_fields(roots)
    drawing_ids = [e.get("id", "") for root in roots.values() for e in root.iter()
                   if etree.QName(e).localname in {"docPr", "cNvPr"}]
    if any(not identifier.isdecimal() for identifier in drawing_ids):
        raise ProjectError("Ungültige Bildkennung in der Word-Vorlage.")
    next_drawing_id = max((int(identifier) for identifier in drawing_ids), default=0) + 1
    for name, rows in groups.items():
        expected = {name + "." + column for column in rows[0]}
        candidates = []
        for part, root in roots.items():
            if not part.startswith("word/"):
                continue
            for row in root.iter(f"{{{W}}}tr"):
                found = set()
                for paragraph in row.iter(f"{{{W}}}p"):
                    for nodes in text_segments(paragraph, protected):
                        text = "".join(n.text or "" for n in nodes)
                        found.update(FIELD_PATTERN.findall(text))
                        remainder = FIELD_PATTERN.sub("", text)
                        if ("{{" in remainder or "}}" in remainder) and name + "." in text:
                            raise ProjectError("Beschädigte Tabellenplatzhalter.")
                if any(field.startswith(name + ".") for field in found):
                    if found != expected:
                        raise ProjectError("Tabellenmusterzeile enthält fehlende, fremde oder gemischte Felder.")
                    candidates.append(row)
        if len(candidates) != 1:
            raise ProjectError("Tabellenmusterzeile fehlt oder ist mehrdeutig.")
        prototype = candidates[0]
        blocked = {"vMerge", "bookmarkStart", "bookmarkEnd", "footnoteReference", "endnoteReference", "commentReference", "tbl"}
        if any(etree.QName(e).localname in blocked for e in prototype.iter()):
            raise ProjectError("Verknüpfte, verschachtelte oder vertikal verbundene Tabellenmusterzeile wird nicht unterstützt.")
        parent = prototype.getparent()
        position = parent.index(prototype)
        row_facts = []
        for index, targets in enumerate(rows):
            values = {name + "." + column: facts[key]["text"] for column, key in targets.items()}
            if any("{{" in value or "}}" in value for value in values.values()):
                raise ProjectError("Tabellenquelle enthält reservierte Platzhalterzeichen.")
            clone = deepcopy(prototype)
            _, clone_protected = inspect_fields({"row": clone})
            for element in clone.iter():
                if etree.QName(element).localname in {"docPr", "cNvPr"}:
                    if next_drawing_id > 4294967295:
                        raise ProjectError("Zu viele Bildkennungen in der Word-Vorlage.")
                    element.set("id", str(next_drawing_id))
                    next_drawing_id += 1
                for attribute in list(element.attrib):
                    if etree.QName(attribute).localname in {"paraId", "textId"}:
                        del element.attrib[attribute]
            for p in clone.iter(f"{{{W}}}p"):
                for nodes in text_segments(p, clone_protected):
                    rewrite_runs(nodes, partial(_render_fields, values=values))
            parent.insert(position + index, clone)
            row_facts.append({column: facts[key] for column, key in targets.items()})
        parent.remove(prototype)
        evidence[name] = row_facts
        for targets in rows:
            for key in targets.values():
                del facts[key]
    return evidence
