"""Local, reviewed Excel/Word development packages and encrypted reverse mapping."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Iterable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from cryptography.fernet import Fernet, InvalidToken
from lxml import etree

from pseudokrat.anonymizer import _resolve_overlaps
from pseudokrat.ki_office import (
    ProjectError,
    S,
    W,
    cell_text,
    read_office,
    shared_text,
    tag_local,
    transform_office,
    write_office,
)
from pseudokrat.recognizers import default_recognizers
from pseudokrat.recognizers.base import Recognizer
from pseudokrat.recognizers.property_identity import PropertyIdentityRecognizer, field_kind

_TOKEN = re.compile(r"\[\[PK_[A-Za-z0-9_]+\]\]")
_VERSION = 1


class _Mapping:
    def __init__(self, terms: Iterable[str], detector: Recognizer | None = None) -> None:
        self.project_id = secrets.token_hex(8)
        self.entries: dict[str, str] = {}
        self.reverse: dict[str, str] = {}
        self.numeric: dict[str, str] = {}
        self.recognizers = [*default_recognizers(), PropertyIdentityRecognizer()]
        if detector is not None:
            self.recognizers.append(detector)
        for term in terms:
            if term.strip():
                self.token(term.strip())

    def token(self, original: str) -> str:
        if _TOKEN.fullmatch(original):
            if original not in self.reverse:
                raise ProjectError("Eingabe enthält fremde Projekt-Platzhalter.")
            return original
        if original not in self.entries:
            token = f"[[PK_{self.project_id}_{len(self.entries) + 1:05d}]]"
            self.entries[original] = token
            self.reverse[token] = original
        return self.entries[original]

    def discover(self, text: str) -> None:
        if "[[PK_" in text:
            raise ProjectError("Originaldatei enthält bereits Projekt-Platzhalter.")
        spans = _resolve_overlaps([s for r in self.recognizers for s in r.analyze(text)])
        for span in spans:
            self.token(span.text)

    def transform(self, text: str) -> str:
        if not self.entries:
            return text
        # One pass: replacement tokens never feed back into the replacement input.
        pattern = re.compile(
            r"(?<!\w)(?:" + "|".join(re.escape(s) for s in sorted(self.entries, key=len, reverse=True))
            + r")(?!\w)"
        )
        parts = _TOKEN.split(text)
        tokens = _TOKEN.findall(text)
        out = []
        for index, part in enumerate(parts):
            out.append(pattern.sub(lambda m: self.entries[m.group()], part))
            if index < len(tokens):
                out.append(tokens[index])
        return "".join(out)


def _text_segments(roots: dict[str, Any]) -> list[str]:
    result = []
    for name, root in roots.items():
        if name.startswith("docProps/"):
            continue
        containers = list(root.iter(f"{{{W}}}p")) if name.startswith("word/") else [
            e for e in root.iter() if tag_local(e) in {"si", "is"}
        ]
        for element in containers:
            result.append("".join(e.text or "" for e in element.iter() if tag_local(e) == "t"))
        for element in root.iter():
            if tag_local(element) in {"oddHeader", "oddFooter", "evenHeader", "evenFooter",
                                      "firstHeader", "firstFooter"} and element.text:
                result.append(element.text)
    return result


def _identity_cells(roots: dict[str, Any], mapping: _Mapping) -> tuple[list[Any], list[dict[str, Any]]]:
    shared = shared_text(roots)
    identities, schema = [], []
    for name, root in roots.items():
        if not re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name):
            continue
        rows = list(root.iter(f"{{{S}}}row"))
        nonempty = [row for row in rows if any(cell_text(c, shared) for c in row)]
        columns: dict[str, str] = {}
        header_row = nonempty[0] if nonempty else None
        if header_row is not None:
            for cell in header_row:
                text = cell_text(cell, shared)
                column = re.sub(r"\d", "", cell.get("r", ""))
                columns[column] = field_kind(text)
        counts = {"identity_cells": 0, "numeric_cells": 0, "quasi_identifier_columns": 0}
        counts["quasi_identifier_columns"] = sum(v == "quasi_identifier" for v in columns.values())
        for row in rows:
            for cell in row:
                if tag_local(cell) != "c":
                    continue
                column = re.sub(r"\d", "", cell.get("r", ""))
                text = cell_text(cell, shared)
                is_number = cell.get("t", "n") == "n" and cell.find(f"{{{S}}}v") is not None
                if is_number:
                    counts["numeric_cells"] += 1
                if row is not header_row and columns.get(column) == "identity" and text:
                    if cell.find(f"{{{S}}}f") is not None:
                        raise ProjectError("Berechnete Identifikatoren benötigen eine lokale Feldzuordnung.")
                    token = mapping.token(text)
                    if is_number:
                        mapping.numeric[token] = text
                    identities.append(cell)
                    counts["identity_cells"] += 1
        schema.append({"part": name, "columns": columns, **counts})
    return identities, schema


def _replace_identity_cells(cells: list[Any], roots: dict[str, Any], mapping: _Mapping) -> None:
    shared = shared_text(roots)
    for cell in cells:
        token = mapping.token(cell_text(cell, shared))
        for child in list(cell):
            cell.remove(child)
        cell.set("t", "inlineStr")
        inline = etree.SubElement(cell, f"{{{S}}}is")
        etree.SubElement(inline, f"{{{S}}}t").text = token


def _numeric_snapshot(roots: dict[str, Any], excluded: set[int]) -> dict[str, str]:
    result = {}
    for name, root in roots.items():
        if not name.startswith("xl/worksheets/"):
            continue
        for cell in root.iter(f"{{{S}}}c"):
            if id(cell) in excluded:
                continue
            if cell.get("t", "n") not in {"n", "b", "d", "e"}:
                continue
            value = cell.find(f"{{{S}}}v")
            result[name + ":" + cell.get("r", "")] = json.dumps(
                [cell.get("t", "n"), value.text if value is not None else None, cell.get("s")]
            )
    return result


def _dump(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare_project(
    inputs: Iterable[Path], destination: Path, key: Fernet, *,
    terms: Iterable[str] = (), detector: Recognizer | None = None,
) -> Path:
    """Create only a LOCAL preview and encrypted manifest; publishing is separate."""
    paths = [Path(p).resolve() for p in inputs]
    destination = Path(destination).resolve()
    if destination.exists():
        raise ProjectError("Zielordner existiert bereits. Einen neuen Projektordner wählen.")
    if not paths or len(paths) > 20 or len(set(paths)) != len(paths):
        raise ProjectError("Ein bis zwanzig unterschiedliche Office-Dateien auswählen.")
    mapping = _Mapping(terms, detector)
    documents = [read_office(path) for path in paths]
    sheet_maps = []
    identities_by_file = []
    schemas = []
    for roots in documents:
        workbook = roots.get("xl/workbook.xml")
        sheets = {
            e.get("name"): f"Blatt_{i:03d}"
            for i, e in enumerate(workbook.iter(f"{{{S}}}sheet"), 1)
        } if workbook is not None else {}
        sheet_maps.append(sheets)
        identities, schema = _identity_cells(roots, mapping)
        identities_by_file.append(identities)
        schemas.append(schema)
        for text in _text_segments(roots):
            mapping.discover(text)
        # Formula text literals also carry names (e.g. SUMIF criteria).
        for root in roots.values():
            for element in root.iter(f"{{{S}}}f"):
                for literal in re.findall(r'"((?:[^"]|"")*)"', element.text or ""):
                    mapping.discover(literal.replace('""', '"'))
    outputs: dict[str, bytes] = {}
    bindings: list[dict[str, Any]] = []
    for i, (path, roots, sheets, identities, schema) in enumerate(
        zip(paths, documents, sheet_maps, identities_by_file, schemas, strict=True), 1
    ):
        excluded = {id(cell) for cell in identities}
        before = _numeric_snapshot(roots, excluded)
        _replace_identity_cells(identities, roots, mapping)
        transform_office(roots, mapping.transform, sheets)
        if before != _numeric_snapshot(roots, excluded):
            raise ProjectError("Rechenwerte wurden verändert; Export gesperrt.")
        filename = f"daten_{i:02d}.xlsx" if path.suffix.lower() == ".xlsx" else f"vorlage_{i:02d}.docx"
        outputs[filename] = write_office(roots)
        bindings.append({"file": filename, "original_path": str(path), "sheets": sheets,
                         "original_sha256": _digest(path.read_bytes()), "schema": schema})
    outputs["schema.json"] = _dump({
        "version": _VERSION, "project_id": mapping.project_id,
        "numbers_preserved": True, "identity_numbers_replaced": bool(mapping.numeric),
        "files": [{"file": b["file"], "sheets": list(b["sheets"].values()), "schema": b["schema"]}
                  for b in bindings],
    })
    outputs["entwicklungsauftrag.md"] = (
        "# Berichtscode entwickeln\n\n"
        "Diese Excel-/Word-Dateien sind pseudonymisiert. Rechenwerte sind unverändert.\n"
        "Entwickle einen lokal ausführbaren Berichtsgenerator für die mitgelieferte Word-Vorlage. "
        "Befülle Tabellen und formuliere Texte aus belegten Berechnungen. "
        "Verwende Datenreferenzen statt eingebauter Beispielwerte oder Namen. "
        "Projekt-Platzhalter [[PK_...]] unverändert erhalten. Keine Cloud-Aufrufe im Generator. "
        "Tabellen und Formeln dürfen nicht durch frei erfundene Werte ersetzt werden. "
        "Die lokale Ausführung verwendet Originaldaten. Fehlende Fachregeln kennzeichnen.\n\n"
        "Die Zahlen und Merkmalskombinationen können Rückschlüsse erlauben. "
        "Dieses Paket ist kein Nachweis vollständiger Anonymität.\n"
    ).encode()
    manifest = {
        "version": _VERSION, "project_id": mapping.project_id, "mapping": mapping.reverse,
        "numeric": mapping.numeric, "bindings": bindings,
        "hashes": {name: _digest(data) for name, data in outputs.items()},
    }
    review = {
        "status": "local_review_required", "numbers_preserved": True,
        "identity_replacements": len(mapping.entries),
        "numeric_identifiers": len(mapping.numeric),
        "quasi_identifier_columns": sum(s["quasi_identifier_columns"] for schema in schemas for s in schema),
        "message": "Vorschau lokal vollständig prüfen. Echte Zahlen können Zuordnung ermöglichen. "
                   "Keine garantierte Anonymität; bei verbleibender Zuordnung nicht freigeben.",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    # All original processing is in memory. Staging contains only transformed
    # files and ciphertext. Atomic rename avoids half-created project folders.
    with TemporaryDirectory(prefix=".pseudokrat-", dir=destination.parent) as staging:
        folder = Path(staging) / "project"
        preview = folder / "vorschau"
        preview.mkdir(parents=True)
        for name, data in outputs.items():
            (preview / name).write_bytes(data)
        (folder / "zuordnung.enc").write_bytes(key.encrypt(_dump(manifest)))
        (folder / "pruefung.json").write_bytes(_dump(review))
        folder.rename(destination)
    return destination


def _manifest(project: Path, key: Fernet) -> dict[str, Any]:
    try:
        raw = (project / "zuordnung.enc").read_bytes()
        data: dict[str, Any] = json.loads(key.decrypt(raw))
        if data["version"] != _VERSION:
            raise ProjectError("Projektversion wird nicht unterstützt.")
        if not all(isinstance(data[k], dict) for k in ("mapping", "numeric", "hashes")):
            raise ProjectError("Ungültiges Projektmanifest.")
        return data
    except (OSError, InvalidToken, ValueError, KeyError, TypeError) as exc:
        raise ProjectError("Zuordnung kann mit diesem Profil nicht geöffnet werden.") from exc


def publish_project(
    project: Path, key: Fernet, *, reviewed: bool = False,
    accept_numeric_linkability: bool = False,
) -> Path:
    """Publish only exactly the reviewed immutable preview, never the vault."""
    if not reviewed:
        raise ProjectError("Lokale Prüfung der vollständigen Vorschau ist erforderlich.")
    if not accept_numeric_linkability:
        raise ProjectError("Unveränderte Zahlen können zuordenbar sein; Restrisiko lokal bewerten.")
    project = Path(project).resolve()
    manifest = _manifest(project, key)
    files = {}
    for name, expected in manifest["hashes"].items():
        if Path(name).name != name:
            raise ProjectError("Ungültiger Paketname.")
        file = project / "vorschau" / name
        if file.is_symlink() or not file.is_file():
            raise ProjectError("Vorschau wurde verändert. Neues Projekt erzeugen und prüfen.")
        data = file.read_bytes()
        if _digest(data) != expected:
            raise ProjectError("Vorschau wurde verändert. Neues Projekt erzeugen und prüfen.")
        files[name] = data
    output = project / "KI-Paket.zip"
    if output.exists():
        raise ProjectError("KI-Paket existiert bereits; es wird nicht überschrieben.")
    with output.open("xb") as handle, ZipFile(handle, "w", ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return output


def restore_file(project: Path, key: Fernet, source: Path, destination: Path) -> Path:
    """Resolve exact project tokens only; unsupported or unknown content blocks."""
    destination = Path(destination)
    if destination.exists() or destination.suffix.lower() != source.suffix.lower():
        raise ProjectError("Neuen Zielpfad mit derselben Dateiendung auswählen.")
    manifest = _manifest(Path(project), key)
    roots = read_office(source)

    def restore(text: str) -> str:
        def replace(match: re.Match[str]) -> str:
            if match.group() not in manifest["mapping"]:
                raise ProjectError("Unbekannter Projekt-Platzhalter; Rückwandlung gesperrt.")
            return str(manifest["mapping"][match.group()])
        result = _TOKEN.sub(replace, text)
        if "[[PK_" in result:
            raise ProjectError("Beschädigter Projekt-Platzhalter; Rückwandlung gesperrt.")
        return result

    sheets: dict[str, str] = {}
    workbook = roots.get("xl/workbook.xml")
    if workbook is not None:
        candidates = [b for b in manifest["bindings"] if b["file"] == source.name]
        if not candidates:
            candidates = [b for b in manifest["bindings"] if b["sheets"]]
        if len(candidates) != 1:
            raise ProjectError("Excel-Quelldatei ist nicht eindeutig zugeordnet.")
        sheets = {new: old for old, new in candidates[0]["sheets"].items()}
        for element in workbook.iter(f"{{{S}}}sheet"):
            if element.get("name") not in sheets:
                raise ProjectError("Excel-Struktur wurde verändert; Zuordnung prüfen.")
    # Restore numeric ID cells as numeric cells, not numeric-looking strings.
    shared = shared_text(roots)
    for name, root in roots.items():
        if not name.startswith("xl/worksheets/"):
            continue
        for cell in root.iter(f"{{{S}}}c"):
            token = cell_text(cell, shared)
            if token in manifest["numeric"]:
                for child in list(cell):
                    cell.remove(child)
                cell.set("t", "n")
                etree.SubElement(cell, f"{{{S}}}v").text = manifest["numeric"][token]
    transform_office(roots, restore, sheets)
    data = write_office(roots)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as handle:
        handle.write(data)
    return destination


def prepare_original_workspace(project: Path, key: Fernet, destination: Path) -> Path:
    """Explicit LOCAL handoff for a trusted coding model; never a cloud package.

