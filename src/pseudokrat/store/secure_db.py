"""Verschlüsselte SQLite-Persistenz — zweistufige Defense-in-Depth.

**Schicht 1 (immer aktiv): Field-Level-Encryption mit Fernet.**
Aus dem Master-Passwort wird via PBKDF2-HMAC-SHA512 (256.000 Iterationen)
ein 32-Byte-Fernet-Schlüssel + ein 32-Byte-HMAC-Schlüssel abgeleitet.
Originaltexte werden Cell-by-Cell verschlüsselt; ``normalized_hmac`` ist ein
keyed-HMAC für Exact-Match-Lookup ohne Entschlüsselung.

**Schicht 2 (optional, wenn ``sqlcipher3`` verfügbar): Page-Level-Encryption
mit SQLCipher.** Aktiviert über ``Settings.use_sqlcipher = True`` (Default:
True, fällt aber transparent zurück auf stdlib-sqlite3, wenn sqlcipher3
nicht installiert ist). Der SQLCipher-Schlüssel wird aus demselben PBKDF2-
Material abgeleitet — getrennter Hex-Subkey, damit ein Auslesen des Fernet-
Keys nicht das SQLCipher-Key kompromittiert.

Die Persistenz toleriert beide Modi parallel: eine DB, die mit Fernet-Only
angelegt wurde, kann später nicht „upgradet" werden ohne Re-Encrypt — beim
ersten Öffnen wird der Modus aus der Datei-Magic erkannt (SQLCipher startet
mit verschlüsselten Bytes, stdlib-sqlite mit Klartext-Header ``SQLite
format 3\\0``).

Siehe DECISIONS.md D-003 / D-031.
"""

from __future__ import annotations

import base64
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC
from pathlib import Path
from typing import Any

from cryptography.fernet import InvalidToken

from pseudokrat.store.key_protector import (
    SALT_BYTES,
    KeyProtector,
    KeyringSecretMissingError,
    OsKeyringKeyProtector,
    PasswordKeyProtector,
)
from pseudokrat.store.key_protector import (
    DerivedKeys as _ProtectorDerivedKeys,
)

PBKDF2_ITERATIONS = 256_000
VERIFICATION_PLAINTEXT = b"pseudokrat-v1-ok"

#: Sidecar neben der DB: existiert → Profil benutzt OS-Keyring statt Passwort.
#: Inhalt = Profilname (UTF-8), das als Account-Name im Keyring liegt.
KEYRING_MARKER_SUFFIX = ".keyring"

#: Magic bytes am Datei-Anfang einer unverschlüsselten SQLite-DB.
SQLITE_MAGIC = b"SQLite format 3\x00"


def _sqlcipher_available() -> bool:
    """True wenn sqlcipher3 (oder sqlcipher3-wheels) importierbar ist."""
    try:
        import sqlcipher3  # noqa: F401  (Import-Test)

        return True
    except ImportError:
        return False


def _use_sqlcipher() -> bool:
    """Effektives Aktivierungs-Flag.

    **Default ist OFF**, weil die passwortfreie Profil-Metadaten-Lese-API
    (D-018, D-023, D-029) auf Klartext-SQLite angewiesen ist — mit
    SQLCipher müsste sie das Master-Passwort kennen. Solange diese
    Metadaten nicht in ein eigenes Sidecar-File migriert sind, bleibt
    SQLCipher opt-in.

    Aktivieren mit::

        export PSEUDOKRAT_USE_SQLCIPHER=1   # Linux/macOS
        $env:PSEUDOKRAT_USE_SQLCIPHER = "1" # PowerShell

    Existierende Profile werden anhand des Datei-Magic-Bytes erkannt
    (siehe :func:`_file_is_sqlcipher`) und im jeweils korrekten Modus
    geöffnet, unabhängig vom Env-Default.
    """
    env = os.environ.get("PSEUDOKRAT_USE_SQLCIPHER")
    if env is not None:
        return env.strip() in ("1", "true", "yes", "on")
    return False


class InvalidPasswordError(Exception):
    """Master-Passwort konnte das Profil nicht entsperren."""


#: Re-export für Rückwärtskompatibilität — bestehender Code importiert
#: ``DerivedKeys`` aus ``secure_db``. Die kanonische Definition liegt jetzt in
#: :mod:`pseudokrat.store.key_protector`.
DerivedKeys = _ProtectorDerivedKeys


