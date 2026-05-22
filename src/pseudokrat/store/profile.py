"""Profile-Verwaltung: jedes Profil hat eigene DB-Datei."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from pseudokrat.config import Settings
from pseudokrat.store.audit_log import AuditLog
from pseudokrat.store.mapping_store import MappingStore

_PROFILE_NAME_RE = re.compile(r"^[A-Za-zÄÖÜäöüß0-9 _\-]{1,64}$")

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

    def list_profiles(self) -> list[Profile]:
        profiles: list[Profile] = []
        for db in sorted(self._settings.profiles_dir.glob("*.sqlite")):
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

    def open_or_create(self, name: str, password: str) -> tuple[MappingStore, AuditLog]:
        path = self.profile_path(name)
        store = MappingStore(path, password=password, profile_name=name)
        log = AuditLog(store.connection)
        return store, log
