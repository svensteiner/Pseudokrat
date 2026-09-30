"""Bounded, fail-closed OOXML processing for reviewed development packages.

Preserve numeric XML and formulas; reject opaque/unsupported parts instead of
claiming to sanitize them. No Office automation, macros or network access.
"""

from __future__ import annotations

import difflib
import io
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from lxml import etree
from openpyxl.formula.tokenizer import Tokenizer

MAX_BYTES = 50 * 1024 * 1024
MAX_PART = 10 * 1024 * 1024
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/package/2006/relationships"
_ALLOWED = re.compile(
    r"(?:\[Content_Types\]\.xml|_rels/\.rels|docProps/(?:core|app|custom)\.xml|"
    r"xl/(?:workbook|styles|sharedStrings)\.xml|xl/theme/theme\d+\.xml|"
    r"xl/worksheets/sheet\d+\.xml|xl/_rels/workbook\.xml\.rels|"
    r"word/(?:document|styles|stylesWithEffects|settings|webSettings|fontTable|numbering|"
    r"footnotes|endnotes|header\d+|footer\d+)\.xml|word/theme/theme\d+\.xml|"
    r"word/_rels/(?:document|header\d+|footer\d+|footnotes|endnotes)\.xml\.rels)"
)


class ProjectError(ValueError):
    """Safe user-facing error; never interpolate source content or parser errors."""


def tag_local(element: Any) -> str:
    return etree.QName(element).localname if isinstance(element.tag, str) else ""


def read_office(path: Path) -> dict[str, Any]:
    if path.suffix.lower() not in {".xlsx", ".docx"}:
        raise ProjectError("Nur XLSX und DOCX werden im KI-Projekt unterstützt.")
    try:
        if path.stat().st_size > MAX_BYTES:
            raise ProjectError("Datei überschreitet die unterstützte Größenbegrenzung.")
        roots = {}
        with ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > 1000 or sum(i.file_size for i in infos) > MAX_BYTES:
                raise ProjectError("Office-Paket überschreitet die unterstützte Größenbegrenzung.")
            if len({i.filename for i in infos}) != len(infos):
                raise ProjectError("Doppelte Office-Bestandteile werden nicht unterstützt.")
            for info in infos:
                # Non-rendered custom data and original-page previews are never
                # needed by the development copy. Remove their links below too.
                if info.filename.startswith("customXml/") or info.filename.startswith("docProps/thumbnail."):
                    continue
                if not _ALLOWED.fullmatch(info.filename):
                    raise ProjectError(
                        "Nicht unterstützt: eingebettete oder zusätzliche Office-Bestandteile. "
                        "Bilder, Kommentare, Pivotdaten, Diagramme und Verbindungen lokal entfernen."
                    )
                if info.file_size > MAX_PART:
                    raise ProjectError("Office-Bestandteil überschreitet die Größenbegrenzung.")
                root = etree.fromstring(archive.read(info), etree.XMLParser(
                    resolve_entities=False, no_network=True, load_dtd=False,
                    remove_comments=True, remove_pis=True,
                ))
                if root.getroottree().docinfo.doctype:
                    raise ProjectError("XML-Dokumenttypdeklarationen werden nicht unterstützt.")
                roots[info.filename] = root
        expected = "xl/workbook.xml" if path.suffix.lower() == ".xlsx" else "word/document.xml"
        if expected not in roots:
            raise ProjectError("Dateiendung und Office-Inhalt stimmen nicht überein.")
        for root in roots.values():
            for element in list(root.iter()):
                local = tag_local(element)
                if ((local == "Relationship" and element.get("Type", "").rsplit("/", 1)[-1]
                     in {"customXml", "thumbnail"}) or
                    (local == "Override" and element.get("PartName", "").startswith("/customXml/"))):
                    element.getparent().remove(element)
                    continue
                if local == "Relationship" and element.get("TargetMode") == "External":
                    raise ProjectError("Externe Office-Verknüpfungen werden nicht unterstützt.")
                if local in {"oleObject", "object", "altChunk", "drawing", "pict", "extLst",
                             "hyperlink", "customXml", "sdt", "smartTag", "ins", "del",
                             "moveFrom", "moveTo", "fldSimple", "instrText"}:
                    raise ProjectError("Nicht unterstütztes Office-Element: " + local + ".")
                if local == "definedName" and not element.get("name", "").startswith("_xlnm."):
                    raise ProjectError("Benutzerdefinierte Excel-Bereichsnamen werden noch nicht unterstützt.")
                if local == "f" and element.attrib:
                    raise ProjectError("Geteilte, Array- oder spezielle Formeln werden noch nicht unterstützt.")
        return roots
    except (OSError, BadZipFile, etree.XMLSyntaxError, RuntimeError, KeyError) as exc:
        raise ProjectError("Office-Datei konnte nicht sicher gelesen werden.") from exc


def write_office(roots: dict[str, Any]) -> bytes:
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, root in roots.items():
            archive.writestr(name, etree.tostring(root, xml_declaration=True, encoding="UTF-8"))
    return output.getvalue()


