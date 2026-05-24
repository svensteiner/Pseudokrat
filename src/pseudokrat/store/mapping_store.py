"""Persistent encrypted store für Pseudonym-Mappings."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pseudokrat.fuzzy import is_fuzzy_merge_category, normalize, should_merge
from pseudokrat.store.secure_db import DerivedKeys, open_or_init, transaction


@dataclass(frozen=True, slots=True)
class Mapping:
    placeholder: str
    original_text: str
    normalized_form: str
    pii_category: str
    first_seen_utc: str
    last_used_utc: str
    use_count: int


class MappingStore:
    """Verschlüsselter Persistenz-Layer für PII-Mappings eines Profils."""

    def __init__(self, db_path: Path, password: str, profile_name: str | None = None) -> None:
        self._conn: sqlite3.Connection
        self._keys: DerivedKeys
        self._conn, self._keys = open_or_init(db_path, password, profile_name=profile_name)

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    @property
    def keys(self) -> DerivedKeys:
        return self._keys

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> MappingStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ----- Profil-Metadaten --------------------------------------------------

    def get_metadata(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM profile_metadata WHERE key = ? LIMIT 1",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return str(row["value"])

    def set_metadata(self, key: str, value: str) -> None:
        with transaction(self._conn):
            self._conn.execute(
                "INSERT INTO profile_metadata (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def delete_metadata(self, key: str) -> None:
        with transaction(self._conn):
            self._conn.execute(
                "DELETE FROM profile_metadata WHERE key = ?",
                (key,),
            )

    # ----- Pseudonym-Vergabe -------------------------------------------------

    def _next_placeholder(self, category: str) -> str:
        """Suche `<CATEGORY_xxx>` mit höchstem Suffix, vergib `xxx+1`."""
        prefix = f"<{category}_"
        rows = self._conn.execute(
            "SELECT placeholder FROM mappings WHERE placeholder LIKE ? ",
            (prefix + "%",),
        ).fetchall()
        max_idx = 0
        for r in rows:
            ph = r["placeholder"]
            suffix = ph[len(prefix) : -1]  # entferne "<CAT_" und ">"
            try:
                idx = int(suffix)
            except ValueError:
                continue
            if idx > max_idx:
                max_idx = idx
        return f"<{category}_{max_idx + 1:03d}>"

    # ----- Lookup ------------------------------------------------------------

    def find_by_original(self, original: str, category: str) -> Mapping | None:
        """Finde Mapping per Exact- oder Fuzzy-Match."""
        normalized = normalize(original)
        # 1) Exact-Match via HMAC-Index
        hmac_hex = self._keys.hmac_hex(normalized)
        row = self._conn.execute(
            "SELECT * FROM mappings WHERE normalized_hmac = ? AND pii_category = ? LIMIT 1",
            (hmac_hex, category),
        ).fetchone()
        if row is not None:
            return self._row_to_mapping(row)
        # 2) Fuzzy-Match — nur für Kategorien, die Schreibvarianten erlauben.
        #    Für numerische IDs (IBAN/UID/SVNR/…) wäre der lineare Scan nicht
        #    nur unnötig (Exact-Match-Schritt 1 ist authoritative), sondern
        #    auch teuer: jeder Lookup würde O(n) Fernet-Entschlüsselungen
        #    kosten. Siehe D-032.
        if not is_fuzzy_merge_category(category):
            return None
        rows = self._conn.execute(
            "SELECT * FROM mappings WHERE pii_category = ?",
            (category,),
        ).fetchall()
        for r in rows:
            candidate_norm = self._decrypt(r["normalized_ct"])
            if should_merge(normalized, candidate_norm, category):
                return self._row_to_mapping(r)
        return None

    def find_by_placeholder(self, placeholder: str) -> Mapping | None:
        row = self._conn.execute(
            "SELECT * FROM mappings WHERE placeholder = ?",
            (placeholder,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_mapping(row)

    def all_placeholders(self) -> list[str]:
        rows = self._conn.execute("SELECT placeholder FROM mappings").fetchall()
        return [r["placeholder"] for r in rows]

    def all_mappings(self) -> list[Mapping]:
        rows = self._conn.execute("SELECT * FROM mappings").fetchall()
        return [self._row_to_mapping(r) for r in rows]

    # ----- Mutation ---------------------------------------------------------

    def get_or_create(self, original: str, category: str) -> Mapping:
        """Liefere bestehendes Mapping oder lege neues an."""
        existing = self.find_by_original(original, category)
        now = datetime.now(UTC).isoformat()
        if existing is not None:
            with transaction(self._conn):
                self._conn.execute(
                    "UPDATE mappings SET last_used_utc = ?, use_count = use_count + 1"
                    " WHERE placeholder = ?",
                    (now, existing.placeholder),
                )
            return Mapping(
                placeholder=existing.placeholder,
                original_text=existing.original_text,
                normalized_form=existing.normalized_form,
                pii_category=existing.pii_category,
                first_seen_utc=existing.first_seen_utc,
                last_used_utc=now,
                use_count=existing.use_count + 1,
            )

        normalized = normalize(original)
        placeholder = self._next_placeholder(category)
        hmac_hex = self._keys.hmac_hex(normalized)
        with transaction(self._conn):
            self._conn.execute(
                "INSERT INTO mappings (placeholder, original_ct, normalized_ct, "
                "normalized_hmac, pii_category, first_seen_utc, last_used_utc, use_count)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    placeholder,
                    self._encrypt(original),
                    self._encrypt(normalized),
                    hmac_hex,
                    category,
                    now,
                    now,
                    1,
                ),
            )
        return Mapping(
            placeholder=placeholder,
            original_text=original,
            normalized_form=normalized,
            pii_category=category,
            first_seen_utc=now,
            last_used_utc=now,
            use_count=1,
        )

    # ----- Internals --------------------------------------------------------

    def _encrypt(self, plain: str) -> bytes:
        return self._keys.fernet.encrypt(plain.encode("utf-8"))

    def _decrypt(self, token: bytes) -> str:
        return self._keys.fernet.decrypt(token).decode("utf-8")

    def _row_to_mapping(self, row: sqlite3.Row) -> Mapping:
        return Mapping(
            placeholder=row["placeholder"],
            original_text=self._decrypt(row["original_ct"]),
            normalized_form=self._decrypt(row["normalized_ct"]),
            pii_category=row["pii_category"],
            first_seen_utc=row["first_seen_utc"],
            last_used_utc=row["last_used_utc"],
            use_count=row["use_count"],
        )
