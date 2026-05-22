"""CLI-Tests für `pseudokrat model {status,download,remove}`."""

from __future__ import annotations

from pathlib import Path

import pytest

from pseudokrat.cli import main


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")


def test_model_status_reports_missing(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["model", "status"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "NICHT VORHANDEN" in out


def test_model_download_without_yes_returns_15(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["model", "download"])
    err = capsys.readouterr().err
    assert rc == 15
    assert "--yes" in err


def test_model_download_with_yes_fails_when_huggingface_missing(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "huggingface_hub", None)
    rc = main(["model", "download", "--yes"])
    err = capsys.readouterr().err
    assert rc == 16
    assert "huggingface_hub" in err


def test_model_remove_on_empty_cache_returns_0(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["model", "remove"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Kein Modell-Cache" in out
