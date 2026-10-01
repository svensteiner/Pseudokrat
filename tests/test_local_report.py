"""First complete local Excel-to-Word journey, including split runs and tables."""

import hashlib
import io
import json
import os
from zipfile import ZipFile

import pytest
from docx import Document
from openpyxl import Workbook, load_workbook
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from pseudokrat.ki_office import ProjectError, read_office
from pseudokrat.local_report import generate_report, main


@pytest.mark.parametrize("engine,flag", [
    pytest.param("Microsoft Excel", "recalculate_excel", marks=pytest.mark.skipif(os.environ.get("PSEUDOKRAT_TEST_EXCEL") != "1", reason="Explicit Excel opt-in")),
    pytest.param("LibreOffice Calc", "recalculate_libreoffice", marks=pytest.mark.skipif(os.environ.get("PSEUDOKRAT_TEST_LIBREOFFICE") != "1", reason="Explicit LibreOffice opt-in")),
])
def test_real_recalculation_reaches_word_with_provenance(tmp_path, report_inputs, engine, flag):
    excel, template, mapping = report_inputs
    book = load_workbook(excel)
    book.active["B2"] = "=ROUND(12.345*2,2)"
    book.save(excel)
    originals = [p.read_bytes() for p in report_inputs]
    with pytest.raises(ProjectError):
        generate_report(excel, template, mapping, tmp_path / "blocked")
    assert not (tmp_path / "blocked").exists()
    output = generate_report(excel, template, mapping, tmp_path / "calculated", **{flag: True})
    assert Document(output / "bericht.docx").tables[0].cell(0, 1).text == "24,69 EUR"
    evidence = json.loads((output / "nachweis.json").read_text("utf-8"))
    calc = evidence["facts"]["amount"]["calculation"]
    assert calc["engine"] == engine
    assert calc["source_sha256"] == hashlib.sha256(excel.read_bytes()).hexdigest()
    assert calc["formulas"]["B2"] == {"formula": "=ROUND(12.345*2,2)", "value": "24.69"}
    assert evidence["production_approved"] is False
    assert [p.read_bytes() for p in report_inputs] == originals


def test_conflicting_engines_never_create_report(tmp_path, report_inputs):
    with pytest.raises(ProjectError):
        generate_report(*report_inputs, tmp_path / "blocked", recalculate_excel=True, recalculate_libreoffice=True)
    assert not (tmp_path / "blocked").exists()


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
def test_local_report_preserves_logo_and_keeps_export_parser_strict(tmp_path, report_inputs, image_format):
    excel, template, mapping = report_inputs
    image = io.BytesIO()
    metadata = PngInfo()
    metadata.add_text("Author", "SyntheticPrivateArtist")
    Image.new("RGB", (8, 8), "blue").save(image, format=image_format, **({"pnginfo": metadata} if image_format == "PNG" else {}))
    original_image = image.getvalue()
    doc = Document(template)
    doc.add_picture(io.BytesIO(original_image))
    doc.sections[0].header.paragraphs[0].add_run().add_picture(io.BytesIO(original_image))
    doc.save(template)
    spec = json.loads(mapping.read_text("utf-8"))
    spec["template_sha256"] = hashlib.sha256(template.read_bytes()).hexdigest()
    mapping.write_text(json.dumps(spec), encoding="utf-8")
    original_template = template.read_bytes()
    with pytest.raises(ProjectError):
        read_office(template)
    output = generate_report(excel, template, mapping, tmp_path / "result")
    doc = Document(output / "bericht.docx")
    assert len(doc.inline_shapes) == 1
    assert doc.tables[0].cell(0, 1).text == "123,45 EUR"
    with ZipFile(output / "bericht.docx") as archive:
        pictures = {name: archive.read(name) for name in archive.namelist() if name.startswith("word/media/")}
    assert list(pictures.values()) == [original_image]
    evidence = json.loads((output / "nachweis.json").read_text("utf-8"))
    assert evidence["embedded_media_sha256"] == {name: hashlib.sha256(data).hexdigest() for name, data in pictures.items()}
    assert template.read_bytes() == original_template
    with pytest.raises(ProjectError):
        read_office(output / "bericht.docx")


def test_dynamic_table_images_receive_unique_ids(tmp_path, report_inputs):
    excel, template, mapping = report_inputs
    book = load_workbook(excel)
    book.active["A3"] = "Zweiter Testfall"
    book.save(excel)
    picture = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(picture, format="PNG")
    doc = Document(template)
    cell = doc.add_table(rows=1, cols=1).cell(0, 0)
    cell.text = "{{ rows.name }}"
    cell.paragraphs[0].add_run().add_picture(io.BytesIO(picture.getvalue()))
    doc.save(template)
    spec = json.loads(mapping.read_text("utf-8"))
    spec.update({"version": 2, "template_sha256": hashlib.sha256(template.read_bytes()).hexdigest(),
                 "tables": {"rows": {"sheet": "Daten", "first_row": 2, "last_row": 3,
                                     "columns": {"name": {"column": "A", "format": "text"}}}}})
    mapping.write_text(json.dumps(spec), encoding="utf-8")
    output = generate_report(excel, template, mapping, tmp_path / "result")
    result = Document(output / "bericht.docx")
    assert len(result.inline_shapes) == 2
    ids = [shape._inline.docPr.id for shape in result.inline_shapes]
    assert len(set(ids)) == 2
    assert [row.cells[0].text for row in result.tables[1].rows] == ["Originalname", "Zweiter Testfall"]


