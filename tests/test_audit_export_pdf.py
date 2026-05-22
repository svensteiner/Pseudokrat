"""Tests für PDF-Export des Audit-Logs (reportlab)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pseudokrat.cli import main
from pseudokrat.store.audit_log import AuditLog
from pseudokrat.store.mapping_store import MappingStore
from tests.conftest import TEST_PASSWORD


def _new_audit_log(tmp_path: Path) -> tuple[MappingStore, AuditLog]:
    db = tmp_path / "p.sqlite"
    store = MappingStore(db, password="pw")
    return store, AuditLog(store.connection)


def _extract_text(path: Path) -> str:
    from pypdf import PdfReader

    return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)


def test_audit_export_pdf_writes_file(tmp_path: Path) -> None:
    store, audit = _new_audit_log(tmp_path)
    try:
        audit.append(
            operation="anonymize",
            entity_counts={"COMPANY": 1, "IBAN": 1},
            anonymized_text="<COMPANY_001> sendet <IBAN_001>",
            model_version="disabled",
            recognizer_version="r1",
        )
        audit.append(
            operation="deanonymize",
            entity_counts={"COMPANY": 1},
            anonymized_text="<COMPANY_001> war hier",
            model_version="disabled",
            recognizer_version="r1",
        )
        out = tmp_path / "audit.pdf"
        audit.export_pdf(out, profile_name="Mandant Hofer")

        assert out.exists()
        assert out.stat().st_size > 0
        text = _extract_text(out)
        assert "Pseudokrat" in text
        assert "Mandant Hofer" in text
        assert "anonymize" in text
        assert "deanonymize" in text
        assert "Hash-Kette" in text
    finally:
        store.close()


def test_audit_export_pdf_empty_log_still_valid(tmp_path: Path) -> None:
    store, audit = _new_audit_log(tmp_path)
    try:
        out = tmp_path / "empty.pdf"
        audit.export_pdf(out)
        assert out.exists()
        text = _extract_text(out)
        assert "Pseudokrat" in text
    finally:
        store.close()


def test_audit_export_pdf_detects_tampering(tmp_path: Path) -> None:
    store, audit = _new_audit_log(tmp_path)
    try:
        audit.append(
            operation="anonymize",
            entity_counts={"X": 1},
            anonymized_text="<X_001>",
            model_version="disabled",
            recognizer_version="r1",
        )
        store.connection.execute(
            "UPDATE audit_log SET entity_counts_json = ? WHERE id = 1",
            ('{"X":99}',),
        )
        store.connection.commit()
        out = tmp_path / "tampered.pdf"
        audit.export_pdf(out)
        text = _extract_text(out)
        assert "MANIPULATION" in text
    finally:
        store.close()


def test_audit_export_pdf_via_cli(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    del data_dir  # PSEUDOKRAT_DATA_DIR ist bereits gesetzt.
    monkeypatch.setenv("PSEUDOKRAT_PASSWORD", TEST_PASSWORD)

    rc = main(["anonymize", "--profile", "audit-pdf", "--text", "Mandant Hofer Bau GmbH"])
    assert rc == 0

    out = tmp_path / "out.pdf"
    rc = main(["audit", "--profile", "audit-pdf", "export", "--format", "pdf", "-o", str(out)])
    assert rc == 0
    assert out.exists()
    text = _extract_text(out)
    assert "audit-pdf" in text
    assert "anonymize" in text


def test_audit_export_pdf_requires_output(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    del data_dir
    monkeypatch.setenv("PSEUDOKRAT_PASSWORD", TEST_PASSWORD)

    rc = main(["anonymize", "--profile", "audit-pdf2", "--text", "x"])
    assert rc == 0
    rc = main(["audit", "--profile", "audit-pdf2", "export", "--format", "pdf"])
    assert rc == 6
    err = capsys.readouterr().err
    assert "--output" in err


def test_audit_csv_export_unchanged(tmp_path: Path) -> None:
    store, audit = _new_audit_log(tmp_path)
    try:
        audit.append(
            operation="anonymize",
            entity_counts={"X": 1},
            anonymized_text="<X_001>",
            model_version="disabled",
            recognizer_version="r1",
        )
        csv_text = audit.export_csv()
        assert csv_text.startswith("id,timestamp_utc,operation,")
        assert "anonymize" in csv_text
    finally:
        store.close()
