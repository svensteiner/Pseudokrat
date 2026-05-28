"""Fixture-Builder: aus Template + Synth-Werten ein (input.txt + expected.json)-Paar.

Hand-Berechnung von Spans ist fehleranfällig. Stattdessen definieren wir
Fixtures als Template mit ``{Slot}``-Platzhaltern und einer Slot-Tabelle.
Der Builder substituiert, berechnet exakt die Offsets, und schreibt
beides reproduzierbar auf Disk.

Beispiel::

    builder = FixtureBuilder(seed=42)
    builder.add_slot("dn_name", "Anna Beispielsohn", "PERSON")
    builder.add_slot("iban", generate_at_iban(rng), "IBAN")
    text, spans = builder.render(
        "Dienstnehmer: {dn_name}\\nGehalt-IBAN: {iban}"
    )
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from tests.eval.scoring import Span


@dataclass
class FixtureBuilder:
    """Sammelt Slots und rendert eine Fixture mit ausgerechneten Spans."""

    slots: dict[str, tuple[str, str]] = field(default_factory=dict)

    def add_slot(self, key: str, value: str, category: str) -> None:
        """Fügt einen substituierbaren Slot hinzu.

        ``key`` ist der Platzhalter-Name (``{key}`` im Template). ``value``
        wird in den Text eingesetzt. ``category`` ist die PII-Kategorie für
        die Ground-Truth.

        Doppelte Keys sind erlaubt — sie produzieren mehrere Spans im
        Output (z. B. wenn derselbe Name dreimal im Text vorkommt).
        """
        self.slots[key] = (value, category)

    def render(self, template: str) -> tuple[str, list[Span]]:
        """Substituiere Slots im Template, berechne Spans pro Vorkommen.

        Wenn ein Slot mehrfach im Template steht (``{name}`` zweimal),
        werden alle Vorkommen ersetzt und für jedes ein Span erzeugt.
        """
        # Wir bauen den Output in einem Pass auf, damit die Offsets exakt
        # sind. Standard-`str.format` würde uns die Positionen nicht
        # liefern.
        output_parts: list[str] = []
        spans: list[Span] = []
        cursor = 0
        i = 0
        while i < len(template):
            ch = template[i]
            if ch == "{":
                # Finde schließendes }
                close = template.find("}", i)
                if close == -1:
                    raise ValueError(f"Offene {{-Klammer an Position {i}")
                key = template[i + 1 : close]
                if key not in self.slots:
                    raise KeyError(f"Slot {{ {key} }} nicht im Builder definiert.")
                value, category = self.slots[key]
                output_parts.append(value)
                spans.append(
                    Span(start=cursor, end=cursor + len(value), category=category)
                )
                cursor += len(value)
                i = close + 1
            else:
                output_parts.append(ch)
                cursor += 1
                i += 1
        return "".join(output_parts), spans

    def write_fixture(
        self,
        *,
        directory: Path,
        template: str,
        description: str,
        seed: int | None = None,
    ) -> None:
        """Schreibe ``input.txt`` und ``expected.json`` ins Zielverzeichnis."""
        text, spans = self.render(template)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "input.txt").write_text(text, encoding="utf-8")
        expected = {
            "description": description,
            "seed": seed,
            "spans": [
                {
                    "start": s.start,
                    "end": s.end,
                    "category": s.category,
                    "text": text[s.start : s.end],
                }
                for s in spans
            ],
        }
        (directory / "expected.json").write_text(
            json.dumps(expected, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def load_expected(directory: Path) -> list[Span]:
    """Lade Ground-Truth-Spans aus ``expected.json``."""
    data = json.loads((directory / "expected.json").read_text(encoding="utf-8"))
    return [Span(s["start"], s["end"], s["category"]) for s in data["spans"]]


def load_input_text(directory: Path) -> str:
    return (directory / "input.txt").read_text(encoding="utf-8")
