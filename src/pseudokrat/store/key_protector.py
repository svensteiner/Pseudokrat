"""Schlüssel-Schutz-Schichten — wählt das Trust-Anchor für ein Profil.

Pseudokrat unterstützt zwei Anker, aus denen die ``DerivedKeys`` (Fernet,
HMAC, SQLCipher-Subkey) abgeleitet werden:

1. **PasswordKeyProtector** — klassischer Pfad. Master-Passwort des Nutzers
   wird via PBKDF2-HMAC-SHA512 (256 000 Iterationen) gestreckt. Schutz auch
   gegen einen Angreifer, der das Windows-Konto kompromittiert hat.

2. **OsKeyringKeyProtector** — Simple-Mode. Pro Profil wird ein 256-Bit-
   Zufallsgeheimnis im OS-Keyring abgelegt:

   * Windows → Credential Manager / DPAPI (über ``keyring``)
   * macOS → Keychain
   * Linux → SecretService/GNOME-Keyring (über ``keyring``)

   Das Geheimnis ist an das Betriebssystem-Konto gebunden — kein Master-
   Passwort nötig. Sicherheitsniveau: identisch zu Edge/Outlook-
   Passwort-Speicher.

Welcher Protector beim Öffnen eines Profils gewählt wird, hängt von einem
Sidecar-File neben der DB ab (``<db>.keyring`` → OS-Keyring-Modus). Bei
Erstanlage entscheidet der Aufrufer.

Test-Mock: :class:`InMemoryKeyringBackend` injizierbar als Backend für
``OsKeyringKeyProtector``, damit Tests ohne echtes OS-Keyring laufen.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

PBKDF2_ITERATIONS = 256_000
SALT_BYTES = 16
SECRET_BYTES = 32  # 256-bit symmetric secret for OS-keyring backend
HKDF_INFO = b"pseudokrat-v1-derived-keys"
KEYRING_SERVICE = "pseudokrat"


@dataclass(frozen=True)
class DerivedKeys:
    """Dreigeteiltes Schlüssel-Material aus PBKDF2 oder HKDF.

    Identisch in der Datenstruktur zur bisherigen ``DerivedKeys`` in
    ``secure_db`` — der Konsument unterscheidet nicht, ob das Material aus
    PBKDF2 (Passwort) oder HKDF (OS-Keyring-Secret) stammt.
    """

    fernet_key: bytes
    hmac_key: bytes
    sqlcipher_key_hex: str

    @property
    def fernet(self) -> Fernet:
        return Fernet(self.fernet_key)

    def hmac_hex(self, value: str) -> str:
        return hmac.new(self.hmac_key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def _split_material(material: bytes) -> DerivedKeys:
    if len(material) != 96:
        raise ValueError(f"Key-Material muss 96 Byte sein, war {len(material)}")
    fernet_key = base64.urlsafe_b64encode(material[:32])
    hmac_key = material[32:64]
    sqlcipher_key_hex = material[64:96].hex()
    return DerivedKeys(
        fernet_key=fernet_key,
        hmac_key=hmac_key,
        sqlcipher_key_hex=sqlcipher_key_hex,
    )


class KeyProtector(Protocol):
    """Erzeugt ``DerivedKeys`` aus einem profil-spezifischen Salt.

    Die Implementierungen halten ihre Trust-Anchor (Passwort bzw.
    OS-Keyring-Eintrag) intern und sind nach erfolgreicher
    Initialisierung deterministisch: zweimal :meth:`derive` mit demselben
    Salt liefert identische Schlüssel.
    """

    def derive(self, salt: bytes) -> DerivedKeys: ...

    @property
    def label(self) -> str:
        """Kurzname für Logs/Diagnose (kein Geheimnis)."""
        ...


class PasswordKeyProtector:
    """PBKDF2-basierter Schutz. Existing-Behavior, kompatibel zu Profilen,
    die mit Master-Passwort angelegt wurden."""

    def __init__(self, password: str) -> None:
        if not isinstance(password, str) or not password:
            raise ValueError("Passwort muss ein nicht-leerer String sein.")
        self._password = password

    def derive(self, salt: bytes) -> DerivedKeys:
        if len(salt) != SALT_BYTES:
            raise ValueError(f"Salt muss {SALT_BYTES} Byte sein, war {len(salt)}")
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA512(),
            length=96,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
        )
        return _split_material(kdf.derive(self._password.encode("utf-8")))

    @property
    def label(self) -> str:
        return "password"


@runtime_checkable
class KeyringBackend(Protocol):
    """Minimale Keyring-Abstraktion — austauschbar für Tests."""

    def get(self, service: str, account: str) -> str | None: ...

    def set(self, service: str, account: str, secret: str) -> None: ...

    def delete(self, service: str, account: str) -> None: ...


class SystemKeyringBackend:
    """Dünner Wrapper um ``keyring``-Library.

    Lazy-Import: ``keyring`` ist nur in der ``simple-mode``-Extra
    enthalten. Wenn nicht verfügbar → klare Fehlermeldung, kein impliziter
    Fallback auf Plaintext.
    """

    def _keyring(self) -> object:
        try:
            import keyring  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - install-path
            raise RuntimeError(
                "Simple-Mode benötigt die Keyring-Bibliothek. Installiere mit:\n"
                "  pip install pseudokrat[simple-mode]"
            ) from exc
        return keyring

    def get(self, service: str, account: str) -> str | None:
        kr = self._keyring()
        return kr.get_password(service, account)  # type: ignore[attr-defined,no-any-return]

    def set(self, service: str, account: str, secret: str) -> None:
        kr = self._keyring()
        kr.set_password(service, account, secret)  # type: ignore[attr-defined]

    def delete(self, service: str, account: str) -> None:
        import contextlib

        kr = self._keyring()
        with contextlib.suppress(Exception):
            # delete_password wirft, wenn der Eintrag nicht existiert —
            # idempotente Löschung ist erwünscht.
            kr.delete_password(service, account)  # type: ignore[attr-defined]


class InMemoryKeyringBackend:
    """Test-Backend. Persistiert nichts."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get(self, service: str, account: str) -> str | None:
        return self._store.get((service, account))

    def set(self, service: str, account: str, secret: str) -> None:
        self._store[(service, account)] = secret

    def delete(self, service: str, account: str) -> None:
        self._store.pop((service, account), None)


