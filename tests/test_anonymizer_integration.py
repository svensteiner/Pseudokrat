"""End-to-End-Tests: Sektion 12 (kritische Test-Cases) des Megaprompts."""

from __future__ import annotations

from pathlib import Path

from pseudokrat.anonymizer import Anonymizer
from pseudokrat.deanonymizer import Deanonymizer
from pseudokrat.recognizers import default_recognizers
from pseudokrat.recognizers.base import Span
from pseudokrat.store.audit_log import AuditLog
from pseudokrat.store.mapping_store import MappingStore


def _make(tmp_path: Path) -> tuple[MappingStore, AuditLog]:
    store = MappingStore(tmp_path / "p.sqlite", password="pw")
    return store, AuditLog(store.connection)


def test_case_2_iban_replaced_amount_untouched(tmp_path: Path) -> None:
    store, log = _make(tmp_path)
    try:
        anon = Anonymizer(store, default_recognizers(), audit_log=log)
        text = "AT611904300234573201 — bitte überweise 4.300 €."
        result = anon.anonymize(text)
        assert "<IBAN_001>" in result.text
        assert "4.300 €" in result.text
        assert result.entity_counts.get("IBAN") == 1
    finally:
        store.close()


def test_case_3_uid_and_company(tmp_path: Path) -> None:
    store, log = _make(tmp_path)
    try:
        anon = Anonymizer(store, default_recognizers(), audit_log=log)
        text = "ATU12345675 ist die UID der Hofer Bau GmbH."
        result = anon.anonymize(text)
        assert "<UID_001>" in result.text
        assert "<COMPANY_001>" in result.text
    finally:
        store.close()


def test_case_4_fuzzy_merge_company(tmp_path: Path) -> None:
    """Drei Schreibweisen → ein gemeinsames Pseudonym."""
    store, log = _make(tmp_path)
    try:
        anon = Anonymizer(store, default_recognizers(), audit_log=log)
        text = (
            "Hofer Bau GmbH und Hofer-Bau GmbH sind dieselbe Firma. "
            "Auch hofer bau GmbH ist gemeint."
        )
        result = anon.anonymize(text)
        # Genau ein eindeutiger Platzhalter in der Ausgabe
        assert result.text.count("<COMPANY_001>") == 3
        assert "<COMPANY_002>" not in result.text
    finally:
        store.close()


def test_case_5_different_legal_forms_stay_separate(tmp_path: Path) -> None:
    store, log = _make(tmp_path)
    try:
        anon = Anonymizer(store, default_recognizers(), audit_log=log)
        text = "Hofer Bau GmbH ist nicht die Hofer Bau GmbH & Co. KG."
        result = anon.anonymize(text)
        assert "<COMPANY_001>" in result.text
        assert "<COMPANY_002>" in result.text
    finally:
        store.close()


def test_case_6_reverse_round_trip(tmp_path: Path) -> None:
    """Anonymisieren → Deanonymisieren → Original-Text (für rein-DACH-Spans)."""
    store, log = _make(tmp_path)
    try:
        anon = Anonymizer(store, default_recognizers(), audit_log=log)
        deanon = Deanonymizer(store, audit_log=log)
        text = "Die Hofer Bau GmbH (UID ATU12345675) hat IBAN AT611904300234573201."
        anonymized = anon.anonymize(text)
        restored = deanon.deanonymize(anonymized.text)
        assert restored.text == text
        assert restored.missing_placeholders == []
    finally:
        store.close()


def test_audit_chain_integration(tmp_path: Path) -> None:
    """Audit-Log baut Hash-Kette automatisch auf."""
    store, log = _make(tmp_path)
    try:
        anon = Anonymizer(store, default_recognizers(), audit_log=log)
        anon.anonymize("Hofer Bau GmbH ist Mandant.")
        anon.anonymize("Schreiben an Hofer Bau GmbH versandt.")
        assert log.verify_chain()
        entries = log.all_entries()
        assert len(entries) == 2
        assert entries[0].this_hash == entries[1].prev_hash
    finally:
        store.close()


def test_overlap_resolution_keeps_longer_span(tmp_path: Path) -> None:
    """Wenn IBAN-Recognizer und ML-Stub einen Span doppeln, gewinnt der längere."""
    from pseudokrat.anonymizer import _resolve_overlaps

    spans = [
        Span(start=0, end=10, category="A", text="0123456789", score=0.5),
        Span(start=2, end=8, category="B", text="234567", score=0.9),
    ]
    resolved = _resolve_overlaps(spans)
    assert len(resolved) == 1
    assert resolved[0].end - resolved[0].start == 10
