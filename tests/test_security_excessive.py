"""Security-Tests: Krypto, Hash-Chain-Tampering, Wrong-Password, PII-Leak.

Diese Tests sind das ergänzende, breitere Pendant zu den punktuellen
Krypto-Tests im Hauptbestand. Sie verifizieren explizit:

1. PBKDF2-Iterationen sind ≥ 256.000 (Brute-Force-Schutz).
2. Falsches Passwort öffnet keine bestehende DB.
3. Salt-Datei-Manipulation wird erkannt.
4. Audit-Log-Manipulation (Zeile gelöscht, Zeile geändert) → ``verify_chain() == False``.
5. Originaltexte erscheinen niemals im SQLite-File.
6. Logs auf Disk enthalten keine Original-PII.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from pseudokrat.anonymizer import Anonymizer
from pseudokrat.recognizers import default_recognizers
from pseudokrat.store.profile import ProfileManager
from pseudokrat.store.secure_db import (
    PBKDF2_ITERATIONS,
    InvalidPasswordError,
    derive_keys,
)


@pytest.fixture
def fresh_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Path, ProfileManager]]:
    data_dir = tmp_path / "pseudokrat-data"
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(data_dir))
    pm = ProfileManager()
    yield data_dir, pm


# --------------------------------------------------------------------------- #
# 1. PBKDF2-Iterationen                                                       #
# --------------------------------------------------------------------------- #


def test_pbkdf2_iterations_meet_security_baseline() -> None:
    """OWASP empfiehlt mindestens 600k PBKDF2-SHA256 oder ≥ 210k PBKDF2-SHA512.

    Wir verwenden SHA-512 und müssen mindestens 256.000 Iterationen einhalten
    (Megaprompt §10 Sicherheits-Anforderungen).
    """
    assert PBKDF2_ITERATIONS >= 256_000


def test_derive_keys_is_deterministic() -> None:
    salt = os.urandom(16)
    k1 = derive_keys("Test-Passw0rt", salt)
    k2 = derive_keys("Test-Passw0rt", salt)
    assert k1.fernet_key == k2.fernet_key
    assert k1.hmac_key == k2.hmac_key
    assert k1.sqlcipher_key_hex == k2.sqlcipher_key_hex


def test_derive_keys_different_passwords_produce_different_keys() -> None:
    salt = os.urandom(16)
    k1 = derive_keys("Passwort-A", salt)
    k2 = derive_keys("Passwort-B", salt)
    assert k1.fernet_key != k2.fernet_key
    assert k1.hmac_key != k2.hmac_key
    assert k1.sqlcipher_key_hex != k2.sqlcipher_key_hex


def test_derive_keys_different_salts_produce_different_keys() -> None:
    k1 = derive_keys("Same-Passwort", b"A" * 16)
    k2 = derive_keys("Same-Passwort", b"B" * 16)
    assert k1.fernet_key != k2.fernet_key


def test_derive_keys_rejects_wrong_salt_size() -> None:
    with pytest.raises(ValueError):
        derive_keys("p", b"too short")


# --------------------------------------------------------------------------- #
# 2. Wrong-Password                                                           #
# --------------------------------------------------------------------------- #


def test_wrong_password_raises_invalid(
    fresh_profile: tuple[Path, ProfileManager],
) -> None:
    _, pm = fresh_profile
    store, _ = pm.open_or_create("ws", "Rich-Passw0rt-123")
    store.close()

    with pytest.raises(InvalidPasswordError):
        pm.open_or_create("ws", "Falsch-Passw0rt-456")


def test_missing_salt_file_blocks_open(
    fresh_profile: tuple[Path, ProfileManager],
) -> None:
    data_dir, pm = fresh_profile
    store, _ = pm.open_or_create("salt", "Salt-Passw0rt")
    store.close()
    # Salt löschen
    salt_files = list(data_dir.rglob("*.salt"))
    assert salt_files
    for sf in salt_files:
        sf.unlink()
    with pytest.raises(InvalidPasswordError):
        pm.open_or_create("salt", "Salt-Passw0rt")


def test_tampered_salt_does_not_open(
    fresh_profile: tuple[Path, ProfileManager],
) -> None:
    data_dir, pm = fresh_profile
    store, _ = pm.open_or_create("ts", "T-Passw0rt")
    store.close()
    salt_files = list(data_dir.rglob("*.salt"))
    sf = salt_files[0]
    sf.write_bytes(b"X" * 16)  # andere Salt, gleiche Größe
    with pytest.raises(InvalidPasswordError):
        pm.open_or_create("ts", "T-Passw0rt")


# --------------------------------------------------------------------------- #
# 3. Audit-Log-Tampering                                                      #
# --------------------------------------------------------------------------- #


def test_audit_chain_detects_deleted_row(
    fresh_profile: tuple[Path, ProfileManager],
) -> None:
    _, pm = fresh_profile
    store, audit = pm.open_or_create("audit_del", "AL-Passw0rt-1")
    try:
        anon = Anonymizer(
            store=store,
            recognizers=default_recognizers(),
            detector=None,
            audit_log=audit,
            model_version="sec",
        )
        for _ in range(5):
            anon.anonymize("UID ATU12345675 — Mandant ohne Schreibvariante.")
        assert audit.verify_chain()
        # Lösche eine Zeile aus dem audit_log
        conn: sqlite3.Connection = store.connection
        conn.execute("DELETE FROM audit_log WHERE id = (SELECT min(id) FROM audit_log)")
        conn.commit()
        assert not audit.verify_chain()
    finally:
        store.close()


def test_audit_chain_detects_modified_row(
    fresh_profile: tuple[Path, ProfileManager],
) -> None:
    _, pm = fresh_profile
    store, audit = pm.open_or_create("audit_mod", "AL-Passw0rt-2")
    try:
        anon = Anonymizer(
            store=store,
            recognizers=default_recognizers(),
            detector=None,
            audit_log=audit,
            model_version="sec",
        )
        for _ in range(3):
            anon.anonymize("UID ATU12345675.")
        # Modifiziere `entity_counts_json` einer Zeile
        conn: sqlite3.Connection = store.connection
        conn.execute(
            "UPDATE audit_log SET entity_counts_json = ? WHERE id = 2",
            (json.dumps({"PERSON": 99}),),
        )
        conn.commit()
        assert not audit.verify_chain()
    finally:
        store.close()


def test_audit_chain_detects_modified_hash(
    fresh_profile: tuple[Path, ProfileManager],
) -> None:
    _, pm = fresh_profile
    store, audit = pm.open_or_create("audit_h", "AL-Passw0rt-3")
    try:
        anon = Anonymizer(
            store=store,
            recognizers=default_recognizers(),
            detector=None,
            audit_log=audit,
            model_version="sec",
        )
        anon.anonymize("UID ATU12345675.")
        anon.anonymize("UID ATU12345675.")
        # Manipuliere `this_hash` der ersten Zeile → Kette bricht ab Zeile 2.
        store.connection.execute(
            "UPDATE audit_log SET this_hash = ? WHERE id = 1", ("00" * 32,)
        )
        store.connection.commit()
        assert not audit.verify_chain()
    finally:
        store.close()


# --------------------------------------------------------------------------- #
# 4. Originaltexte erscheinen NICHT im SQLite-File                            #
# --------------------------------------------------------------------------- #


def test_originals_not_in_raw_sqlite_bytes(
    fresh_profile: tuple[Path, ProfileManager],
) -> None:
    """Selbst ohne SQLCipher dürfen Originaltexte nicht plaintext auf Disk landen."""
    data_dir, pm = fresh_profile
    store, audit = pm.open_or_create("leak", "Leak-Passw0rt")
    try:
        anon = Anonymizer(
            store=store,
            recognizers=default_recognizers(),
            detector=None,
            audit_log=audit,
            model_version="leak",
        )
        secret_iban = "AT611904300234573201"
        secret_uid = "ATU12345675"
        anon.anonymize(
            "Geheim-Mandant Hofer Bau GmbH mit IBAN "
            + secret_iban
            + " und UID "
            + secret_uid
            + "."
        )
    finally:
        store.close()

    # Lese die rohe SQLite-DB
    db_files = list(data_dir.rglob("*.sqlite"))
    assert db_files, f"Erwartete .sqlite-Datei unter {data_dir}, fanden: {list(data_dir.rglob('*'))}"
    raw = db_files[0].read_bytes()
    # Originaltexte dürfen NICHT im Plaintext erscheinen.
    assert b"Hofer Bau GmbH" not in raw
    assert secret_iban.encode("utf-8") not in raw
    assert secret_uid.encode("utf-8") not in raw


# --------------------------------------------------------------------------- #
# 5. Audit-Log enthält keinen Originaltext                                    #
# --------------------------------------------------------------------------- #


def test_audit_log_stores_only_hashes_no_originals(
    fresh_profile: tuple[Path, ProfileManager],
) -> None:
    _, pm = fresh_profile
    store, audit = pm.open_or_create("hash", "Hash-Passw0rt")
    try:
        anon = Anonymizer(
            store=store,
            recognizers=default_recognizers(),
            detector=None,
            audit_log=audit,
            model_version="audit",
        )
        secret = "Mandant Hofer Bau GmbH mit IBAN AT611904300234573201"
        anon.anonymize(secret)
        entries = audit.all_entries()
        for e in entries:
            # Kein Feld darf den Originaltext oder die IBAN enthalten
            for value in (
                e.anonymized_text_sha256,
                e.model_version,
                e.recognizer_version,
                e.prev_hash,
                e.this_hash,
            ):
                assert "Hofer Bau GmbH" not in value
                assert "AT611904300234573201" not in value
    finally:
        store.close()


# --------------------------------------------------------------------------- #
# 6. Wiederöffnen mit korrektem Passwort liefert dieselben Mappings           #
# --------------------------------------------------------------------------- #


def test_reopen_preserves_mappings(
    fresh_profile: tuple[Path, ProfileManager],
) -> None:
    _, pm = fresh_profile
    store, audit = pm.open_or_create("reopen", "Reopen-Passw0rt")
    anon = Anonymizer(
        store=store,
        recognizers=default_recognizers(),
        detector=None,
        audit_log=audit,
        model_version="reopen",
    )
    r1 = anon.anonymize("IBAN AT611904300234573201 — UID ATU12345675.")
    placeholders_before = {s.text for s in r1.spans}
    store.close()

    store2, audit2 = pm.open_or_create("reopen", "Reopen-Passw0rt")
    try:
        anon2 = Anonymizer(
            store=store2,
            recognizers=default_recognizers(),
            detector=None,
            audit_log=audit2,
            model_version="reopen",
        )
        r2 = anon2.anonymize("IBAN AT611904300234573201 — UID ATU12345675.")
        placeholders_after = {s.text for s in r2.spans}
        assert placeholders_before == placeholders_after
        # Anonymisat-Text muss bit-identisch sein (Mappings sind stabil).
        assert r1.text == r2.text
    finally:
        store2.close()


# --------------------------------------------------------------------------- #
# 7. Verifikations-Token-Manipulation                                         #
# --------------------------------------------------------------------------- #


def test_tampered_verification_token_rejects_open(
    fresh_profile: tuple[Path, ProfileManager],
) -> None:
    _, pm = fresh_profile
    store, _ = pm.open_or_create("vtok", "VTok-Passw0rt")
    # Manipulation
    store.connection.execute(
        "UPDATE profile_metadata SET value = ? WHERE key = 'verification_ct_b64'",
        ("Zm9v",),  # base64("foo")
    )
    store.connection.commit()
    store.close()
    with pytest.raises(InvalidPasswordError):
        pm.open_or_create("vtok", "VTok-Passw0rt")
