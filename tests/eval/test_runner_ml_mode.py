"""Tests für den ``--with-ml``-Pfad des Eval-Runners.

Strategie: Wir lassen das echte Modell nicht laden (3 GB Download in
CI verboten). Stattdessen:

* ``test_ml_mode_raises_when_model_not_cached`` deckt den
  „Modell-Cache leer"-Pfad ab — der Runner muss klar werfen, nicht
  silent downloaden.
* ``test_recognizers_only_mode_default`` validiert, dass ohne Flag
  der Detector ``None`` ist.
* ``test_main_returns_2_when_model_not_cached`` validiert den
  CLI-Exit-Code.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.eval import runner as runner_mod
from tests.eval.runner import ModelNotCachedError, _build_anonymizer, main


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Jeder Test bekommt ein frisches Datenverzeichnis. Das hindert
    den ML-Lauf daran, zufällig ein echtes Modell im Default-Cache
    zu finden."""
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    # Sicherstellen, dass kein vorheriger Test PSEUDOKRAT_DISABLE_ML
    # auf 1 stehen ließ.
    monkeypatch.delenv("PSEUDOKRAT_DISABLE_ML", raising=False)


def test_recognizers_only_mode_default(tmp_path: Path) -> None:
    """Ohne ``with_ml=True`` darf NIEMALS versucht werden, ein Modell zu
    laden — auch nicht, um die Cache-Existenz zu prüfen.

    Beweis über den tatsächlichen Mechanismus: der ML-Privacy-Detektor bleibt
    ungesetzt (``None``). (Die frühere Proxy-Annahme „PERSON/ADDRESS nur via
    ML" gilt nicht mehr — der ML-freie Gazetteer-Recognizer erkennt bekannte
    Vornamen wie „Erika" auch ohne Modell.) Der Cache ist via Fixture leer;
    mit ``with_ml=True`` würde der Aufbau hier mit ``ModelNotCachedError``
    scheitern — ohne ML gelingt er und lädt nichts."""
    anon = _build_anonymizer(with_ml=False)
    assert anon._detector is None
    # Die regelbasierte Pipeline funktioniert trotzdem.
    assert isinstance(anon.detect("Beliebiger Text ohne Modell-Abhängigkeit."), list)


def test_ml_mode_raises_when_model_not_cached(tmp_path: Path) -> None:
    """``with_ml=True`` plus leerer Cache → ModelNotCachedError mit
    Anweisungen, KEIN automatischer Download."""
    # Sicherstellen, dass der Cache-Ordner leer ist.
    cache = tmp_path / "models"
    cache.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ModelNotCachedError) as exc:
        _build_anonymizer(with_ml=True)
    msg = str(exc.value)
    assert "pseudokrat model download" in msg
    assert "ohne --with-ml" in msg


def test_main_exits_2_when_model_not_cached(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI: ``--with-ml`` mit fehlendem Cache → Exit-Code 2 + klare
    Fehlermeldung auf stderr."""
    rc = main(["--with-ml"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "Privacy-Filter-Modell ist nicht im Cache" in captured.err


def test_main_recognizers_only_writes_recognizers_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Default-CLI-Lauf schreibt ``"mode": "recognizers-only"`` in den Report."""
    rc = main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"mode": "recognizers-only"' in out


def test_model_not_cached_error_is_runtime_subclass() -> None:
    """ModelNotCachedError ist eine RuntimeError-Subclass — damit
    bestehende Exception-Handler in der CLI sie als generischen
    Laufzeit-Fehler behandeln können."""
    assert issubclass(ModelNotCachedError, RuntimeError)


def test_ml_mode_clears_disable_ml_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``with_ml=True`` muss ``PSEUDOKRAT_DISABLE_ML`` aus der ENV
    entfernen — sonst läuft der Settings.load() in den Null-Detector,
    auch wenn das Flag gesetzt ist."""
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")
    with pytest.raises(ModelNotCachedError):
        _build_anonymizer(with_ml=True)
    # Nach dem fehlgeschlagenen Aufruf muss die Variable weg sein.
    assert os.environ.get("PSEUDOKRAT_DISABLE_ML") is None


def test_runner_module_exports_model_not_cached_error() -> None:
    """ModelNotCachedError muss aus dem Modul importierbar sein —
    damit externe Scripts auf den Cache-Miss-Fall reagieren können."""
    assert hasattr(runner_mod, "ModelNotCachedError")
