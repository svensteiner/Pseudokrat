"""The installation probe exercises real native engines when explicitly enabled."""

import hashlib
import json
import os
import sys

import pytest
from reportlab.pdfgen.canvas import Canvas

from pseudokrat import report_mapping, spark_smoke
from pseudokrat.ki_office import ProjectError
from pseudokrat.spark_smoke import run_smoke


@pytest.mark.parametrize("fault", [None, "calculation", "pages", "footer"])
def test_probe_checks_results_independently_of_native_engines(tmp_path, monkeypatch, fault):
    """Fault injection checks the probe, not native engine compatibility."""
    monkeypatch.setattr(spark_smoke.platform, "system", lambda: "Linux")

    def calculate(path):
        return {
            "engine": "synthetic-test-double",
            "version": "test",
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "cells": {
                "Daten": {
                    "B2": {"value": 99 if fault == "calculation" else 24.69},
                    "B3": {"value": -24.69},
                }
            },
        }

    def preview(source, destination):
        destination.mkdir()
        canvas = Canvas(str(destination / "preview.pdf"))
        for index in range(64 if fault == "pages" else 65):
            canvas.drawString(50, 50, "wrong" if fault == "footer" else f"Seite {index + 1} von 65")
            canvas.showPage()
        canvas.save()
        return destination

    monkeypatch.setattr(report_mapping, "recalculate_with_libreoffice", calculate)
    monkeypatch.setattr(spark_smoke, "render_preview", preview)
    output = tmp_path / "smoke"
    if fault:
        with pytest.raises(ProjectError):
            run_smoke(output)
    else:
        run_smoke(output)
    evidence = json.loads((output / "smoke.json").read_text())
    assert evidence["status"] == ("failed" if fault else "passed")
    assert evidence["production_approved"] is False
    assert evidence["checks"]["inputs_unchanged"] is True
    if fault:
        check = {"calculation": "table", "pages": "pages", "footer": "page_fields"}[fault]
        assert evidence["checks"][check] is False


@pytest.mark.skipif(
    sys.platform != "linux" or os.environ.get("PSEUDOKRAT_TEST_LIBREOFFICE") != "1",
    reason="Explicit Linux native opt-in",
)
def test_synthetic_installation_probe(tmp_path):
    output = run_smoke(tmp_path / "smoke")
    evidence = json.loads((output / "smoke.json").read_text())
    assert evidence["status"] == "passed"
    assert evidence["synthetic_only"] is True
    assert evidence["production_approved"] is False
    assert all(evidence["checks"].values())
    original = (output / "smoke.json").read_bytes()
    with pytest.raises(ProjectError):
        run_smoke(output)
    assert (output / "smoke.json").read_bytes() == original
