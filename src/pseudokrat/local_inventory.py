"""Confidential offline inventory for local Excel-to-Word mapping work."""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import sys
from pathlib import Path
from typing import Any

from pseudokrat.ki_office import (
    ProjectError,
    S,
    W,
    cell_text,
    read_local_template,
    read_office,
    shared_text,
)


def inspect_documents(paths: list[Path]) -> dict[str, Any]:
    """Return local source structure. Never label this report safe for cloud use."""
    if not 1 <= len(paths) <= 20:
        raise ProjectError("Ein bis zwanzig Dateien auswählen.")
    files: list[dict[str, Any]] = []
    for path in paths:
        item: dict[str, Any] = {"path": str(path.resolve()), "status": "inspected"}
        files.append(item)
        try:
            media: dict[str, bytes] = {}
            if path.suffix.lower() == ".docx":
                roots, media = read_local_template(path)
            else:
                roots = read_office(path)
            workbook = roots.get("xl/workbook.xml")
            if workbook is not None:
                rels = roots.get("xl/_rels/workbook.xml.rels")
                if rels is None:
                    raise ProjectError("Excel-Blattzuordnung fehlt.")
                targets = {r.get("Id"): posixpath.normpath(posixpath.join("xl", r.get("Target", ""))).lstrip("/") for r in rels}
                strings = shared_text(roots)
                sheets = []
                for sheet in workbook.iter(f"{{{S}}}sheet"):
                    target = targets.get(sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"))
                    if target not in roots:
                        raise ProjectError("Excel-Blattzuordnung ist ungültig.")
                    root = roots[target]
                    rows = list(root.iter(f"{{{S}}}row"))
                    cells = list(root.iter(f"{{{S}}}c"))
                    first = next((row for row in rows if any(cell_text(c, strings) for c in row)), None)
                    formulas = [c for c in cells if c.find(f"{{{S}}}f") is not None]
                    sheets.append({
                        "name": sheet.get("name"), "state": sheet.get("state", "visible"),
                        "stored_rows": len(rows), "stored_cells": len(cells),
                        "candidate_header": [{"cell": c.get("r"), "text": cell_text(c, strings)} for c in first] if first is not None else [],
                        "header_confirmed": False,
                        "formula_cells": len(formulas),
                        "formulas_without_cached_value": sum(c.find(f"{{{S}}}v") is None or c.find(f"{{{S}}}v").text is None for c in formulas),
                        "calculation_engine_verified": False,
                    })
                item["sheets"] = sheets
            else:
                paragraphs = []
                table_count = 0
                for name, root in roots.items():
                    if not name.startswith("word/"):
                        continue
                    table_count += sum(1 for _ in root.iter(f"{{{W}}}tbl"))
                    for p in root.iter(f"{{{W}}}p"):
                        paragraphs.append("".join(t.text or "" for t in p.iter(f"{{{W}}}t")))
                item.update({
                    "paragraph_count": len(paragraphs), "table_count": table_count,
                    "placeholders": sorted({m for p in paragraphs for m in re.findall(r"\{\{\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\}\}", p)}),
                    "placeholder_syntax": "{{ field_name }} only; other target types require local mapping",
                    "mapping_confirmed": False, "layout_verified": False,
                    "embedded_image_count": len(media), "image_contents_reviewed": False,
                })
        except ProjectError as exc:
            item.clear()
            item.update({"path": str(path.resolve()), "status": "blocked", "reason": str(exc)})
    return {
        "version": 1, "classification": "CONFIDENTIAL_LOCAL_ONLY",
        "production_approved": False,
        "notice": "Enthält Originalpfade und möglicherweise Originaltexte. Nicht an externe KI weitergeben.",
        "files": files,
        "required_local_checks": ["Fachliche Quellen-Ziel-Zuordnung", "Excel-Neuberechnung", "Word-Layout", "Lokale Abnahme"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VERTRAULICHE Bestandsaufnahme auf dem eigenen Rechner/Spark.")
    parser.add_argument("--input", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ProjectError("Ausgabe existiert bereits; neuen Zielpfad wählen.")
        report = inspect_documents(args.input)
        payload = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
        print("VERTRAULICHER lokaler Prüfbericht erstellt. Nicht weitergeben; keine Produktionsfreigabe.")
        return 20 if any(f["status"] == "blocked" for f in report["files"]) else 0
    except (ProjectError, OSError, ValueError):
        print("Bestandsaufnahme fehlgeschlagen. Dateien und neuen Ausgabeort lokal prüfen.", file=sys.stderr)
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
