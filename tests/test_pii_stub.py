"""Tests für den PrivacyFilter-Adapter (Stub-Modus)."""

from __future__ import annotations

from pseudokrat.config import Settings
from pseudokrat.pii.privacy_filter import (
    NullPrivacyFilterDetector,
    load_default_detector,
)


def test_null_detector_returns_empty() -> None:
    detector = NullPrivacyFilterDetector()
    assert detector.analyze("Herr Müller wohnt in Salzburg") == []


def test_load_default_detector_returns_null_when_disabled(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")
    settings = Settings.load()
    detector = load_default_detector(settings)
    assert isinstance(detector, NullPrivacyFilterDetector)
