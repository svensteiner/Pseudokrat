"""Audit-Log mit Hash-Kette (tamper-evident)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping as TMapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pseudokrat.store.secure_db import transaction

GENESIS_HASH = "0" * 64


@dataclass(frozen=True, slots=True)
class AuditEntry:
    id: int
    timestamp_utc: str
    operation: str
    entity_counts: dict[str, int]
    anonymized_text_sha256: str
    model_version: str
    recognizer_version: str
    prev_hash: str
    this_hash: str


def _hash_entry(
    timestamp_utc: str,
    operation: str,
    entity_counts_json: str,
    anonymized_text_sha256: str,
    model_version: str,
    recognizer_version: str,
    prev_hash: str,
) -> str:
    payload = "|".join(
        [
            timestamp_utc,
            operation,
            entity_counts_json,
            anonymized_text_sha256,
            model_version,
            recognizer_version,
            prev_hash,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditLog:
    """Append-only Audit-Log mit Hash-Kette über alle Einträge."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _last_hash(self) -> str:
        row = self._conn.execute(
            "SELECT this_hash FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["this_hash"] if row else GENESIS_HASH

    def append(
        self,
        *,
        operation: str,
        entity_counts: TMapping[str, int],
        anonymized_text: str,
        model_version: str,
        recognizer_version: str,
    ) -> AuditEntry:
        timestamp = datetime.now(UTC).isoformat()
        entity_counts_json = json.dumps(dict(sorted(entity_counts.items())), separators=(",", ":"))
        anon_hash = hashlib.sha256(anonymized_text.encode("utf-8")).hexdigest()
        prev_hash = self._last_hash()
        this_hash = _hash_entry(
            timestamp,
            operation,
            entity_counts_json,
            anon_hash,
            model_version,
            recognizer_version,
            prev_hash,
        )
        with transaction(self._conn):
            cur = self._conn.execute(
                "INSERT INTO audit_log (timestamp_utc, operation, entity_counts_json, "
                "anonymized_text_sha256, model_version, recognizer_version, prev_hash, "
                "this_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    timestamp,
                    operation,
                    entity_counts_json,
                    anon_hash,
                    model_version,
                    recognizer_version,
                    prev_hash,
                    this_hash,
                ),
            )
        entry_id = int(cur.lastrowid or 0)
        return AuditEntry(
            id=entry_id,
            timestamp_utc=timestamp,
            operation=operation,
            entity_counts=dict(entity_counts),
            anonymized_text_sha256=anon_hash,
            model_version=model_version,
            recognizer_version=recognizer_version,
            prev_hash=prev_hash,
            this_hash=this_hash,
        )

    def all_entries(self) -> list[AuditEntry]:
        rows = self._conn.execute("SELECT * FROM audit_log ORDER BY id ASC").fetchall()
        return [
            AuditEntry(
                id=r["id"],
                timestamp_utc=r["timestamp_utc"],
                operation=r["operation"],
                entity_counts=json.loads(r["entity_counts_json"]),
                anonymized_text_sha256=r["anonymized_text_sha256"],
                model_version=r["model_version"],
                recognizer_version=r["recognizer_version"],
                prev_hash=r["prev_hash"],
                this_hash=r["this_hash"],
            )
            for r in rows
        ]

    def verify_chain(self) -> bool:
        """Validiere die komplette Hash-Kette. Manipulation → False."""
        prev = GENESIS_HASH
        rows = self._conn.execute(
            "SELECT timestamp_utc, operation, entity_counts_json, anonymized_text_sha256,"
            " model_version, recognizer_version, prev_hash, this_hash"
            " FROM audit_log ORDER BY id ASC"
        ).fetchall()
        for r in rows:
            if r["prev_hash"] != prev:
                return False
            recomputed = _hash_entry(
                r["timestamp_utc"],
                r["operation"],
                r["entity_counts_json"],
                r["anonymized_text_sha256"],
                r["model_version"],
                r["recognizer_version"],
                r["prev_hash"],
            )
            if recomputed != r["this_hash"]:
                return False
            prev = r["this_hash"]
        return True

    def export_pdf(self, output_path: Path, *, profile_name: str | None = None) -> Path:
        """PDF-Repräsentation für externen Audit (reportlab).

        Schreibt die Audit-Tabelle inkl. Hash-Chain-Verifikationszeile in eine
        neue PDF-Datei. Original-Spalten bleiben identisch zu ``export_csv``.
        """
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=landscape(A4),
            leftMargin=24,
            rightMargin=24,
            topMargin=24,
            bottomMargin=24,
        )
        styles = getSampleStyleSheet()
        story: list[object] = []

        title = "Pseudokrat — Audit-Log"
        if profile_name:
            title = f"{title} (Profil: {profile_name})"
        story.append(Paragraph(title, styles["Title"]))
        chain_ok = self.verify_chain()
        chain_text = "Hash-Kette gültig" if chain_ok else "MANIPULATION ERKANNT"
        story.append(Paragraph(f"Generiert: {datetime.now(UTC).isoformat()}", styles["Normal"]))
        story.append(Paragraph(f"Status: {chain_text}", styles["Normal"]))
        story.append(Spacer(1, 12))

        header = [
            "ID",
            "Zeitstempel (UTC)",
            "Operation",
            "Entitäten",
            "SHA-256 (Anon.)",
            "Modell",
            "Recognizer",
            "this_hash",
        ]
        rows: list[list[str]] = [header]
        for entry in self.all_entries():
            rows.append(
                [
                    str(entry.id),
                    entry.timestamp_utc,
                    entry.operation,
                    json.dumps(entry.entity_counts, separators=(",", ":")),
                    entry.anonymized_text_sha256[:16] + "…",
                    entry.model_version,
                    entry.recognizer_version,
                    entry.this_hash[:16] + "…",
                ]
            )
        table = Table(rows, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(table)
        doc.build(story)
        return output_path

    def export_csv(self) -> str:
        """CSV-Repräsentation für externen Audit."""
        import csv
        import io

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "id",
                "timestamp_utc",
                "operation",
                "entity_counts",
                "anonymized_text_sha256",
                "model_version",
                "recognizer_version",
                "prev_hash",
                "this_hash",
            ]
        )
        for entry in self.all_entries():
            writer.writerow(
                [
                    entry.id,
                    entry.timestamp_utc,
                    entry.operation,
                    json.dumps(entry.entity_counts, separators=(",", ":")),
                    entry.anonymized_text_sha256,
                    entry.model_version,
                    entry.recognizer_version,
                    entry.prev_hash,
                    entry.this_hash,
                ]
            )
        return buffer.getvalue()
