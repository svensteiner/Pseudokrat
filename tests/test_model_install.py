"""Tests für die ML-Modell-Installations-Helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from pseudokrat.config import Settings
from pseudokrat.pii.model_install import (
    ModelDownloadError,
    _model_cache_subdir,
    free_disk_bytes,
    model_is_ready,
    model_status,
    remove_model,
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        profiles_dir=tmp_path / "profiles",
        model_cache_dir=tmp_path / "models",
        model_id="openai/privacy-filter",
        disable_ml=False,
    )


def test_model_status_reports_missing_for_empty_cache(settings: Settings) -> None:
    status = model_status(settings)
    assert status.model_id == "openai/privacy-filter"
    assert status.is_present is False
    assert status.bytes_on_disk == 0
    assert status.gigabytes_on_disk == 0.0


def test_model_status_reports_present_when_cache_has_large_blob(settings: Settings) -> None:
    settings.model_cache_dir.mkdir(parents=True, exist_ok=True)
    model_dir = _model_cache_subdir(settings.model_cache_dir, settings.model_id)
    model_dir.mkdir(parents=True, exist_ok=True)
    # Schreibe ein „großes" Snapshot-File (101 MB).
    big = model_dir / "snapshots" / "fake_snapshot"
    big.parent.mkdir(parents=True, exist_ok=True)
    big.write_bytes(b"\0" * (101 * 1024 * 1024))

    status = model_status(settings)
    assert status.is_present is True
    assert status.gigabytes_on_disk > 0.09


def test_model_status_ignores_partial_download(settings: Settings) -> None:
    """Ein angefangener Download (< 100 MB) gilt als NICHT vorhanden."""
    settings.model_cache_dir.mkdir(parents=True, exist_ok=True)
    model_dir = _model_cache_subdir(settings.model_cache_dir, settings.model_id)
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "partial.bin").write_bytes(b"\0" * (5 * 1024 * 1024))
    assert model_status(settings).is_present is False


def test_remove_model_removes_cache(settings: Settings) -> None:
    settings.model_cache_dir.mkdir(parents=True, exist_ok=True)
    model_dir = _model_cache_subdir(settings.model_cache_dir, settings.model_id)
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "blob.bin").write_bytes(b"\0" * (200 * 1024 * 1024))
    bytes_freed = remove_model(settings)
    assert bytes_freed >= 200 * 1024 * 1024
    assert not model_dir.exists()


def test_remove_model_on_empty_cache_returns_zero(settings: Settings) -> None:
    assert remove_model(settings) == 0


def test_free_disk_bytes_returns_positive(settings: Settings) -> None:
    assert free_disk_bytes(settings.model_cache_dir) > 0


def test_model_is_ready_false_when_disable_ml(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    disabled = Settings(
        data_dir=settings.data_dir,
        profiles_dir=settings.profiles_dir,
        model_cache_dir=settings.model_cache_dir,
        model_id=settings.model_id,
        disable_ml=True,
    )
    monkeypatch.delenv("PSEUDOKRAT_DISABLE_ML", raising=False)
    assert model_is_ready(disabled) is False


def test_model_is_ready_false_when_cache_missing(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PSEUDOKRAT_DISABLE_ML", raising=False)
    assert model_is_ready(settings) is False


def test_download_model_raises_when_huggingface_hub_missing(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ohne huggingface_hub muss download_model klar erklären, was fehlt."""
    import sys

    monkeypatch.setitem(sys.modules, "huggingface_hub", None)

    with pytest.raises(ModelDownloadError) as exc:
        from pseudokrat.pii.model_install import download_model

        download_model(settings)
    assert "huggingface_hub" in str(exc.value)


def test_resolved_revision_strict_mode_rejects_branch(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Strict-Mode-Flag muss `main`/`master`/`HEAD` als ungepinnt verweigern."""
    from pseudokrat.pii.model_install import (
        UnpinnedModelRevisionError,
        _resolved_revision,
    )

    monkeypatch.delenv("PSEUDOKRAT_MODEL_REVISION", raising=False)
    monkeypatch.setenv("PSEUDOKRAT_REQUIRE_PINNED_REVISION", "1")

    with pytest.raises(UnpinnedModelRevisionError):
        _resolved_revision(settings)


def test_resolved_revision_strict_mode_accepts_sha(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mit gesetzter SHA muss Strict-Mode anstandslos durchlassen."""
    from pseudokrat.pii.model_install import _resolved_revision

    sha = "a" * 40
    monkeypatch.setenv("PSEUDOKRAT_MODEL_REVISION", sha)
    monkeypatch.setenv("PSEUDOKRAT_REQUIRE_PINNED_REVISION", "1")

    assert _resolved_revision(settings) == sha


def test_resolved_revision_default_returns_pinned(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ohne Strict-Mode liefert die Funktion den hartcodierten Pin."""
    from pseudokrat.pii.model_install import (
        PINNED_MODEL_REVISION,
        _resolved_revision,
    )

    monkeypatch.delenv("PSEUDOKRAT_MODEL_REVISION", raising=False)
    monkeypatch.delenv("PSEUDOKRAT_REQUIRE_PINNED_REVISION", raising=False)

    assert _resolved_revision(settings) == PINNED_MODEL_REVISION