@pytest.mark.skipif(os.environ.get("PSEUDOKRAT_TEST_LIBREOFFICE") != "1", reason="Explicit LibreOffice opt-in")
def test_linux_formulas_tables_and_narratives_in_large_report(tmp_path, report_inputs):
    excel, template, mapping = report_inputs
    book = load_workbook(excel)
    book.active["B2"] = "=ROUND(12.345*2,2)"
    book.active["A3"] = "Zweiter Testfall"
    book.active["B3"] = "=-B2"
    book.save(excel)
    doc = Document()
    for index in range(65):
        if index:
            doc.add_page_break()
        doc.add_heading(f"Abschnitt {index + 1}", level=1)
        doc.add_paragraph("{{ assessment }}")
    row = doc.add_table(rows=1, cols=2).rows[0]
    row.cells[0].text = "{{ rows.name }}"
    row.cells[1].text = "{{ rows.amount }} EUR"
    doc.save(template)
    spec = json.loads(mapping.read_text("utf-8"))
    spec["fields"]["amount"].update({"range": "B2:B3", "operation": "sum"})
    spec.update({"version": 3, "template_sha256": hashlib.sha256(template.read_bytes()).hexdigest(),
                 "narratives": {"assessment": {"template": "Für {{ name }} beträgt der Gesamtsaldo {{ amount }} EUR."}},
                 "tables": {"rows": {"sheet": "Daten", "first_row": 2, "last_row": 3,
                     "columns": {"name": {"column": "A", "format": "text"},
                                 "amount": {"column": "B", "format": "decimal", "decimals": 2}}}}})
    mapping.write_text(json.dumps(spec), encoding="utf-8")
    originals = [path.read_bytes() for path in report_inputs]
    output = generate_report(excel, template, mapping, tmp_path / "result", recalculate_libreoffice=True)
    result = Document(output / "bericht.docx")
    assert sum(p.text == "Für Originalname beträgt der Gesamtsaldo 0,00 EUR." for p in result.paragraphs) == 65
    assert [row.cells[1].text for row in result.tables[0].rows] == ["24,69 EUR", "-24,69 EUR"]
    evidence = json.loads((output / "nachweis.json").read_text("utf-8"))
    assert evidence["tables"]["rows"][1]["amount"]["calculation"]["engine"] == "LibreOffice Calc"
    assert evidence["narratives"]["assessment"]["inputs"] == ["amount", "name"]
    assert [path.read_bytes() for path in report_inputs] == originals


def test_failed_recalculation_never_creates_report(tmp_path, report_inputs, monkeypatch):
    excel, template, mapping = report_inputs
    book = load_workbook(excel)
    book.active["B2"] = "=1+2"
    book.save(excel)

    def failed(*args, **kwargs):
        raise ProjectError("Calculation unavailable")

    monkeypatch.setattr("pseudokrat.report_mapping.recalculate", failed)
    with pytest.raises(ProjectError):
        generate_report(excel, template, mapping, tmp_path / "blocked", recalculate_excel=True)
    assert not (tmp_path / "blocked").exists()


@pytest.mark.parametrize("value,changed_hash", [(True, False), ("3", False), (3, True)])
def test_invalid_calculated_number_or_binding_stops_report(tmp_path, report_inputs, monkeypatch, value, changed_hash):
    excel, template, mapping = report_inputs
    book = load_workbook(excel)
    book.active["B2"] = "=1+2"
    book.save(excel)
    digest = "0" * 64 if changed_hash else hashlib.sha256(excel.read_bytes()).hexdigest()
    monkeypatch.setattr("pseudokrat.report_mapping.recalculate", lambda path: {
        "engine": "Microsoft Excel", "version": "test", "source_sha256": digest,
        "cells": {"Daten": {"B2": {"value": value}}},
    })
    with pytest.raises(ProjectError):
        generate_report(excel, template, mapping, tmp_path / "blocked", recalculate_excel=True)
    assert not (tmp_path / "blocked").exists()


