"""Tests für den Audit-Log mit Hash-Kette."""

from __future__ import annotations

from pathlib import Path

from pseudokrat.store.audit_log import GENESIS_HASH, AuditLog
from pseudokrat.store.mapping_store import MappingStore


def _new_audit_log(tmp_path: Path) -> tuple[MappingStore, AuditLog]:
    db = tmp_path / "p.sqlite"
    store = MappingStore(db, password="pw")
    return store, AuditLog(store.connection)


def test_first_entry_uses_genesis_hash(tmp_path: Path) -> None:
    store, log = _new_audit_log(tmp_path)
    try:
        entry = log.append(
            operation="anonymize",
            entity_counts={"PERSON": 1},
            anonymized_text="hello <PERSON_001>",
            model_version="m",
            recognizer_version="r",
        )
        assert entry.prev_hash == GENESIS_HASH
        assert entry.this_hash != GENESIS_HASH
    finally:
        store.close()


def test_chain_links_entries(tmp_path: Path) -> None:
    store, log = _new_audit_log(tmp_path)
    try:
        e1 = log.append(
            operation="anonymize",
            entity_counts={"PERSON": 1},
            anonymized_text="x",
            model_version="m",
            recognizer_version="r",
        )
        e2 = log.append(
            operation="deanonymize",
            entity_counts={"PERSON": 1},
            anonymized_text="y",
            model_version="m",
            recognizer_version="r",
        )
        assert e2.prev_hash == e1.this_hash
        assert log.verify_chain()
    finally:
        store.close()


def test_verify_detects_tampering(tmp_path: Path) -> None:
    store, log = _new_audit_log(tmp_path)
    try:
        log.append(
            operation="anonymize",
            entity_counts={"PERSON": 1},
            anonymized_text="x",
            model_version="m",
            recognizer_version="r",
        )
        log.append(
            operation="anonymize",
            entity_counts={"PERSON": 2},
            anonymized_text="y",
            model_version="m",
            recognizer_version="r",
        )
        store.connection.execute(
            "UPDATE audit_log SET entity_counts_json = ? WHERE id = 1",
            ('{"PERSON":99}',),
        )
        store.connection.commit()
        assert not log.verify_chain()
    finally:
        store.close()


def test_export_csv_contains_entries(tmp_path: Path) -> None:
    store, log = _new_audit_log(tmp_path)
    try:
        log.append(
            operation="anonymize",
            entity_counts={"PERSON": 1},
            anonymized_text="x",
            model_version="m",
            recognizer_version="r",
        )
        csv_data = log.export_csv()
        assert "anonymize" in csv_data
        assert "PERSON" in csv_data
    finally:
        store.close()