def cell_text(cell: Any, shared: list[str]) -> str:
    value = cell.find(f"{{{S}}}v")
    if cell.get("t") == "s" and value is not None:
        try:
            return shared[int(value.text)]
        except (IndexError, ValueError, TypeError) as exc:
            raise ProjectError("Ungültiger Excel-Textverweis.") from exc
    if cell.get("t") == "inlineStr":
        return "".join(cell.itertext())
    return value.text or "" if value is not None else ""


def shared_text(roots: dict[str, Any]) -> list[str]:
    root = roots.get("xl/sharedStrings.xml")
    if root is None:
        return []
    return ["".join(si.itertext()) for si in root]


def rewrite_runs(nodes: list[Any], transform: Callable[[str], str]) -> None:
    """Replace across split runs while retaining unaffected run formatting."""
    original = "".join(node.text or "" for node in nodes)
    new = transform(original)
    if original == new:
        return
    bounds, offset = [], 0
    for node in nodes:
        size = len(node.text or "")
        bounds.append((offset, offset + size))
        offset += size
    for op, i, end, j, stop in reversed(difflib.SequenceMatcher(
        a=original, b=new, autojunk=False
    ).get_opcodes()):
        if op == "equal":
            continue
        start_node = next((n for n, (_, b) in enumerate(bounds) if b > i), len(nodes) - 1)
        end_node = next((n for n, (_, b) in enumerate(bounds) if b >= end), len(nodes) - 1)
        end_node = max(start_node, end_node)
        prefix = (nodes[start_node].text or "")[:i - bounds[start_node][0]]
        suffix = (nodes[end_node].text or "")[end - bounds[end_node][0]:]
        if start_node == end_node:
            nodes[start_node].text = prefix + new[j:stop] + suffix
        else:
            nodes[start_node].text = prefix + new[j:stop]
            for n in range(start_node + 1, end_node):
                nodes[n].text = ""
            nodes[end_node].text = suffix
    for node in nodes:
        node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def transform_formula(formula: str, transform: Callable[[str], str], sheets: dict[str, str]) -> str:
    """Keep arithmetic tokens verbatim; only rewrite text and exact sheet references."""
    prefix = formula.startswith("=")
    try:
        tokens = Tokenizer(formula if prefix else "=" + formula).items
    except Exception as exc:
        raise ProjectError("Formel kann nicht sicher geprüft werden.") from exc
    result = []
    for token in tokens:
        value = token.value
        if token.subtype == "TEXT":
            text = value[1:-1].replace('""', '"')
            value = '"' + transform(text).replace('"', '""') + '"'
        elif token.subtype == "RANGE" and "!" in value:
            sheet, ref = value.rsplit("!", 1)
            decoded = sheet[1:-1].replace("''", "'") if sheet.startswith("'") else sheet
            if decoded not in sheets:
                raise ProjectError("Externe oder mehrdeutige Blattreferenz wird nicht unterstützt.")
            value = "'" + sheets[decoded].replace("'", "''") + "'!" + ref
        elif token.type == "FUNC" and re.match(
            r"(?:_xlfn\.)?(?:INDIRECT|HYPERLINK|WEBSERVICE|RTD|IMAGE|STOCKHISTORY)\(", value, re.I
        ):
            raise ProjectError("Dynamische oder externe Formelfunktion wird nicht unterstützt.")
        result.append(value)
    return ("=" if prefix else "") + "".join(result)


def transform_office(
    roots: dict[str, Any], transform: Callable[[str], str], sheets: dict[str, str],
) -> None:
    """Transform text containers, strip properties, retain numeric/formula XML."""
    for name, root in roots.items():
        if name.startswith("docProps/"):
            for child in list(root):
                root.remove(child)
            continue
        if name.startswith("word/"):
            for paragraph in root.iter(f"{{{W}}}p"):
                nodes = list(paragraph.iter(f"{{{W}}}t"))
                if nodes:
                    rewrite_runs(nodes, transform)
        if name.startswith("xl/"):
            for element in list(root.iter()):
                local = tag_local(element)
                if local in {"si", "is"}:
                    nodes = list(element.iter(f"{{{S}}}t"))
                    if nodes:
                        rewrite_runs(nodes, transform)
                elif local == "sheet" and element.get("name") in sheets:
                    element.set("name", sheets[element.get("name")])
                elif local in {"f", "definedName", "formula", "formula1", "formula2"} and element.text:
                    element.text = transform_formula(element.text, transform, sheets)
                elif local in {"oddHeader", "oddFooter", "evenHeader", "evenFooter", "firstHeader", "firstFooter"} and element.text:
                    element.text = transform(element.text)
                elif local == "c" and element.get("t") == "str":
                    value = element.find(f"{{{S}}}v")
                    if value is not None and value.text:
                        value.text = transform(value.text)
        # Check metadata/attributes and unhandled text too. Do not alter unknown
        # structural fields: block instead when a sensitive value is found there.
        for element in root.iter():
            for value in element.attrib.values():
                if transform(value) != value:
                    raise ProjectError("Identifikator in einem nicht unterstützten Office-Attribut.")
            if (element.text and tag_local(element) not in {
                "t", "v", "f", "definedName", "formula", "formula1", "formula2",
                "oddHeader", "oddFooter", "evenHeader", "evenFooter", "firstHeader", "firstFooter",
            } and transform(element.text) != element.text):
                raise ProjectError("Identifikator in einem nicht unterstützten Office-Inhalt.")
