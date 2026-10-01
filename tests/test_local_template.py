"""Picture support stays local and rejects dangling or external references."""

import io
from zipfile import ZipFile

import pytest
from docx import Document
from lxml import etree
from PIL import Image

from pseudokrat.ki_office import ProjectError, read_local_template, read_office
from pseudokrat.local_inventory import inspect_documents


@pytest.fixture
def picture_template(tmp_path):
    image = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(image, format="PNG")
    doc = Document()
    doc.add_picture(io.BytesIO(image.getvalue()))
    path = tmp_path / "template.docx"
    doc.save(path)
    return path


def test_inventory_recognizes_local_images_without_privacy_approval(picture_template):
    report = inspect_documents([picture_template])
    assert report["files"][0]["status"] == "inspected"
    assert report["files"][0]["embedded_image_count"] == 1
    assert report["files"][0]["image_contents_reviewed"] is False
    assert report["production_approved"] is False
    with pytest.raises(ProjectError):
        read_office(picture_template)


@pytest.mark.parametrize("damage", ["missing", "external", "duplicate_id", "drawing_type", "signature"])
def test_invalid_local_picture_blocks_template(picture_template, damage):
    with ZipFile(picture_template) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    image_name = next(name for name in parts if name.startswith("word/media/"))
    if damage == "missing":
        del parts[image_name]
    elif damage == "signature":
        parts[image_name] = b"not a picture"
    elif damage == "drawing_type":
        parts["word/document.xml"] = parts["word/document.xml"].replace(b"/drawingml/2006/picture", b"/drawingml/2006/chart")
    else:
        key = "word/_rels/document.xml.rels"
        root = etree.fromstring(parts[key])
        rel = next(r for r in root if r.get("Type", "").endswith("/image"))
        if damage == "external":
            rel.set("TargetMode", "External")
            rel.set("Target", "https://example.invalid/picture.png")
        else:
            rel.set("Id", root[0].get("Id"))
        parts[key] = etree.tostring(root)
    with ZipFile(picture_template, "w") as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    with pytest.raises(ProjectError):
        read_local_template(picture_template)
