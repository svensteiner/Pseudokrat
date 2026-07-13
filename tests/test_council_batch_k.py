"""Tests fuer Council-Batch-K (#30): OllamaDetector — Wortgrenzen, Plausibilitaet,
Cache, min_chars. HTTP wird ueber Monkeypatch von _query umgangen (kein Server noetig)."""

from __future__ import annotations

from pseudokrat.pii.ollama_detector import OllamaDetector


def test_analyze_finds_entity_with_word_boundaries() -> None:
    det = OllamaDetector(min_chars=5)
    det._query = lambda text: [("Hankook", "COMPANY")]  # type: ignore[assignment]
    spans = det.analyze("Die Hankook Reifenhandel liefert schnell.")
    assert any(s.text == "Hankook" and s.category == "COMPANY" for s in spans)


def test_no_match_inside_longer_word() -> None:
    det = OllamaDetector(min_chars=5)
    det._query = lambda text: [("Hank", "COMPANY")]  # type: ignore[assignment]
    # 'Hank' kommt nur INNERHALB von 'Hankook' vor -> kein eigenstaendiger Treffer.
    assert det.analyze("Die Hankook Reifen liefern.") == []


def test_person_type_maps_through() -> None:
    det = OllamaDetector(min_chars=5)
    det._query = lambda text: [("Sven Steiner", "PERSON")]  # type: ignore[assignment]
    spans = det.analyze("Herr Sven Steiner unterschreibt heute.")
    assert any(s.category == "PERSON" for s in spans)


class TestPlausibility:
    def test_real_name_ok(self) -> None:
        assert OllamaDetector._is_plausible("Hankook") is True

    def test_stopword_rejected(self) -> None:
        assert OllamaDetector._is_plausible("GmbH") is False
        assert OllamaDetector._is_plausible("Rechnung") is False  # Stopwort trotz Grossbuchstabe

    def test_too_short_rejected(self) -> None:
        assert OllamaDetector._is_plausible("ab") is False

    def test_no_uppercase_rejected(self) -> None:
        assert OllamaDetector._is_plausible("firmenname") is False


def test_min_chars_skips_query() -> None:
    det = OllamaDetector(min_chars=100)
    calls: list[str] = []
    det._query = lambda text: calls.append(text) or []  # type: ignore[assignment,return-value]
    assert det.analyze("kurz") == []
    assert calls == []  # LLM gar nicht erst befragt


def test_cache_avoids_second_query() -> None:
    det = OllamaDetector(min_chars=5)
    calls: list[str] = []

    def q(text: str) -> list[tuple[str, str]]:
        calls.append(text)
        return [("Hankook", "COMPANY")]

    det._query = q  # type: ignore[assignment]
    text = "Die Hankook Reifen GmbH liefert."
    det.analyze(text)
    det.analyze(text)  # gleicher (normalisierter) Text -> Cache-Treffer
    assert len(calls) == 1
