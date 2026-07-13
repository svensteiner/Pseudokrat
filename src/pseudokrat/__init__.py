"""Pseudokrat — Lokale PII-Anonymisierung für DACH-Berufsträger."""

__version__ = "0.1.0"
__all__ = [
    "Anonymizer",
    "AnonymizationResult",
    "Deanonymizer",
    "DeanonymizationResult",
    "__version__",
]


def __getattr__(name: str) -> object:
    if name in {"Anonymizer", "AnonymizationResult"}:
        from pseudokrat.anonymizer import AnonymizationResult, Anonymizer

        return {"Anonymizer": Anonymizer, "AnonymizationResult": AnonymizationResult}[name]
    if name in {"Deanonymizer", "DeanonymizationResult"}:
        from pseudokrat.deanonymizer import DeanonymizationResult, Deanonymizer

        return {"Deanonymizer": Deanonymizer, "DeanonymizationResult": DeanonymizationResult}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
