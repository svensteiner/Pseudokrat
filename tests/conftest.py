"""Globale pytest-Fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# ML deaktivieren, bevor irgendein Modul aus pseudokrat importiert wird.
os.environ.setdefault("PSEUDOKRAT_DISABLE_ML", "1")


from pseudokrat.recognizers import default_recognizers  # noqa: E402
from pseudokrat.store.profile import ProfileManager  # noqa: E402

TEST_PASSWORD = "correct horse battery staple"


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def profile_manager(data_dir: Path) -> ProfileManager:
    del data_dir
    return ProfileManager()


@pytest.fixture
def store_and_audit(profile_manager: ProfileManager) -> Iterator[tuple[object, object]]:
    store, audit = profile_manager.open_or_create("test_profile", TEST_PASSWORD)
    try:
        yield store, audit
    finally:
        store.close()


@pytest.fixture
def recognizers() -> list:
    return default_recognizers()
