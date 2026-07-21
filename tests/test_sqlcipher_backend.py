"""SQLCipher-Backend-Tests (opt-in über ``PSEUDOKRAT_USE_SQLCIPHER=1``).

Diese Suite prüft den SQLCipher-Pfad direkt: dass Schreibvorgänge das
Datei-Magic ändern, dass das Master-Passwort tatsächlich erforderlich ist,
und dass ein in SQLCipher angelegtes Profil von einem Fernet-Only-Open
NICHT versehentlich entschlüsselt werden kann.

Wird beim normalen ``pytest``-Lauf übersprungen, wenn sqlcipher3 nicht
installiert ist.
"""

from __future__ import annotations

from pathlib import Path

import pytest

sqlcipher3 = pytest.importorskip("sqlcipher3", reason="sqlcipher3 nicht installiert")

from pseudokrat.store.audit_log import AuditLog  # noqa: E402
from pseudokrat.store.mapping_store import MappingStore  # noqa: E402
from pseudokrat.store.secure_db import (  # noqa: E402
    SQLITE_MAGIC,
    InvalidPasswordError,
    _file_is_sqlcipher,
    open_or_init,
)


@pytest.fixture(autouse=True)
def _enable_sqlcipher(monkeypatch: pytest.MonkeyPatch) -> None:
    """Erzwingt SQLCipher für jeden Test in dieser Datei."""
    monkeypatch.setenv("PSEUDOKRAT_USE_SQLCIPHER", "1")


def test_new_profile_writes_sqlcipher_encrypted_file(tmp_path: Path) -> None:
    db = tmp_path / "sc.sqlite"
    conn, _keys = open_or_init(db, "supergeheim", profile_name="SC-Test")
    conn.execute("INSERT INTO profile_metadata (key, value) VALUES ('marker', 'x')")
    conn.commit()
    conn.close()

    # Datei-Magic darf NICHT der stdlib-SQLite-Header sein.
    assert db.read_bytes()[: len(SQLITE_MAGIC)] != SQLITE_MAGIC
    assert _file_is_sqlcipher(db) is True

    # Sidecar-Salt existiert.
    assert (tmp_path / "sc.sqlite.salt").exists()


def test_reopen_with_correct_password_returns_data(tmp_path: Path) -> None:
    db = tmp_path / "sc.sqlite"
    conn, _ = open_or_init(db, "supergeheim", profile_name="SC-Test")
    conn.execute("INSERT INTO profile_metadata (key, value) VALUES ('test_key', 'test_value')")
    conn.commit()
    conn.close()

    conn2, _ = open_or_init(db, "supergeheim")
    row = conn2.execute("SELECT value FROM profile_metadata WHERE key = 'test_key'").fetchone()
    assert row["value"] == "test_value"
    conn2.close()


def test_reopen_with_wrong_password_fails(tmp_path: Path) -> None:
    db = tmp_path / "sc.sqlite"
    conn, _ = open_or_init(db, "supergeheim")
    conn.close()

    with pytest.raises(InvalidPasswordError):
        open_or_init(db, "FALSCHES-PASSWORT")


def test_mapping_store_works_with_sqlcipher(tmp_path: Path) -> None:
    """Verifikation, dass die MappingStore-Schicht oben drauf weiterhin funktioniert."""
    db = tmp_path / "mp.sqlite"
    store = MappingStore(db, password="supergeheim", profile_name="SC-Mapping")
    try:
        m = store.get_or_create("Hofer Bau GmbH", "COMPANY")
        assert m.placeholder == "<COMPANY_001>"
        m2 = store.get_or_create("Hofer Bau GmbH", "COMPANY")
        assert m2.placeholder == "<COMPANY_001>"
    finally:
        store.close()


def test_audit_log_hash_chain_works_with_sqlcipher(tmp_path: Path) -> None:
    db = tmp_path / "audit.sqlite"
    store = MappingStore(db, password="supergeheim", profile_name="SC-Audit")
    try:
        audit = AuditLog(store.connection)
        audit.append(
            operation="anonymize",
            entity_counts={"COMPANY": 1},
            anonymized_text="<COMPANY_001> hat überwiesen.",
            model_version="model-x",
            recognizer_version="rec-y",
        )
        audit.append(
            operation="deanonymize",
            entity_counts={},
            anonymized_text="Hofer Bau GmbH hat überwiesen.",
            model_version="model-x",
            recognizer_version="rec-y",
        )
        assert audit.verify_chain() is True
    finally:
        store.close()


def test_existing_sqlcipher_db_opened_even_with_env_unset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ein einmal als SQLCipher angelegtes Profil bleibt SQLCipher.

    Auch wenn der Nutzer später ``PSEUDOKRAT_USE_SQLCIPHER`` auf 0 setzt,
    erkennt :func:`_file_is_sqlcipher` den existierenden Modus aus dem
    Datei-Magic und wählt automatisch den richtigen Pfad.
    """
    db = tmp_path / "persistent.sqlite"
    conn, _ = open_or_init(db, "supergeheim")
    conn.close()

    monkeypatch.setenv("PSEUDOKRAT_USE_SQLCIPHER", "0")
    conn2, _ = open_or_init(db, "supergeheim")
    # Wenn der Fall falsch erkannt wäre, würde sqlite3.connect den header
    # nicht parsen können — die folgende Query wäre dann ein Error.
    rows = conn2.execute("SELECT key FROM profile_metadata").fetchall()
    assert any(r["key"] == "profile_name" for r in rows)
    conn2.close()
