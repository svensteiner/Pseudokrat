"""Bounded, fail-closed OOXML processing for reviewed development packages.

Preserve numeric XML and formulas; reject opaque/unsupported parts instead of
claiming to sanitize them. No Office automation, macros or network access.
"""

from __future__ import annotations

import difflib
import io
import posixpath
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from lxml import etree
from openpyxl.formula.tokenizer import Tokenizer
from openpyxl.utils.cell import range_boundaries
from openpyxl.utils.formulas import FORMULAE

MAX_BYTES = 50 * 1024 * 1024
MAX_PART = 10 * 1024 * 1024
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/package/2006/relationships"
_SAFE_FUNCTIONS = set(FORMULAE) | {"XLOOKUP", "XMATCH", "FILTER", "SORT", "SORTBY", "UNIQUE", "SEQUENCE", "LET", "IFS", "SWITCH", "TEXTJOIN", "CONCAT"}
_UNSAFE_FUNCTIONS = {"INDIRECT", "HYPERLINK", "WEBSERVICE", "RTD", "IMAGE", "STOCKHISTORY", "CALL", "EXEC", "REGISTER", "REGISTER.ID", "SQL.REQUEST"}
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
    if cell.get("t") == "s":
        try:
            index = int(value.text) if value is not None else -1
            if index < 0:
                raise ValueError
            return shared[index]
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


def compact_shared_strings(roots: dict[str, Any]) -> None:
    """Remove unused Excel strings, including former ID values, and remap indices."""
    table = roots.get("xl/sharedStrings.xml")
    if table is None:
        return
    entries = list(table)
    references: list[tuple[Any, int]] = []
    for name, root in roots.items():
        if not name.startswith("xl/worksheets/"):
            continue
        for cell in root.iter(f"{{{S}}}c"):
            if cell.get("t") != "s":
                continue
            value = cell.find(f"{{{S}}}v")
            try:
                index = int(value.text) if value is not None else -1
                if not 0 <= index < len(entries):
                    raise ValueError
            except (ValueError, TypeError) as exc:
                raise ProjectError("Ungültiger Excel-Textverweis.") from exc
            references.append((value, index))
    used = sorted({index for _, index in references})
    remap = {old: new for new, old in enumerate(used)}
    for entry in entries:
        table.remove(entry)
    for index in used:
        table.append(entries[index])
    for value, index in references:
        value.text = str(remap[index])
    table.set("count", str(len(references)))
    table.set("uniqueCount", str(len(used)))


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
        elif token.type == "FUNC" and token.subtype == "OPEN":
            function = re.sub(r"^_xlfn\.", "", value[:-1], flags=re.I).upper()
            if function in _UNSAFE_FUNCTIONS or function not in _SAFE_FUNCTIONS:
                raise ProjectError("Unbekannte, dynamische oder externe Formelfunktion wird nicht unterstützt.")
        result.append(value)
    return ("=" if prefix else "") + "".join(result)


def guard_numeric_identifiers(roots: dict[str, Any], identities: list[Any]) -> None:
    """Changing numeric IDs to tokens must never silently alter a dependent formula."""
    cells = [cell for cell in identities if cell.get("t", "n") == "n"]
    if not cells:
        return
    workbook = roots["xl/workbook.xml"]
    rels = roots.get("xl/_rels/workbook.xml.rels")
    if rels is None:
        raise ProjectError("Excel-Blattzuordnung kann nicht geprüft werden.")
    targets = {r.get("Id"): posixpath.normpath(posixpath.join("xl", r.get("Target", ""))).lstrip("/")
               for r in rels}
    parts = {s.get("name"): targets.get(s.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"))
             for s in workbook.iter(f"{{{S}}}sheet")}
    protected: dict[str, list[tuple[int, int]]] = {}
    for cell in cells:
        path = next(name for name, root in roots.items() if root is cell.getroottree().getroot())
        col, row, _, _ = range_boundaries(cell.get("r"))
        protected.setdefault(path, []).append((col, row))
    for name, root in roots.items():
        for formula in root.iter():
            if tag_local(formula) not in {"f", "definedName", "formula", "formula1", "formula2"}:
                continue
            try:
                tokens = Tokenizer("=" + (formula.text or "").lstrip("=")).items
                for token in tokens:
                    if token.subtype != "RANGE":
                        continue
                    ref, target = token.value, name
                    if "!" in ref:
                        sheet, ref = ref.rsplit("!", 1)
                        sheet = sheet[1:-1].replace("''", "'") if sheet.startswith("'") else sheet
                        target = parts.get(sheet) or ""
                    if target not in protected:
                        continue
                    lo_col, lo_row, hi_col, hi_row = range_boundaries(ref)
                    if any((lo_col is None or lo_col <= col <= hi_col) and
                           (lo_row is None or lo_row <= row <= hi_row)
                           for col, row in protected[target]):
                        raise ProjectError("Formel verwendet eine numerische Kennung. Lokale Feldzuordnung erforderlich.")
            except ProjectError:
                raise
            except (ValueError, TypeError) as exc:
                raise ProjectError("Formelbezug auf numerische Kennungen kann nicht sicher geprüft werden.") from exc


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
