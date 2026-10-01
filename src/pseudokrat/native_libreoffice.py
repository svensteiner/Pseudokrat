"""Experimental Linux calculation using a private LibreOffice/UNO worker."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import signal
import subprocess
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

from openpyxl.formula.tokenizer import Tokenizer

from pseudokrat.ki_office import MAX_BYTES, ProjectError, S, write_office
from pseudokrat.native_excel import _validated


def recalculate(path: Path, *, timeout: int = 120) -> dict[str, Any]:
    """Rebuild a validated XLSX copy; return confidential values, never approval."""
    try:
        if platform.system() != "Linux" or type(timeout) is not int or not 1 <= timeout <= 600:
            raise ProjectError(
                "LibreOffice-Neuberechnung benötigt Linux und ein gültiges Zeitlimit."
            )
        if path.suffix.lower() != ".xlsx":
            raise ProjectError("Neuberechnung unterstützt nur XLSX-Dateien.")
        with path.open("rb") as handle:
            snapshot = handle.read(MAX_BYTES + 1)
        if len(snapshot) > MAX_BYTES:
            raise ProjectError("Datei überschreitet die unterstützte Größenbegrenzung.")
        digest = hashlib.sha256(snapshot).hexdigest()
        with tempfile.TemporaryDirectory(prefix="pseudokrat-lo-") as temporary:
            folder = Path(temporary)
            source = folder / "source.xlsx"
            source.write_bytes(snapshot)
            roots, requests = _validated(source)
            if any(
                cell.get("t") == "b" for root in roots.values() for cell in root.iter(f"{{{S}}}c")
            ):
                raise ProjectError(
                    "Boolesche Quellzellen benötigen gesonderte Typunterstützung in LibreOffice."
                )
            volatile = {"RAND", "RANDBETWEEN", "RANDARRAY", "NOW", "TODAY", "CELL", "INFO"}
            for root in roots.values():
                for element in root.iter():
                    if element.tag in {
                        f"{{{S}}}{tag}"
                        for tag in ("f", "formula", "formula1", "formula2", "definedName")
                    }:
                        tokens = Tokenizer("=" + (element.text or "").lstrip("=")).items
                        if any(
                            t.type == "FUNC"
                            and t.subtype == "OPEN"
                            and t.value[:-1].upper().split(".")[-1] in volatile
                            for t in tokens
                        ):
                            raise ProjectError(
                                "Volatile Formeln benötigen gesonderte Unterstützung in LibreOffice."
                            )
            source.unlink()
            (folder / "input.xlsx").write_bytes(write_office(roots))
            (folder / "request.json").write_text(json.dumps(requests), encoding="utf-8")
            command = [
                "/usr/bin/python3",
                str(Path(__file__).with_name("libreoffice_worker.py")),
                str(folder),
            ]
            # Both worker and soffice inherit this new session/process group.
            # Never signal an existing LibreOffice session or a process by name.
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
                raise ProjectError(
                    "LibreOffice-Neuberechnung fehlgeschlagen; keine Werte freigegeben."
                )
            output = folder / "result.json"
            if output.stat().st_size > MAX_BYTES:
                raise ProjectError("Berechnungsergebnis überschreitet die Begrenzung.")
            result: dict[str, Any] = json.loads(output.read_text("utf-8"))
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ProjectError("Excel-Quelle hat sich während der Berechnung verändert.")
        if result.get("engine") != "LibreOffice Calc" or not isinstance(result.get("version"), str):
            raise ProjectError("Unvollständiger Berechnungsnachweis.")
        if set(result.get("cells", {})) != set(requests):
            raise ProjectError("Unvollständiger Berechnungsnachweis.")
        for sheet, addresses in requests.items():
            if set(result["cells"][sheet]) != set(addresses):
                raise ProjectError("Unvollständiger Berechnungsnachweis.")
            for cell in result["cells"][sheet].values():
                if not isinstance(cell, dict) or set(cell) != {"value"}:
                    raise ProjectError("Ungültiges Berechnungsergebnis.")
                value = cell["value"]
                if type(value) not in {str, int, float} or value == "":
                    raise ProjectError("Ungültiges Berechnungsergebnis.")
                if type(value) is float and not math.isfinite(value):
                    raise ProjectError("Ungültiges Berechnungsergebnis.")
        result["source_sha256"] = digest
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
        raise ProjectError(
            "Lokale LibreOffice-Neuberechnung konnte nicht abgeschlossen werden."
        ) from exc
