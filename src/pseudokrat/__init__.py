"""Pseudokrat — Lokale PII-Anonymisierung für DACH-Berufsträger."""

from pseudokrat.anonymizer import AnonymizationResult, Anonymizer
from pseudokrat.deanonymizer import DeanonymizationResult, Deanonymizer

__version__ = "0.1.0"
__all__ = [
    "Anonymizer",
    "AnonymizationResult",
    "Deanonymizer",
    "DeanonymizationResult",
    "__version__",
]
