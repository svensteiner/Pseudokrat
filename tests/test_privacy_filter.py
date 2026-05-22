"""Tests für PII-Detector (Privacy-Filter-Adapter + Null-Stub)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pseudokrat.config import Settings
from pseudokrat.pii.privacy_filter import (
    NullPrivacyFilterDetector,
    PrivacyFilterDetector,
    load_default_detector,
)


def test_null_detector_returns_empty() -> None:
    det = NullPrivacyFilterDetector()
    assert det.analyze("Beliebiger Text mit Herrn Müller.") == []
    assert det.name == "null_privacy_filter"


def test_load_default_detector_returns_null_when_disabled(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        profiles_dir=tmp_path / "profiles",
        model_cache_dir=tmp_path / "models",
        model_id="dummy/model",
        disable_ml=True,
    )
    det = load_default_detector(settings)
    assert isinstance(det, NullPrivacyFilterDetector)


def test_load_default_detector_returns_privacy_filter_when_enabled(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        profiles_dir=tmp_path / "profiles",
        model_cache_dir=tmp_path / "models",
        model_id="dummy/model",
        disable_ml=False,
    )
    det = load_default_detector(settings)
    assert isinstance(det, PrivacyFilterDetector)
    assert det.name == "privacy_filter"


def test_load_default_detector_uses_default_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")
    det = load_default_detector()
    assert isinstance(det, NullPrivacyFilterDetector)


def test_privacy_filter_empty_text_short_circuits() -> None:
    det = PrivacyFilterDetector(model_id="dummy/model")
    assert det.analyze("") == []


class _FakePipeline:
    """Minimaler Fake einer HuggingFace token-classification Pipeline."""

    def __init__(self, entities: list[dict[str, Any]]) -> None:
        self._entities = entities

    def __call__(self, text: str) -> list[dict[str, Any]]:
        del text
        return self._entities


def test_privacy_filter_maps_known_labels() -> None:
    det = PrivacyFilterDetector(model_id="dummy/model")
    det._pipeline = _FakePipeline(  # type: ignore[attr-defined]
        [
            {"entity_group": "private_person", "start": 0, "end": 6, "score": 0.99},
            {"entity_group": "private_address", "start": 10, "end": 18, "score": 0.88},
            {"entity_group": "unknown_label", "start": 20, "end": 25, "score": 0.5},
            {"entity_group": "private_phone", "start": 30, "end": 30, "score": 0.7},
        ]
    )
    spans = det.analyze("Müller in Salzburg gestern.")
    cats = [s.category for s in spans]
    assert "PERSON" in cats
    assert "ADDRESS" in cats
    # unknown_label und Null-Length werden gefiltert
    assert "UNKNOWN" not in cats
    assert all(s.end > s.start for s in spans)


def test_privacy_filter_handles_legacy_entity_field() -> None:
    det = PrivacyFilterDetector(model_id="dummy/model")
    det._pipeline = _FakePipeline(  # type: ignore[attr-defined]
        [{"entity": "person", "start": 0, "end": 6, "score": 0.9}]
    )
    spans = det.analyze("Müller schreibt.")
    assert len(spans) == 1
    assert spans[0].category == "PERSON"
