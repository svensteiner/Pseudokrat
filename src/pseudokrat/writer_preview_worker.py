"""Internal isolated UNO worker for a confidential PDF preview."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any


def run(folder: Path) -> None:
    import uno

    def prop(name: str, value: Any) -> Any:
        item = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
        item.Name, item.Value = name, value
        return item

    pipe = "pseudokrat_writer_" + uuid.uuid4().hex
    office = subprocess.Popen(["/usr/bin/libreoffice", "-env:UserInstallation=" + (folder / "profile").as_uri(),
        "--headless", "--norestore", "--nodefault", "--nofirststartwizard",
        "--accept=pipe,name=" + pipe + ";urp;StarOffice.ComponentContext"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        document = desktop.loadComponentFromURL((folder / "input.docx").as_uri(), "_blank", 0,
            (prop("Hidden", True), prop("ReadOnly", True), prop("MacroExecutionMode", 0), prop("UpdateDocMode", 0)))
        if document is None or not document.supportsService("com.sun.star.text.TextDocument"):
            raise RuntimeError("No Writer document")
        document.reformat()
        document.getTextFields().refresh()
        document.reformat()
        document.storeToURL((folder / "preview.pdf").as_uri(),
            (prop("FilterName", "writer_pdf_Export"), prop("Overwrite", False),
             prop("FilterData", (prop("ExportFormFields", False), prop("ExportBookmarks", False)))))
        provider = manager.createInstanceWithContext("com.sun.star.configuration.ConfigurationProvider", context)
        config = provider.createInstanceWithArguments("com.sun.star.configuration.ConfigurationAccess",
            (prop("nodepath", "/org.openoffice.Setup/Product"),))
        (folder / "engine.json").write_text(json.dumps({"engine": "LibreOffice Writer",
            "version": config.getPropertyValue("ooSetupVersionAboutBox")}), encoding="utf-8")
    finally:
        if document is not None:
            document.close(True)
        office.terminate()


if __name__ == "__main__":
    try:
        run(Path(sys.argv[1]).resolve())
    except Exception:
        sys.exit(20)