class KeyringSecretMissingError(Exception):
    """OS-Keyring kennt das Profil nicht — vermutlich gelöscht oder Konto-Wechsel."""


class OsKeyringKeyProtector:
    """Simple-Mode-Protector — Geheimnis liegt im OS-Keyring.

    Bei Erstanlage (``ensure_exists=True``) wird ein neues 256-Bit-Geheimnis
    erzeugt und im Keyring abgelegt. Bei jedem späteren Öffnen wird das
    Geheimnis aus dem Keyring gelesen und via HKDF mit dem profil-Salt zu
    den ``DerivedKeys`` gespannt.

    Account-Name = Profilname (z. B. ``default``). Service-Name ist konstant
    ``pseudokrat`` — damit ein Nutzer alle seine Pseudokrat-Profile auf
    einen Blick in seinem Credential-Manager sieht.
    """

    def __init__(
        self,
        profile_name: str,
        *,
        backend: KeyringBackend | None = None,
        service: str = KEYRING_SERVICE,
    ) -> None:
        if not profile_name:
            raise ValueError("profile_name darf nicht leer sein.")
        self._profile_name = profile_name
        self._backend: KeyringBackend = backend or SystemKeyringBackend()
        self._service = service

    @property
    def label(self) -> str:
        return f"os-keyring:{self._service}/{self._profile_name}"

    @property
    def profile_name(self) -> str:
        return self._profile_name

    def ensure_secret(self) -> None:
        """Lege ein neues Zufallsgeheimnis an, wenn noch keines existiert.

        Idempotent: erneutes Aufrufen überschreibt nichts.
        """
        existing = self._backend.get(self._service, self._profile_name)
        if existing is not None:
            return
        secret = os.urandom(SECRET_BYTES)
        encoded = base64.b64encode(secret).decode("ascii")
        self._backend.set(self._service, self._profile_name, encoded)

    def reset_secret(self) -> None:
        """Lösche das gespeicherte Geheimnis. Macht das Profil unentschlüsselbar!

        Nur für Migrations- oder Test-Pfade. Produktions-Code sollte das
        nicht aufrufen, ohne den Nutzer explizit zu warnen.
        """
        self._backend.delete(self._service, self._profile_name)

    def derive(self, salt: bytes) -> DerivedKeys:
        if len(salt) != SALT_BYTES:
            raise ValueError(f"Salt muss {SALT_BYTES} Byte sein, war {len(salt)}")
        encoded = self._backend.get(self._service, self._profile_name)
        if encoded is None:
            raise KeyringSecretMissingError(
                f"Kein OS-Keyring-Eintrag für Profil {self._profile_name!r}. "
                "Entweder wurde der Eintrag gelöscht (Reinstall des OS?) "
                "oder das Profil läuft auf einem anderen Benutzerkonto."
            )
        secret = base64.b64decode(encoded)
        if len(secret) != SECRET_BYTES:
            raise KeyringSecretMissingError(
                "OS-Keyring-Eintrag hat falsche Länge — vermutlich manipuliert."
            )
        material = HKDF(
            algorithm=hashes.SHA512(),
            length=96,
            salt=salt,
            info=HKDF_INFO,
        ).derive(secret)
        return _split_material(material)
