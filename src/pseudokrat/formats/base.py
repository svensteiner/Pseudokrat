"""Gemeinsame Typen und Protokolle für Format-Handler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class UnsupportedFormatError(ValueError):
    """Wird geworfen, wenn keine Handler-Klasse für ein Dateiformat existiert."""


# Eine Transform-Funktion erhält einen Text-String (z. B. einen Absatz, eine
# Zelle, einen ganzen TXT-Inhalt) und liefert die anonymisierte Variante.
TextTransform = Callable[[str], str]


@dataclass(frozen=True)
class FormatProcessResult:
    """Resultat einer Datei-Anonymisierung."""

    input_path: Path
    output_path: Path
    segments_processed: int = 0
    segments_skipped: int = 0
    notes: tuple[str, ...] = field(default_factory=tuple)


class FormatHandler(Protocol):
    """Format-spezifische Read/Write/Transform-Strategie."""

    name: str

    def supports(self, path: Path) -> bool: ...

    def process(
        self,
        input_path: Path,
        output_path: Path,
        transform: TextTransform,
    ) -> FormatProcessResult: ...

    def default_output_path(self, input_path: Path, suffix: str = "anon") -> Path: ...


def derive_default_output(input_path: Path, suffix: str = "anon") -> Path:
    """``foo.csv`` → ``foo.anon.csv``."""
    stem = input_path.stem
    return input_path.with_name(f"{stem}.{suffix}{input_path.suffix}")
