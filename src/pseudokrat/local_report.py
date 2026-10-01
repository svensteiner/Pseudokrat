"""Deterministic offline draft reports from reviewed source-to-field mappings."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from pseudokrat.ki_office import ProjectError, W, read_office, rewrite_runs, write_office
from pseudokrat.report_mapping import resolve_mapping

_FIELD = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_.]{0,99})\s*\}\}")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_private(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)


def generate_report(excel: Path, template: Path, mapping: Path, destination: Path) -> Path:
    """Create a confidential draft plus provenance, never a production approval."""
    try:
        return _generate(excel, template, mapping, destination)
    except ProjectError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ProjectError("Bericht konnte nicht sicher erzeugt werden. Eingaben lokal prüfen.") from exc


def _generate(excel: Path, template: Path, mapping: Path, destination: Path) -> Path:
    destination = destination.resolve()
    if destination.exists() or mapping.stat().st_size > 1024 * 1024:
        raise ProjectError("Neuen Zielordner und eine unterstützte Zuordnungsdatei verwenden.")
    hashes = {"excel": _hash(excel), "template": _hash(template), "mapping": _hash(mapping)}
    spec = json.loads(mapping.read_text("utf-8-sig"))
    facts = resolve_mapping(excel, template, spec)
    roots = read_office(template)
    paragraphs: list[tuple[list[Any], str]] = []
    found: set[str] = set()
    for name, root in roots.items():
        if not name.startswith("word/"):
            continue
        for p in root.iter(f"{{{W}}}p"):
            nodes = list(p.iter(f"{{{W}}}t"))
            text = "".join(n.text or "" for n in nodes)
            remainder = _FIELD.sub("", text)
            if "{{" in remainder or "}}" in remainder:
                raise ProjectError("Nicht unterstützte oder beschädigte Word-Platzhalter.")
            found.update(_FIELD.findall(text))
            paragraphs.append((nodes, text))
    if found != set(facts):
        raise ProjectError("Word-Platzhalter und geprüfte Zuordnung stimmen nicht vollständig überein.")
    if any("{{" in f["text"] or "}}" in f["text"] for f in facts.values()):
        raise ProjectError("Quelldaten enthalten reservierte Platzhalterzeichen; lokale Zuordnung prüfen.")
    for nodes, _ in paragraphs:
        if nodes:
            rewrite_runs(nodes, lambda text: _FIELD.sub(lambda match: facts[match[1]]["text"], text))
    for root in roots.values():
        for element in root.iter():
            values = [element.text or "", *element.attrib.values()]
            if any("{{" in v or "}}" in v for v in values):
                raise ProjectError("Nicht ersetzter Platzhalter in einem nicht unterstützten Word-Bereich.")
    current = {"excel": _hash(excel), "template": _hash(template), "mapping": _hash(mapping)}
    if hashes != current:
        raise ProjectError("Eingaben wurden während der Verarbeitung verändert. Erneut starten.")
    output = write_office(roots)
    evidence = {
        "version": 1, "classification": "CONFIDENTIAL_LOCAL_ONLY", "status": "draft_requires_local_review",
        "production_approved": False, "layout_verified": False,
        "input_sha256": hashes, "output_sha256": hashlib.sha256(output).hexdigest(), "facts": facts,
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
    args = parser.parse_args(argv)
    try:
        generate_report(args.excel, args.template, args.mapping, args.output)
        print("Vertraulicher Berichtsentwurf mit Quellennachweis erstellt. Layout und Fachinhalt lokal prüfen.")
        return 0
    except ProjectError:
        print("Berichtserstellung gestoppt. Quellen, Zuordnung und Vorlage lokal prüfen.", file=sys.stderr)
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
