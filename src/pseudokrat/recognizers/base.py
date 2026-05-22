"""Basis-Protokoll und Span-Datentyp."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Span:
    """Eine erkannte PII-Stelle in einem Text."""

    start: int
    end: int
    category: str
    text: str
    score: float

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError(f"Ungültiger Span-Bereich: {self.start}..{self.end}")
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"Score muss in [0,1] liegen, war {self.score}")


class Recognizer(Protocol):
    """Schnittstelle für alle Recognizer."""

    name: str

    def analyze(self, text: str) -> list[Span]:  # pragma: no cover - protocol
        ...
