"""Konfigurations- und Pfad-Helfer."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _default_data_dir() -> Path:
    """Standardpfad für Pseudokrat-Daten.

    Windows: %LOCALAPPDATA%/Pseudokrat
    macOS:   ~/Library/Application Support/Pseudokrat
    Linux:   ~/.local/share/pseudokrat
    """
    override = os.environ.get("PSEUDOKRAT_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()

    platform = sys.platform
    if platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        return base / "Pseudokrat"
    if platform == "darwin":  # pragma: no cover - macOS-spezifisch
        return Path.home() / "Library/Application Support/Pseudokrat"
    return Path.home() / ".local/share/pseudokrat"


@dataclass(frozen=True)
class Settings:
    """Globale Pfade und Feature-Flags."""

    data_dir: Path
    profiles_dir: Path
    model_cache_dir: Path
    model_id: str
    disable_ml: bool

    @classmethod
    def load(cls) -> Settings:
        data_dir = _default_data_dir()
        return cls(
            data_dir=data_dir,
            profiles_dir=data_dir / "profiles",
            model_cache_dir=data_dir / "models",
            model_id=os.environ.get("PSEUDOKRAT_MODEL_ID", "openai/privacy-filter"),
            disable_ml=os.environ.get("PSEUDOKRAT_DISABLE_ML", "").lower() in {"1", "true", "yes"},
        )

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.model_cache_dir.mkdir(parents=True, exist_ok=True)
