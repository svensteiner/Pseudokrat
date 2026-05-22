"""Hauptpipeline: Text → erkannte PII → Platzhalter → anonymisierter Text."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from pseudokrat.pii.privacy_filter import PIIDetector
from pseudokrat.recognizers.base import Recognizer, Span
from pseudokrat.store.audit_log import AuditEntry, AuditLog
from pseudokrat.store.mapping_store import MappingStore

RECOGNIZER_VERSION = "1.0.0"


@dataclass(frozen=True)
class AnonymizationResult:
    text: str
    spans: list[Span]
    entity_counts: dict[str, int]
    audit_entry: AuditEntry | None = field(default=None)


def _resolve_overlaps(spans: list[Span]) -> list[Span]:
    """Bei Überlappung gewinnt der längere, bei Gleichstand der höhere Score.

    Spans werden anschließend in Reihenfolge (start ASC) zurückgegeben.
    """
    if not spans:
        return []
    ordered = sorted(spans, key=lambda s: (s.start, -(s.end - s.start), -s.score))
    accepted: list[Span] = []
    for span in ordered:
        if accepted and span.start < accepted[-1].end:
            current = accepted[-1]
            cur_len = current.end - current.start
            new_len = span.end - span.start
            if (new_len, span.score) > (cur_len, current.score):
                accepted[-1] = span
            continue
        accepted.append(span)
    return accepted


class Anonymizer:
    """Erkennt PII via Recognizer-Bundle + optionalem ML-Detektor und ersetzt sie."""

    def __init__(
        self,
        store: MappingStore,
        recognizers: list[Recognizer],
        detector: PIIDetector | None = None,
        audit_log: AuditLog | None = None,
        model_version: str = "n/a",
    ) -> None:
        self._store = store
        self._recognizers = recognizers
        self._detector = detector
        self._audit_log = audit_log
        self._model_version = model_version

    def detect(self, text: str) -> list[Span]:
        """Sammle Spans aus allen Recognizern + ggf. ML-Detektor."""
        spans: list[Span] = []
        for recognizer in self._recognizers:
            spans.extend(recognizer.analyze(text))
        if self._detector is not None:
            spans.extend(self._detector.analyze(text))
        return _resolve_overlaps(spans)

    def anonymize(self, text: str) -> AnonymizationResult:
        spans = self.detect(text)
        # Wandle Spans → Platzhalter rückwärts, damit Indizes stabil bleiben.
        result_chars = list(text)
        placeholders_used: list[str] = []
        counts: Counter[str] = Counter()
        for span in sorted(spans, key=lambda s: s.start, reverse=True):
            mapping = self._store.get_or_create(span.text, span.category)
            result_chars[span.start : span.end] = mapping.placeholder
            placeholders_used.append(mapping.placeholder)
            counts[span.category] += 1

        anonymized = "".join(result_chars)
        audit_entry = None
        if self._audit_log is not None:
            audit_entry = self._audit_log.append(
                operation="anonymize",
                entity_counts=dict(counts),
                anonymized_text=anonymized,
                model_version=self._model_version,
                recognizer_version=RECOGNIZER_VERSION,
            )
        return AnonymizationResult(
            text=anonymized,
            spans=spans,
            entity_counts=dict(counts),
            audit_entry=audit_entry,
        )
