"""Render a local DOCX copy for human layout review; never approve automatically."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import signal
import subprocess
import sys
import tempfile
from contextlib import suppress
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from pseudokrat.ki_office import (
    MAX_BYTES,
    ProjectError,
    W,
    read_local_template,
    write_local_template,
)
from pseudokrat.word_fields import inspect_fields


def render_preview(source: Path, destination: Path, *, timeout: int = 120) -> Path:
    """Publish a confidential preview and evidence in a new output directory."""
    try:
        if platform.system() != "Linux" or type(timeout) is not int or not 1 <= timeout <= 600:
            raise ProjectError("PDF-Vorschau benötigt Linux und ein gültiges Zeitlimit.")
        destination = destination.resolve()
        if destination.exists() or source.suffix.lower() != ".docx":
            raise ProjectError("DOCX-Bericht und einen neuen Ausgabeordner verwenden.")
        with source.open("rb") as handle:
            snapshot = handle.read(MAX_BYTES + 1)
        if len(snapshot) > MAX_BYTES:
            raise ProjectError("Bericht überschreitet die Größenbegrenzung.")
        digest = hashlib.sha256(snapshot).hexdigest()
        with tempfile.TemporaryDirectory(prefix="pseudokrat-preview-") as directory:
            folder = Path(directory)
            original = folder / "source.docx"
            original.write_bytes(snapshot)
            roots, media = read_local_template(original)
            original.unlink()
            codes, _ = inspect_fields(roots)
            for root in roots.values():
                text = "".join(node.text or "" for node in root.iter(f"{{{W}}}t"))
                if "{{" in text or "}}" in text:
                    raise ProjectError("Bericht enthält noch nicht befüllte Platzhalter.")
            (folder / "input.docx").write_bytes(write_local_template(roots, media))
            command = [
                "/usr/bin/python3",
                str(Path(__file__).with_name("writer_preview_worker.py")),
                str(folder),
            ]
            with subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            ) as process:
                try:
                    code = process.wait(timeout=timeout)
                finally:
                    with suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGKILL)  # type: ignore[attr-defined]
                    process.wait(timeout=10)
            if code != 0:
                raise ProjectError("Lokale Vorschau konnte nicht gerendert werden.")
            pdf = folder / "preview.pdf"
            if pdf.stat().st_size > MAX_BYTES:
                raise ProjectError("PDF-Vorschau überschreitet die Größenbegrenzung.")
            payload = pdf.read_bytes()
            reader = PdfReader(io.BytesIO(payload), strict=True)
            if reader.is_encrypted or not 1 <= len(reader.pages) <= 5000:
                raise ProjectError("PDF-Vorschau ist nicht vollständig prüfbar.")
            engine = json.loads((folder / "engine.json").read_text("utf-8"))
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ProjectError("Bericht wurde während der Vorschauerstellung geändert.")
        if engine.get("engine") != "LibreOffice Writer" or not isinstance(
            engine.get("version"), str
        ):
            raise ProjectError("Rendering-Nachweis ist unvollständig.")
        evidence = {
            "classification": "CONFIDENTIAL_LOCAL_ONLY",
            "status": "requires_visual_review",
            "production_approved": False,
            "visual_reviewed": False,
            "source_docx_updated": False,
            "source_sha256": digest,
            "pdf_sha256": hashlib.sha256(payload).hexdigest(),
            "pages": len(reader.pages),
            "engine": engine,
            "pagination_fields": codes,
            "field_refresh_requested_in_preview": True,
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".pseudokrat-preview-", dir=destination.parent
        ) as staging:
            output = Path(staging) / "result"
            output.mkdir(mode=0o700)
            (output / "preview.pdf").write_bytes(payload)
            (output / "preview.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            for path in output.iterdir():
                path.chmod(0o600)
            if destination.exists():
                raise ProjectError("Ausgabeordner existiert bereits.")
            output.rename(destination)
        return destination
    except ProjectError:
        raise
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        PyPdfError,
        subprocess.SubprocessError,
    ) as exc:
        raise ProjectError("Lokale PDF-Vorschau konnte nicht sicher erstellt werden.") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Vertrauliche lokale PDF-Vorschau eines DOCX-Berichts."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        render_preview(args.input, args.output)
        print("Vertrauliche Vorschau erstellt. Layout lokal prüfen; keine Produktionsfreigabe.")
        return 0
    except ProjectError:
        print(
            "Vorschauerstellung gestoppt. Lokale Eingaben und Writer-Installation prüfen.",
            file=sys.stderr,
        )
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
