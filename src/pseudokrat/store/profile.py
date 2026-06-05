"""Profile-Verwaltung: jedes Profil hat eigene DB-Datei."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pseudokrat.config import Settings
from pseudokrat.store.audit_log import AuditLog
from pseudokrat.store.mapping_store import MappingStore

if TYPE_CHECKING:
    from pseudokrat.store.key_protector import KeyProtector, KeyringBackend

_PROFILE_NAME_RE = re.compile(r"^[A-Za-zÄÖÜäöüß0-9 _\-]{1,64}$")

#: Slug-Prefix für reservierte Profile (interne Smoke-Tests, Doctor-Sandbox-
#: Leichen aus Bestandsinstallationen vor Iter-14). User-sichtbare APIs
#: blenden diese standardmäßig aus, damit kein Pilot-Tester über sie
#: stolpert. Reine Underscore-Prefix-Konvention — User können selbst keine
#: solchen Profile via :meth:`profile_path` anlegen, weil der zugehörige
#: Profilname „_…" durch :data:`_PROFILE_NAME_RE` zwar erlaubt ist, der
#: Slug nach :func:`_safe_slug` mit ``strip("_")`` aber bereinigt würde.
RESERVED_PROFILE_SLUG_PREFIX = "_"

#: Schlüssel in ``profile_metadata`` für den per-Profil konfigurierbaren
#: Mandanten-Nummern-Regex (§7 Megaprompt). Wird unverschlüsselt gespeichert,
#: weil der Regex selbst keine PII enthält und ohne Master-Passwort lesbar
#: sein muss (z. B. für Profile-Listenanzeigen und Validierungen).
MANDANTEN_PATTERN_METADATA_KEY = "mandanten_nr_pattern"


def read_profile_metadata(db_path: Path, key: str) -> str | None:
    """Liest einen Klartext-Eintrag aus ``profile_metadata`` ohne Master-Passwort.

    Hilfsfunktion für Metadaten, die bewusst nicht verschlüsselt sind
    (Profilname, schema_version, mandanten_nr_pattern, …).
    """
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT value FROM profile_metadata WHERE key = ? LIMIT 1",
                (key,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return str(row[0])


def _safe_slug(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", name)
    return cleaned.strip("_") or "profile"


def _read_profile_name(db_path: Path) -> str:
    """Liest den Klartext-Profilnamen aus ``profile_metadata`` (kein Passwort nötig).

    Der Profilname wird beim Anlegen unverschlüsselt in ``profile_metadata``
    gespeichert (siehe ``secure_db.open_or_init``), damit ``profiles list``
    auch ohne Master-Passwort die Originalnamen zeigen kann. Bei beschädigten
    oder leeren Datenbanken fällt der Name auf den Datei-Stem zurück.
    """
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT value FROM profile_metadata WHERE key = 'profile_name' LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return db_path.stem
    if row is None or not row[0]:
        return db_path.stem
    return str(row[0])


@dataclass(frozen=True)
class Profile:
    name: str
    db_path: Path

    @property
    def slug(self) -> str:
        return _safe_slug(self.name)


class ProfileManager:
    """Erzeugt, listet und öffnet Mandantenprofile."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings.load()
        self._settings.ensure_dirs()

    @property
    def settings(self) -> Settings:
        return self._settings

    def list_profiles(self, *, include_reserved: bool = False) -> list[Profile]:
        """Alle Profile im konfigurierten ``profiles_dir``.

        ``include_reserved=False`` (Default) blendet Profile mit einem
        Slug-Prefix von ``_`` aus — das sind interne Sandbox-Profile
        (Doctor-Smoke-Test vor Iter-14, Migrations-Leichen). Echte
        Pilot-Tester sollen sie weder im CLI-``profiles list`` noch im
        GUI sehen.

        ``include_reserved=True`` ist für Diagnose-/Cleanup-Pfade
        gedacht (Doctor-Migration, Backup-Tooling).
        """
        profiles: list[Profile] = []
        for db in sorted(self._settings.profiles_dir.glob("*.sqlite")):
            if not include_reserved and db.stem.startswith(
                RESERVED_PROFILE_SLUG_PREFIX
            ):
                continue
            name = _read_profile_name(db)
            profiles.append(Profile(name=name, db_path=db))
        return profiles

    def profile_path(self, name: str) -> Path:
        if not _PROFILE_NAME_RE.fullmatch(name):
            raise ValueError(
                "Profilname enthält ungültige Zeichen. Erlaubt: Buchstaben, Ziffern, "
                "Leerzeichen, _, -."
            )
        return self._settings.profiles_dir / f"{_safe_slug(name)}.sqlite"

    def open_or_create(
        self,
        name: str,
        password: str | None = None,
        *,
        protector: KeyProtector | None = None,
    ) -> tuple[MappingStore, AuditLog]:
        """Öffne oder erzeuge ein Profil per Master-Passwort ODER per
        OS-Keyring-``protector``. Existiert das Profil bereits im
        Simple-Mode (``<db>.keyring``-Marker), genügt ``password=None``,
        ``protector=None`` — der Modus wird automatisch erkannt."""
        path = self.profile_path(name)
        store = MappingStore(
            path, password=password, profile_name=name, protector=protector
        )
        log = AuditLog(store.connection)
        return store, log

    def detect_simple_default(self) -> str | None:
        """Erkennt das Default-Profil für den Simple-Mode-UX-Pfad.

        Liefert genau dann einen Profilnamen zurück, wenn es **genau ein**
        Profil gibt und das im Simple-Mode (OS-Keyring-Marker) angelegt
        wurde. Sonst ``None`` — entweder weil mehrere Profile existieren
        (Multi-Mandant-Setup, Profil-Auswahl bleibt sichtbar), keines
        existiert (Wizard-Onboarding nötig), oder das einzige im
        Passwort-Modus liegt (Power-User-Setup).

        Diese Heuristik treibt den GUI-Simple-Mode: ein Profil + Simple-
        Mode → Profil-Selector + Profile-Tab werden ausgeblendet, das
        Profil wird beim Start automatisch geöffnet.
        """
        from pseudokrat.store.secure_db import profile_uses_keyring

        profiles = self.list_profiles()
        if len(profiles) != 1:
            return None
        only = profiles[0]
        if not profile_uses_keyring(only.db_path):
            return None
        return only.name

    def open_or_create_simple(
        self, name: str, *, backend: KeyringBackend | None = None
    ) -> tuple[MappingStore, AuditLog]:
        """Convenience: legt das Profil im Simple-Mode an (OS-Keyring),
        falls noch nicht vorhanden — sonst öffnet es im erkannten Modus.

        ``backend`` ist nur für Tests gedacht — Default ist
        :class:`SystemKeyringBackend` (Windows Credential Manager / macOS
        Keychain / Linux SecretService).
        """
        from pseudokrat.store.key_protector import OsKeyringKeyProtector

        protector = OsKeyringKeyProtector(name, backend=backend)
        protector.ensure_secret()
        return self.open_or_create(name, protector=protector)