def test_reviewed_narrative_uses_facts_without_separate_word_fields(tmp_path, report_inputs):
    excel, template, mapping = report_inputs
    doc = Document()
    doc.add_paragraph("{{ assessment }}")
    doc.save(template)
    spec = json.loads(mapping.read_text("utf-8"))
    spec.update({"version": 3, "template_sha256": hashlib.sha256(template.read_bytes()).hexdigest(),
                 "narratives": {"assessment": {"cases": [
                     {"field": "amount", "op": "gt", "value": "0", "template": "Für {{ name }} beträgt der positive Saldo {{ amount }} EUR."}
                 ], "otherwise": "Für {{ name }} beträgt der Saldo {{ amount }} EUR."}}})
    mapping.write_text(json.dumps(spec), encoding="utf-8")
    output = generate_report(excel, template, mapping, tmp_path / "result")
    assert Document(output / "bericht.docx").paragraphs[0].text == "Für Originalname beträgt der positive Saldo 123,45 EUR."
    evidence = json.loads((output / "nachweis.json").read_text("utf-8"))
    assert evidence["narratives"]["assessment"]["selected_branch"] == 0
    assert evidence["narratives"]["assessment"]["inputs"] == ["amount", "name"]
    assert evidence["facts"]["amount"]["source"]["range"] == "B2"
    assert evidence["production_approved"] is False


@pytest.fixture
def report_inputs(tmp_path):
    excel = tmp_path / "original.xlsx"
    book = Workbook()
    book.active.title = "Daten"
    book.active.append(["Name", "Betrag"])
    book.active.append(["Originalname", 123.45])
    book.save(excel)
    template = tmp_path / "template.docx"
    doc = Document()
    p = doc.add_paragraph("Bericht für ")
    p.add_run("{{ na").bold = True
    p.add_run("me }}")
    doc.add_table(rows=1, cols=2).cell(0, 1).text = "{{ amount }} EUR"
    doc.sections[0].header.paragraphs[0].text = "{{ name }}"
    doc.core_properties.author = "PrivateAuthor"
    doc.save(template)
    spec = {"version": 1, "reviewed": True, "template_sha256": hashlib.sha256(template.read_bytes()).hexdigest(),
            "headers": {"Daten": {"A1": "Name", "B1": "Betrag"}},
            "fields": {"name": {"sheet": "Daten", "range": "A2", "operation": "cell", "format": "text"},
                       "amount": {"sheet": "Daten", "range": "B2", "operation": "cell", "format": "decimal", "decimals": 2}}}
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps(spec), encoding="utf-8")
    return excel, template, mapping


def test_local_report_preserves_template_and_records_sources(tmp_path, report_inputs):
    excel, template, mapping = report_inputs
    before = [p.read_bytes() for p in report_inputs]
    output = generate_report(excel, template, mapping, tmp_path / "result")
    doc = Document(output / "bericht.docx")
    assert doc.paragraphs[0].text == "Bericht für Originalname"
    assert doc.tables[0].cell(0, 1).text == "123,45 EUR"
    assert doc.sections[0].header.paragraphs[0].text == "Originalname"
    provenance = json.loads((output / "nachweis.json").read_text("utf-8"))
    assert provenance["classification"] == "CONFIDENTIAL_LOCAL_ONLY"
    assert provenance["production_approved"] is False
    assert provenance["facts"]["amount"]["exact_value"] == "123.45"
    assert provenance["output_sha256"] == hashlib.sha256((output / "bericht.docx").read_bytes()).hexdigest()
    with ZipFile(output / "bericht.docx") as archive:
        assert not any(n.startswith("docProps/") for n in archive.namelist())
    assert [p.read_bytes() for p in report_inputs] == before
    with pytest.raises(ProjectError):
        generate_report(excel, template, mapping, output)


def test_missing_mapping_field_leaves_no_output(tmp_path, report_inputs):
    excel, template, mapping = report_inputs
    spec = json.loads(mapping.read_text("utf-8"))
    del spec["fields"]["amount"]
    mapping.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ProjectError):
        generate_report(excel, template, mapping, tmp_path / "result")
    assert not (tmp_path / "result").exists()


def test_cli_does_not_echo_original_values(tmp_path, report_inputs, capsys):
    excel, template, mapping = report_inputs
    assert main(["--excel", str(excel), "--template", str(template), "--mapping", str(mapping),
                 "--output", str(tmp_path / "result")]) == 0
    assert "Originalname" not in str(capsys.readouterr())


def test_sixty_five_section_report(tmp_path, report_inputs):
    excel, template, mapping = report_inputs
    doc = Document()
    for i in range(65):
        if i:
            doc.add_page_break()
        doc.add_heading(f"Abschnitt {i + 1}", level=1)
        doc.add_paragraph("Bericht für {{ name }}")
        doc.add_table(rows=1, cols=2).cell(0, 1).text = "{{ amount }} EUR"
    doc.save(template)
    spec = json.loads(mapping.read_text("utf-8"))
    spec["template_sha256"] = hashlib.sha256(template.read_bytes()).hexdigest()
    mapping.write_text(json.dumps(spec), encoding="utf-8")
    output = generate_report(excel, template, mapping, tmp_path / "result")
    result = Document(output / "bericht.docx")
    assert len(result.tables) == 65
    assert all(t.cell(0, 1).text == "123,45 EUR" for t in result.tables)
    assert sum(p.text == "Bericht für Originalname" for p in result.paragraphs) == 65
