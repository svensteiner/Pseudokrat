"""Reverse-Pipeline: Platzhalter → Originaltexte."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from pseudokrat.anonymizer import RECOGNIZER_VERSION
from pseudokrat.store.audit_log import AuditEntry, AuditLog
from pseudokrat.store.mapping_store import MappingStore

_PLACEHOLDER_RE = re.compile(r"<([A-Z_]+)_(\d{3,})>")


@dataclass(frozen=True)
class DeanonymizationResult:
    text: str
    resolved_placeholders: list[str]
    missing_placeholders: list[str]
    entity_counts: dict[str, int]
    audit_entry: AuditEntry | None = field(default=None)


class Deanonymizer:
    """Ersetzt Platzhalter zurück zu Originaltexten anhand des Mapping-Stores."""

    def __init__(
        self,
        store: MappingStore,
        audit_log: AuditLog | None = None,
        model_version: str = "n/a",
    ) -> None:
        self._store = store
        self._audit_log = audit_log
        self._model_version = model_version

    def deanonymize(self, text: str) -> DeanonymizationResult:
        resolved: list[str] = []
        missing: list[str] = []
        counts: Counter[str] = Counter()

        def replace(match: re.Match[str]) -> str:
            placeholder = match.group(0)
            mapping = self._store.find_by_placeholder(placeholder)
            if mapping is None:
                missing.append(placeholder)
                return placeholder
            resolved.append(placeholder)
            counts[mapping.pii_category] += 1
            return mapping.original_text

        result_text = _PLACEHOLDER_RE.sub(replace, text)
        audit_entry = None
        if self._audit_log is not None:
            audit_entry = self._audit_log.append(
                operation="deanonymize",
                entity_counts=dict(counts),
                anonymized_text=text,
                model_version=self._model_version,
                recognizer_version=RECOGNIZER_VERSION,
            )
        return DeanonymizationResult(
            text=result_text,
            resolved_placeholders=resolved,
            missing_placeholders=missing,
            entity_counts=dict(counts),
            audit_entry=audit_entry,
        )
