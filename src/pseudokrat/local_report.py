"""Deterministic offline draft reports from reviewed source-to-field mappings."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from pseudokrat.ki_office import (
    ProjectError,
    W,
    read_local_template,
    rewrite_runs,
    write_local_template,
)
from pseudokrat.report_mapping import resolve_mapping
from pseudokrat.report_narratives import compile_narratives, render_narratives
from pseudokrat.report_tables import FIELD_PATTERN as _FIELD
from pseudokrat.report_tables import compile_tables, render_tables
from pseudokrat.word_fields import inspect_fields, text_segments


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_private(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)


def generate_report(excel: Path, template: Path, mapping: Path, destination: Path, *, recalculate_excel: bool = False, recalculate_libreoffice: bool = False) -> Path:
    """Create a confidential draft plus provenance, never a production approval."""
    try:
        return _generate(excel, template, mapping, destination, recalculate_excel, recalculate_libreoffice)
    except ProjectError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ProjectError("Bericht konnte nicht sicher erzeugt werden. Eingaben lokal prüfen.") from exc


def _generate(excel: Path, template: Path, mapping: Path, destination: Path, recalculate_excel: bool, recalculate_libreoffice: bool) -> Path:
    destination = destination.resolve()
    if destination.exists() or mapping.stat().st_size > 1024 * 1024:
        raise ProjectError("Neuen Zielordner und eine unterstützte Zuordnungsdatei verwenden.")
    hashes = {"excel": _hash(excel), "template": _hash(template), "mapping": _hash(mapping)}
    spec = json.loads(mapping.read_text("utf-8-sig"))
    spec, narrative_rules = compile_narratives(spec)
    compiled, groups = compile_tables(spec)
    facts = resolve_mapping(excel, template, compiled, recalculate_excel=recalculate_excel, recalculate_libreoffice=recalculate_libreoffice)
    roots, media = read_local_template(template)
    tables = render_tables(roots, groups, facts)
    narratives, narrative_inputs = render_narratives(narrative_rules, facts)
    field_codes, protected = inspect_fields(roots)
    render_values = {**facts, **narratives}
    paragraphs: list[tuple[list[Any], str]] = []
    found: set[str] = set()
    for name, root in roots.items():
        if not name.startswith("word/"):
            continue
        for p in root.iter(f"{{{W}}}p"):
            for nodes in text_segments(p, protected):
                text = "".join(n.text or "" for n in nodes)
                remainder = _FIELD.sub("", text)
                if "{{" in remainder or "}}" in remainder:
                    raise ProjectError("Nicht unterstützte oder beschädigte Word-Platzhalter.")
                found.update(_FIELD.findall(text))
                paragraphs.append((nodes, text))
    if (not found <= set(render_values) or not set(narratives) <= found
        or not set(facts) <= found | narrative_inputs):
        raise ProjectError("Word-Platzhalter und geprüfte Zuordnung stimmen nicht vollständig überein.")
    if any("{{" in f["text"] or "}}" in f["text"] for f in render_values.values()):
        raise ProjectError("Quelldaten enthalten reservierte Platzhalterzeichen; lokale Zuordnung prüfen.")
    for nodes, _ in paragraphs:
        if nodes:
            rewrite_runs(nodes, lambda text: _FIELD.sub(lambda match: render_values[match[1]]["text"], text))
    for root in roots.values():
        for element in root.iter():
            values = [element.text or "", *element.attrib.values()]
            if any("{{" in v or "}}" in v for v in values):
                raise ProjectError("Nicht ersetzter Platzhalter in einem nicht unterstützten Word-Bereich.")
    current = {"excel": _hash(excel), "template": _hash(template), "mapping": _hash(mapping)}
    if hashes != current:
        raise ProjectError("Eingaben wurden während der Verarbeitung verändert. Erneut starten.")
    output = write_local_template(roots, media)
    evidence = {
        "version": 1, "classification": "CONFIDENTIAL_LOCAL_ONLY", "status": "draft_requires_local_review",
        "production_approved": False, "layout_verified": False,
        "input_sha256": hashes, "output_sha256": hashlib.sha256(output).hexdigest(), "facts": facts,
        "tables": tables,
        "narratives": narratives,
        "embedded_media_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in media.items()},
        "word_fields": {"codes": field_codes, "updated": False},
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".pseudokrat-report-", dir=destination.parent) as staging:
        folder = Path(staging) / "result"
        folder.mkdir(mode=0o700)
        _write_private(folder / "bericht.docx", output)
        _write_private(folder / "nachweis.json", json.dumps(evidence, ensure_ascii=False, indent=2).encode("utf-8"))
        if destination.exists():
            raise ProjectError("Zielordner wurde zwischenzeitlich angelegt; neuen Zielordner wählen.")
        folder.rename(destination)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vertraulichen Word-Berichtsentwurf lokal erzeugen.")
    for name in ("excel", "template", "mapping", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    engines = parser.add_mutually_exclusive_group()
    engines.add_argument("--recalculate-excel", action="store_true", help="Formeln mit installiertem lokalem Microsoft Excel neu berechnen (Windows).")
    engines.add_argument("--recalculate-libreoffice", action="store_true", help="Formeln mit installiertem lokalem LibreOffice Calc neu berechnen (Linux; eingeschränkte Kompatibilität).")
    args = parser.parse_args(argv)
    try:
        generate_report(args.excel, args.template, args.mapping, args.output, recalculate_excel=args.recalculate_excel, recalculate_libreoffice=args.recalculate_libreoffice)
        print("Vertraulicher Berichtsentwurf mit Quellennachweis erstellt. Layout und Fachinhalt lokal prüfen.")
        return 0
    except ProjectError:
        print("Berichtserstellung gestoppt. Quellen, Zuordnung und Vorlage lokal prüfen.", file=sys.stderr)
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