Keep real values, use the same neutral sheet names as the development files,
and provide the exact project token mapping locally for template integration.
No code or model is automatically executed, and nothing is uploaded.
"""
    destination = Path(destination).resolve()
    if destination.exists():
        raise ProjectError("Zielordner existiert bereits.")
    manifest = _manifest(Path(project), key)
    outputs = {}
    for binding in manifest["bindings"]:
        original = Path(binding["original_path"])
        if not original.is_file() or _digest(original.read_bytes()) != binding["original_sha256"]:
            raise ProjectError("Originaldatei wurde verändert oder verschoben. Neues Projekt vorbereiten.")
        roots = read_office(original)
        transform_office(roots, lambda text: text, binding["sheets"])
        outputs[binding["file"]] = write_office(roots)
    outputs["lokale-zuordnung.json"] = _dump(manifest["mapping"])
    outputs["SPARK-AUFTRAG.md"] = (
        "# VERTRAULICH – nur auf dem eigenen Spark verwenden\n\n"
        "Dieser Ordner enthält ORIGINALDATEN und die Klartext-Zuordnung. Nicht an eine Cloud-KI senden.\n\n"
        "Setze den an pseudonymisierten Beispielen entwickelten Berichtscode mit den hier liegenden "
        "Excel- und Word-Dateien um. Neutrale Dateinamen und Blattnamen entsprechen dem KI-Paket; "
        "Zahlen und Inhalte sind echt. Nutze lokale-zuordnung.json nur für exakte Platzhalter. "
        "Erzeuge den Word-Bericht lokal, einschließlich Tabellen und datenbasierten Texten. "
        "Keine Cloud-, Telemetrie- oder externen Datenaufrufe. Originale nicht überschreiben. "
        "Fachliche Annahmen und fehlende Feldzuordnungen als offene Punkte melden. "
        "Jede Zahl gegen die Excel-Quelle prüfen, keine Ursachen erfinden. "
        "Für Qwen3-Coder-Next: Code umsetzen und testen. Für GPT-OSS 120B: Fakten und Texte prüfen. "
        "BGE-M3 ist optional für lokale Suche, kein Nachweis der Anonymität.\n\n"
        "Berichtscode wird separat vom Benutzer bereitgestellt. Pseudokrat führt keinen fremden Code aus.\n"
    ).encode()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".pseudokrat-local-", dir=destination.parent) as staging:
        folder = Path(staging) / "originaldaten"
        folder.mkdir()
        for name, data in outputs.items():
            (folder / name).write_bytes(data)
        folder.rename(destination)
    return destination


__all__ = ["ProjectError", "prepare_original_workspace", "prepare_project", "publish_project", "restore_file"]
