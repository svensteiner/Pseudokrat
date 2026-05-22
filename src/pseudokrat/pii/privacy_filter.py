"""Adapter für das HuggingFace-Modell `openai/privacy-filter` (oder kompatibel).

In Phase 1 wird das Modell *lazy* beim ersten Aufruf von ``analyze`` geladen.
Über die Umgebungsvariable ``PSEUDOKRAT_DISABLE_ML=1`` wird der ML-Pfad
deaktiviert; in diesem Fall liefert :class:`NullPrivacyFilterDetector` leere
Resultate. Dies ist die Default-Einstellung für Tests und CI.
"""

from __future__ import annotations

from typing import Any, Protocol

from pseudokrat.config import Settings
from pseudokrat.recognizers.base import Span

# Mapping der Modell-Label auf interne Kategorien.
_LABEL_MAP: dict[str, str] = {
    "private_person": "PERSON",
    "person": "PERSON",
    "private_address": "ADDRESS",
    "address": "ADDRESS",
    "private_email": "EMAIL",
    "email": "EMAIL",
    "private_phone": "PHONE",
    "phone": "PHONE",
    "private_url": "URL",
    "url": "URL",
    "private_date": "DATE",
    "date": "DATE",
    "account_number": "ACCOUNT",
    "secret": "SECRET",
}


class PIIDetector(Protocol):
    """Schnittstelle für ML-basierte PII-Detektion."""

    name: str

    def analyze(self, text: str) -> list[Span]:  # pragma: no cover - protocol
        ...


class NullPrivacyFilterDetector:
    """Stub für Tests/CI — liefert immer eine leere Span-Liste."""

    name = "null_privacy_filter"

    def analyze(self, text: str) -> list[Span]:
        del text
        return []


class PrivacyFilterDetector:
    """Lazy-loading HuggingFace-NER-Pipeline.

    Das schwere Importieren von ``transformers``/``torch`` erfolgt erst beim
    ersten Aufruf von ``analyze``. So bleibt der Import-Fußabdruck der
    pseudokrat-CLI klein.
    """

    name = "privacy_filter"

    def __init__(self, model_id: str, cache_dir: str | None = None) -> None:
        self._model_id = model_id
        self._cache_dir = cache_dir
        self._pipeline: Any = None

    def _ensure_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        try:
            from transformers import pipeline
        except ImportError as exc:  # pragma: no cover - geprüft via env-flag
            raise RuntimeError(
                "ML-Modell aktiviert, aber transformers ist nicht installiert. "
                "Installation: `pip install pseudokrat[ml]` oder "
                "`PSEUDOKRAT_DISABLE_ML=1` setzen, um den ML-Pfad zu überspringen."
            ) from exc

        self._pipeline = pipeline(
            task="token-classification",
            model=self._model_id,
            aggregation_strategy="simple",
            model_kwargs={"cache_dir": self._cache_dir} if self._cache_dir else {},
        )
        return self._pipeline

    def analyze(self, text: str) -> list[Span]:
        if not text:
            return []
        pipe = self._ensure_pipeline()
        raw_results = pipe(text)
        spans: list[Span] = []
        for entity in raw_results:
            label = str(entity.get("entity_group", entity.get("entity", ""))).lower()
            category = _LABEL_MAP.get(label)
            if category is None:
                continue
            start = int(entity["start"])
            end = int(entity["end"])
            if end <= start:
                continue
            spans.append(
                Span(
                    start=start,
                    end=end,
                    category=category,
                    text=text[start:end],
                    score=float(entity.get("score", 0.5)),
                )
            )
        return spans


def load_default_detector(settings: Settings | None = None) -> PIIDetector:
    """Liefere den passenden Detektor anhand der Settings/Env."""
    if settings is None:
        settings = Settings.load()
    if settings.disable_ml:
        return NullPrivacyFilterDetector()
    return PrivacyFilterDetector(
        model_id=settings.model_id,
        cache_dir=str(settings.model_cache_dir),
    )
