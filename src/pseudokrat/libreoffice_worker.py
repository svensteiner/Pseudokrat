"""Internal worker launched with system Python that provides the UNO bindings."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any


def run(folder: Path) -> None:
    """Read only the parent's validated copy in an isolated temporary profile."""
    import uno

    def prop(name: str, value: Any) -> Any:
        item = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
        item.Name, item.Value = name, value
        return item

    pipe = "pseudokrat_" + uuid.uuid4().hex
    command = ["/usr/bin/libreoffice", "-env:UserInstallation=" + (folder / "profile").as_uri(),
               "--headless", "--norestore", "--nodefault", "--nofirststartwizard",
               "--accept=pipe,name=" + pipe + ";urp;StarOffice.ComponentContext"]
    # No new session here: the parent owns and kills our entire process group.
    office = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    document = None
    try:
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
        context = None
        for _ in range(100):
            try:
                context = resolver.resolve("uno:pipe,name=" + pipe + ";urp;StarOffice.ComponentContext")
                break
            except Exception:
                if office.poll() is not None:
                    raise RuntimeError("Office startup failed") from None
                time.sleep(0.1)
        if context is None:
            raise RuntimeError("Office startup timed out")
        manager = context.ServiceManager
        desktop = manager.createInstanceWithContext("com.sun.star.frame.Desktop", context)
        document = desktop.loadComponentFromURL((folder / "input.xlsx").as_uri(), "_blank", 0,
            (prop("Hidden", True), prop("ReadOnly", True), prop("MacroExecutionMode", 0), prop("UpdateDocMode", 0)))
        if document is None:
            raise RuntimeError("No document")
        requests = json.loads((folder / "request.json").read_text("utf-8"))
        document.enableAutomaticCalculation(False)
        # Calc's exposed numeric result type loses the logical distinction
        # when a user overrides the cell's number format. Check the expression
        # inside Calc before accepting a value. The parent rejects volatile
        # functions: both evaluations must see the same deterministic inputs.
        for name, addresses in requests.items():
            sheet = document.Sheets.getByName(name)
            for address in addresses:
                cell = sheet.getCellRangeByName(address)
                expression = cell.getFormula()
                if not expression.startswith("="):
                    raise RuntimeError("Missing formula")
                cell.setFormula(f"=IF(ISLOGICAL(({expression[1:]}));NA();({expression[1:]}))")
        document.calculateAll()
        cells = {}
        for name, addresses in requests.items():
            sheet = document.Sheets.getByName(name)
            values = {}
            for address in addresses:
                cell = sheet.getCellRangeByName(address)
                if cell.getError() != 0:
                    raise RuntimeError("Formula error")
                kind = cell.getPropertyValue("FormulaResultType2")
                if kind == 2:
                    value = cell.getString()
                elif kind == 1:
                    value = cell.getValue()
                else:
                    raise RuntimeError("Unsupported result")
                values[address] = {"value": value}
            cells[name] = values
        provider = manager.createInstanceWithContext("com.sun.star.configuration.ConfigurationProvider", context)
        config = provider.createInstanceWithArguments("com.sun.star.configuration.ConfigurationAccess",
                   (prop("nodepath", "/org.openoffice.Setup/Product"),))
        result = {"engine": "LibreOffice Calc", "version": config.getPropertyValue("ooSetupVersionAboutBox"), "cells": cells}
        (folder / "result.json").write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
    finally:
        if document is not None:
            document.close(True)
        office.terminate()


if __name__ == "__main__":
    try:
        run(Path(sys.argv[1]).resolve())
    except Exception:
        # Native parser/UNO exceptions may contain original cell content.
        sys.exit(20)
