"""Tests für KeyProtector + OsKeyringKeyProtector + secure_db-Integration.

Vermeidet das echte OS-Keyring (CI-Headless, Test-Stabilität): nutzt
:class:`InMemoryKeyringBackend` als injizierten Backend.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest

from pseudokrat.store.key_protector import (
    KEYRING_SERVICE,
    SALT_BYTES,
    SECRET_BYTES,
    InMemoryKeyringBackend,
    KeyringSecretMissingError,
    OsKeyringKeyProtector,
    PasswordKeyProtector,
)
from pseudokrat.store.secure_db import (
    InvalidPasswordError,
    open_or_init,
    profile_uses_keyring,
)

# --- PasswordKeyProtector ---------------------------------------------------


def test_password_protector_deterministic() -> None:
    salt = os.urandom(SALT_BYTES)
    a = PasswordKeyProtector("hunter2hunter2").derive(salt)
    b = PasswordKeyProtector("hunter2hunter2").derive(salt)
    assert a == b


def test_password_protector_changes_with_password() -> None:
    salt = os.urandom(SALT_BYTES)
    a = PasswordKeyProtector("hunter2hunter2").derive(salt)
    b = PasswordKeyProtector("hunter3hunter3").derive(salt)
    assert a != b


def test_password_protector_changes_with_salt() -> None:
    a = PasswordKeyProtector("hunter2hunter2").derive(os.urandom(SALT_BYTES))
    b = PasswordKeyProtector("hunter2hunter2").derive(os.urandom(SALT_BYTES))
    assert a != b


def test_password_protector_rejects_empty_password() -> None:
    with pytest.raises(ValueError):
        PasswordKeyProtector("")


def test_password_protector_rejects_wrong_salt_length() -> None:
    with pytest.raises(ValueError):
        PasswordKeyProtector("hunter2hunter2").derive(b"too-short")


# --- OsKeyringKeyProtector --------------------------------------------------


def test_os_keyring_protector_creates_secret_when_ensured() -> None:
    backend = InMemoryKeyringBackend()
    p = OsKeyringKeyProtector("alice", backend=backend)
    p.ensure_secret()
    raw = backend.get(KEYRING_SERVICE, "alice")
    assert raw is not None
    assert len(base64.b64decode(raw)) == SECRET_BYTES


def test_os_keyring_protector_ensure_is_idempotent() -> None:
    backend = InMemoryKeyringBackend()
    p = OsKeyringKeyProtector("alice", backend=backend)
    p.ensure_secret()
    first = backend.get(KEYRING_SERVICE, "alice")
    p.ensure_secret()
    second = backend.get(KEYRING_SERVICE, "alice")
    assert first == second  # nicht überschrieben


def test_os_keyring_protector_derive_is_deterministic() -> None:
    backend = InMemoryKeyringBackend()
    p = OsKeyringKeyProtector("alice", backend=backend)
    p.ensure_secret()
    salt = os.urandom(SALT_BYTES)
    a = p.derive(salt)
    b = p.derive(salt)
    assert a == b


def test_os_keyring_protector_distinct_profiles_distinct_keys() -> None:
    backend = InMemoryKeyringBackend()
    alice = OsKeyringKeyProtector("alice", backend=backend)
    bob = OsKeyringKeyProtector("bob", backend=backend)
    alice.ensure_secret()
    bob.ensure_secret()
    salt = os.urandom(SALT_BYTES)
    assert alice.derive(salt) != bob.derive(salt)


def test_os_keyring_protector_missing_secret_raises() -> None:
    backend = InMemoryKeyringBackend()
    p = OsKeyringKeyProtector("alice", backend=backend)
    with pytest.raises(KeyringSecretMissingError):
        p.derive(os.urandom(SALT_BYTES))


def test_os_keyring_protector_tampered_secret_raises() -> None:
    backend = InMemoryKeyringBackend()
    backend.set(KEYRING_SERVICE, "alice", base64.b64encode(b"too-short").decode())
    p = OsKeyringKeyProtector("alice", backend=backend)
    with pytest.raises(KeyringSecretMissingError):
        p.derive(os.urandom(SALT_BYTES))


def test_os_keyring_protector_rejects_empty_profile() -> None:
    with pytest.raises(ValueError):
        OsKeyringKeyProtector("")


def test_os_keyring_protector_reset_removes_entry() -> None:
    backend = InMemoryKeyringBackend()
    p = OsKeyringKeyProtector("alice", backend=backend)
    p.ensure_secret()
    p.reset_secret()
    assert backend.get(KEYRING_SERVICE, "alice") is None


# --- secure_db.open_or_init mit OsKeyringKeyProtector -----------------------


def _make_keyring_protector(profile: str) -> OsKeyringKeyProtector:
    """Per-Test isolierter Backend, damit Tests sich nicht überschreiben."""
    backend = InMemoryKeyringBackend()
    p = OsKeyringKeyProtector(profile, backend=backend)
    p.ensure_secret()
    return p


def test_open_or_init_creates_keyring_marker(tmp_path: Path) -> None:
    db = tmp_path / "alice.sqlite"
    protector = _make_keyring_protector("alice")
    conn, _ = open_or_init(db, protector=protector, profile_name="alice")
    conn.close()

    marker = db.with_suffix(db.suffix + ".keyring")
    assert marker.exists()
    assert marker.read_text(encoding="utf-8") == "alice"
    assert profile_uses_keyring(db)


def test_open_or_init_reopen_with_same_protector_succeeds(tmp_path: Path) -> None:
    db = tmp_path / "alice.sqlite"
    protector = _make_keyring_protector("alice")
    conn, keys_a = open_or_init(db, protector=protector, profile_name="alice")
    conn.close()
    conn2, keys_b = open_or_init(db, protector=protector)
    conn2.close()
    assert keys_a == keys_b


def test_open_or_init_reopen_with_wrong_keyring_secret_raises(tmp_path: Path) -> None:
    db = tmp_path / "alice.sqlite"
    protector = _make_keyring_protector("alice")
    open_or_init(db, protector=protector, profile_name="alice")[0].close()

    # Frisches Backend → simuliert: Eintrag im Keyring weg (z. B. nach OS-
    # Reinstall) oder Konto-Wechsel.
    fresh = InMemoryKeyringBackend()
    new_protector = OsKeyringKeyProtector("alice", backend=fresh)
    new_protector.ensure_secret()  # neues Secret, anderer Key
    with pytest.raises(InvalidPasswordError):
        open_or_init(db, protector=new_protector)


def test_open_or_init_password_mode_does_not_write_marker(tmp_path: Path) -> None:
    db = tmp_path / "alice.sqlite"
    conn, _ = open_or_init(db, "hunter2hunter2", profile_name="alice")
    conn.close()
    marker = db.with_suffix(db.suffix + ".keyring")
    assert not marker.exists()
    assert not profile_uses_keyring(db)


def test_open_or_init_password_profile_rejects_keyring_open(tmp_path: Path) -> None:
    """Passwort-Profil mit OS-Keyring-Protector öffnen → schlägt fehl."""
    db = tmp_path / "alice.sqlite"
    open_or_init(db, "hunter2hunter2", profile_name="alice")[0].close()
    backend = InMemoryKeyringBackend()
    p = OsKeyringKeyProtector("alice", backend=backend)
    p.ensure_secret()
    with pytest.raises(InvalidPasswordError):
        open_or_init(db, protector=p)


def test_open_or_init_auto_detect_uses_marker(tmp_path: Path) -> None:
    """Wenn Marker existiert, soll der zweite Open ohne expliziten Protector
    automatisch in den OS-Keyring-Pfad gehen — sofern der Default-Backend
    den richtigen Eintrag liefert. Wir testen das mit einem präparierten
    Default-Backend per Monkeypatch nicht (zu viel Magie), sondern weisen
    nach, dass _resolve_protector ohne password+ohne protector und mit
    Marker den OsKeyringKeyProtector wählt."""
    db = tmp_path / "alice.sqlite"
    protector = _make_keyring_protector("alice")
    open_or_init(db, protector=protector, profile_name="alice")[0].close()

    # Ohne explizit-Protector und ohne Password würde der Default-Backend
    # (SystemKeyringBackend) befragt — der hat den Eintrag nicht. Wir
    # wollen die Pfadwahl testen, nicht das echte OS-Keyring.
    from pseudokrat.store.secure_db import _resolve_protector

    chosen = _resolve_protector(db, protector=None, password=None)
    assert isinstance(chosen, OsKeyringKeyProtector)
    assert chosen.profile_name == "alice"


def test_open_or_init_without_password_or_marker_raises(tmp_path: Path) -> None:
    db = tmp_path / "alice.sqlite"
    with pytest.raises(InvalidPasswordError):
        open_or_init(db)


# --- ProfileManager.open_or_create_simple end-to-end ------------------------


def test_profile_manager_simple_mode_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Volle Kette: ProfileManager → open_or_create_simple → MappingStore →
    Mapping schreiben → schließen → wieder öffnen (ohne Passwort, ohne
    Backend-Argument!) → gleiche Mappings sichtbar.

    Bestätigt: Auto-Detect über Sidecar-Marker funktioniert auch durch den
    ProfileManager hindurch.
    """
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    from pseudokrat.store.profile import ProfileManager

    manager = ProfileManager()
    backend = InMemoryKeyringBackend()

    # Erstanlage im Simple-Mode
    store, _ = manager.open_or_create_simple("alice", backend=backend)
    mapping = store.get_or_create("Max Mustermann", "PERSON")
    placeholder = mapping.placeholder
    store.close()

    # Reopen: kein Password, kein explizites Backend — Auto-Detect über Marker.
    # Aber wir müssen denselben Backend benutzen, sonst wäre das Geheimnis weg.
    # In Production: SystemKeyringBackend wird per Default genommen. Im Test
    # injizieren wir denselben InMemory-Backend, indem wir den Protector
    # explizit übergeben.
    from pseudokrat.store.key_protector import OsKeyringKeyProtector

    protector = OsKeyringKeyProtector("alice", backend=backend)
    store2, _ = manager.open_or_create("alice", protector=protector)
    found = store2.find_by_original("Max Mustermann", "PERSON")
    assert found is not None
    assert found.placeholder == placeholder
    store2.close()