def derive_keys(password: str, salt: bytes) -> DerivedKeys:
    """Kompatibilitäts-Shim. Neuer Code soll ``PasswordKeyProtector(password)
    .derive(salt)`` verwenden — diese Funktion delegiert genau dorthin und
    bleibt für ältere Aufrufer (Tests, externe Skripte) erhalten."""
    return PasswordKeyProtector(password).derive(salt)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS profile_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mappings (
    placeholder TEXT PRIMARY KEY,
    original_ct BLOB NOT NULL,
    normalized_ct BLOB NOT NULL,
    normalized_hmac TEXT NOT NULL,
    pii_category TEXT NOT NULL,
    first_seen_utc TEXT NOT NULL,
    last_used_utc TEXT NOT NULL,
    use_count INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_mappings_normalized_hmac
    ON mappings(normalized_hmac);
CREATE INDEX IF NOT EXISTS idx_mappings_category
    ON mappings(pii_category);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    operation TEXT NOT NULL,
    entity_counts_json TEXT NOT NULL,
    anonymized_text_sha256 TEXT NOT NULL,
    model_version TEXT NOT NULL,
    recognizer_version TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    this_hash TEXT NOT NULL
);
"""


def _read_file_magic(db_path: Path) -> bytes:
    """Liest die ersten 16 Bytes — entscheidet, ob die DB SQLCipher oder stdlib ist."""
    try:
        with db_path.open("rb") as f:
            return f.read(16)
    except OSError:
        return b""


def _file_is_sqlcipher(db_path: Path) -> bool:
    """True, wenn die existierende DB SQLCipher-verschlüsselt aussieht.

    Heuristik: SQLite-Magic-Bytes am Anfang → stdlib-sqlite. Sonst:
    SQLCipher (oder beschädigt). Bei nicht existenter Datei: False.
    """
    if not db_path.exists():
        return False
    magic = _read_file_magic(db_path)
    return not magic.startswith(SQLITE_MAGIC)


def _connect(db_path: Path, *, encrypted: bool, key_hex: str) -> sqlite3.Connection:
    """Öffnet die DB im passenden Modus.

    ``encrypted=True`` → ``sqlcipher3.connect`` + ``PRAGMA key``. Die
    zurückgegebene Connection ist API-kompatibel zu ``sqlite3.Connection``,
    weil sqlcipher3 ein Drop-in-Wrapper ist.
    """
    if encrypted:
        try:
            import sqlcipher3  # type: ignore[import-not-found,unused-ignore]
            from sqlcipher3.dbapi2 import (
                Row as SqlcipherRow,  # type: ignore[import-not-found,unused-ignore]
            )
        except ImportError as exc:  # pragma: no cover - guarded by caller
            raise InvalidPasswordError(
                "Profil ist SQLCipher-verschlüsselt, aber sqlcipher3 ist nicht installiert. "
                "Installiere mit:  pip install pseudokrat[sqlcipher]"
            ) from exc
        conn_any: Any = sqlcipher3.connect(str(db_path))
        # PRAGMA key MUSS vor der ersten Query gesetzt werden.
        conn_any.execute(f"PRAGMA key = \"x'{key_hex}'\"")
        # Empfohlene Härtung: SHA-512 KDF + 256-bit AES + page_size 4096.
        conn_any.execute("PRAGMA cipher_page_size = 4096")
        conn_any.execute("PRAGMA kdf_iter = 256000")
        conn_any.execute("PRAGMA cipher_hmac_algorithm = HMAC_SHA512")
        conn_any.execute("PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA512")
        conn_any.row_factory = SqlcipherRow
        return conn_any  # type: ignore[no-any-return]
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _keyring_marker_path(db_path: Path) -> Path:
    """Sidecar-Marker neben der DB: existiert → Profil im OS-Keyring-Modus."""
    return db_path.with_suffix(db_path.suffix + KEYRING_MARKER_SUFFIX)


def profile_uses_keyring(db_path: Path) -> bool:
    """True, wenn das Profil im Simple-Mode angelegt wurde (OS-Keyring statt
    Passwort). Wird von der CLI/GUI für den Auto-Open-Pfad benutzt — ohne
    Passwort-Prompt."""
    return _keyring_marker_path(db_path).exists()


def _resolve_protector(
    db_path: Path,
    *,
    protector: KeyProtector | None,
    password: str | None,
) -> KeyProtector:
    """Wähle Protector entweder explizit (``protector`` Arg), oder
    abgeleitet aus Sidecar-Marker + ``password``."""
    if protector is not None:
        return protector
    marker_path = _keyring_marker_path(db_path)
    if marker_path.exists():
        profile_name = marker_path.read_text(encoding="utf-8").strip()
        if not profile_name:
            raise InvalidPasswordError(
                f"Keyring-Marker {marker_path} ist leer — Profil-Metadaten beschädigt."
            )
        return OsKeyringKeyProtector(profile_name=profile_name)
    if password is None:
        raise InvalidPasswordError(
            "Profil benötigt ein Master-Passwort, aber keines wurde übergeben "
            "(und kein OS-Keyring-Marker gefunden)."
        )
    return PasswordKeyProtector(password)


def open_or_init(
    db_path: Path,
    password: str | None = None,
    *,
    profile_name: str | None = None,
    protector: KeyProtector | None = None,
) -> tuple[sqlite3.Connection, DerivedKeys]:
    """Öffne oder initialisiere eine Profil-DB.

    Zwei Modi:

    1. **Passwort-Modus** (Default für Backwards-Compat): ``password`` wird
       per PBKDF2 in einen ``PasswordKeyProtector`` gewickelt.
    2. **Simple-Mode**: ``protector`` ist explizit ein
       :class:`OsKeyringKeyProtector`. Beim Erstanlegen wird ein
       Sidecar-Marker ``<db>.keyring`` geschrieben — dann erkennt jeder
       spätere ``open_or_init``-Aufruf den Modus automatisch und braucht
       kein Passwort.

    Bei Erstanlage werden Salt + Verifikations-Token generiert. Bei jedem
    weiteren Öffnen wird der abgeleitete Schlüssel über das
    Verifikations-Token geprüft; Mismatch → :class:`InvalidPasswordError`.
    """
    is_new = not db_path.exists()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Salt liegt als Sidecar `<db>.salt` neben der DB. Nötig, weil bei
    # SQLCipher-Modus ohne Salt der PRAGMA-key nicht abgeleitet werden
    # kann (Salt ist innerhalb der verschlüsselten DB nicht lesbar).
    salt_path = db_path.with_suffix(db_path.suffix + ".salt")
    use_sqlcipher = _file_is_sqlcipher(db_path) if not is_new else _use_sqlcipher()

    active_protector = _resolve_protector(db_path, protector=protector, password=password)
    is_keyring_mode = isinstance(active_protector, OsKeyringKeyProtector)

    if is_new:
        salt = os.urandom(SALT_BYTES)
        try:
            keys = active_protector.derive(salt)
        except KeyringSecretMissingError as exc:
            raise InvalidPasswordError(str(exc)) from exc
        salt_path.write_bytes(salt)
        if isinstance(active_protector, OsKeyringKeyProtector):
            # Marker FIRST: bei einem späteren Crash zwischen DB-Create und
            # Marker-Write hätten wir sonst eine DB ohne Auto-Detect — der
            # Nutzer würde nach einem Passwort gefragt, das er nie gesetzt
            # hat. Reihenfolge: Marker → Salt → DB.
            _keyring_marker_path(db_path).write_text(
                active_protector.profile_name, encoding="utf-8"
            )
        conn = _connect(db_path, encrypted=use_sqlcipher, key_hex=keys.sqlcipher_key_hex)
        conn.executescript(_SCHEMA)
        verification_ct = keys.fernet.encrypt(VERIFICATION_PLAINTEXT)
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        conn.executemany(
            "INSERT INTO profile_metadata (key, value) VALUES (?, ?)",
            [
                ("verification_ct_b64", base64.b64encode(verification_ct).decode("ascii")),
                ("created_utc", now),
                ("profile_name", profile_name or db_path.stem),
                ("model_version_pinned", ""),
                ("recognizer_version_pinned", ""),
                ("schema_version", "2"),
                ("encryption_mode", "sqlcipher+fernet" if use_sqlcipher else "fernet"),
                ("auth_mode", "os-keyring" if is_keyring_mode else "password"),
            ],
        )
        conn.commit()
        return conn, keys

    # Open existing
    if not salt_path.exists():
        raise InvalidPasswordError(
            f"Salt-Datei fehlt: {salt_path}. Profil ist nicht entschlüsselbar."
        )
    salt = salt_path.read_bytes()
    try:
        keys = active_protector.derive(salt)
    except KeyringSecretMissingError as exc:
        raise InvalidPasswordError(str(exc)) from exc
    conn = _connect(db_path, encrypted=use_sqlcipher, key_hex=keys.sqlcipher_key_hex)
    if use_sqlcipher:
        try:
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except Exception as exc:
            conn.close()
            raise InvalidPasswordError(
                "Falsches Master-Passwort (SQLCipher konnte die DB nicht öffnen)."
            ) from exc
    conn.executescript(_SCHEMA)

    rows = conn.execute(
        "SELECT key, value FROM profile_metadata WHERE key = ?",
        ("verification_ct_b64",),
    ).fetchall()
    meta = {r["key"]: r["value"] for r in rows}
    if "verification_ct_b64" not in meta:
        conn.close()
        raise InvalidPasswordError("Profil-Metadaten unvollständig — DB beschädigt?")
    verification_ct = base64.b64decode(meta["verification_ct_b64"])
    try:
        plaintext = keys.fernet.decrypt(verification_ct)
    except InvalidToken as exc:
        conn.close()
        if is_keyring_mode:
            raise InvalidPasswordError(
                "OS-Keyring-Eintrag passt nicht zur Profil-DB — "
                "vermutlich aus einem Backup übernommen oder Konto-Wechsel."
            ) from exc
        raise InvalidPasswordError("Falsches Master-Passwort") from exc
    if plaintext != VERIFICATION_PLAINTEXT:
        conn.close()
        raise InvalidPasswordError("Verifikations-Token ungültig")
    return conn, keys


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
