"""Allow only inert pagination fields in confidential local Word templates."""

from __future__ import annotations

import re
from typing import Any

from pseudokrat.ki_office import ProjectError, W

_PAGINATION = re.compile(
    r"\s*(PAGE|NUMPAGES|SECTION|SECTIONPAGES)(?:\s+\\\*\s+(?:MERGEFORMAT|CHARFORMAT|Arabic|ROMAN|ALPHABETIC)){0,3}\s*",
    re.IGNORECASE,
)


def _code(text: str) -> str:
    match = _PAGINATION.fullmatch(text) if len(text) <= 256 else None
    if match is None:
        raise ProjectError("Nur lokale Seiten- und Abschnittszahlfelder werden unterstützt.")
    return match[1].upper()


def inspect_fields(roots: dict[str, Any]) -> tuple[list[str], set[Any]]:
    """Validate complete fields and identify cached text that must not be filled."""
    codes = []
    protected: set[Any] = set()
    for root in roots.values():
        active = None
        instruction = ""
        separated = False
        for element in root.iter():
            if element.tag == f"{{{W}}}fldSimple":
                if active is not None or any(
                    child.tag in {f"{{{W}}}{tag}" for tag in ("fldSimple", "fldChar", "instrText")}
                    for child in element.iterdescendants()
                ):
                    raise ProjectError("Verschachtelte Word-Felder werden nicht unterstützt.")
                codes.append(_code(element.get(f"{{{W}}}instr", "")))
                protected.update(element.iter(f"{{{W}}}t"))
            elif element.tag == f"{{{W}}}fldChar":
                if len(element):
                    raise ProjectError("Zusätzliche Word-Felddaten werden nicht unterstützt.")
                kind = element.get(f"{{{W}}}fldCharType")
                if kind == "begin" and active is None:
                    active, instruction, separated = element, "", False
                elif kind == "separate" and active is not None and not separated:
                    _code(instruction)
                    separated = True
                elif kind == "end" and active is not None:
                    codes.append(_code(instruction))
                    active = None
                else:
                    raise ProjectError("Unvollständige oder verschachtelte Word-Feldstruktur.")
            elif element.tag == f"{{{W}}}instrText":
                if active is None or separated:
                    raise ProjectError("Word-Feldanweisung steht außerhalb eines gültigen Feldes.")
                instruction += element.text or ""
                if len(instruction) > 256:
                    raise ProjectError("Word-Feldanweisung überschreitet die Begrenzung.")
            elif element.tag == f"{{{W}}}t" and active is not None:
                if not separated:
                    raise ProjectError(
                        "Nicht unterstützter Text innerhalb einer Word-Feldanweisung."
                    )
                protected.add(element)
        if active is not None:
            raise ProjectError("Nicht abgeschlossenes Word-Feld.")
        cached = "".join(node.text or "" for node in root.iter(f"{{{W}}}t") if node in protected)
        if "{{" in cached or "}}" in cached:
            raise ProjectError(
                "Berichtsplatzhalter in überschreibbaren Word-Feldergebnissen sind nicht erlaubt."
            )
    return codes, protected


def text_segments(paragraph: Any, protected: set[Any]) -> list[list[Any]]:
    """Never concatenate a placeholder across an automatic field boundary."""
    segments: list[list[Any]] = []
    nodes: list[Any] = []
    for element in paragraph.iter():
        if element in protected or element.tag in {
            f"{{{W}}}{tag}" for tag in ("fldChar", "fldSimple", "instrText")
        }:
            if nodes:
                segments.append(nodes)
                nodes = []
        elif element.tag == f"{{{W}}}t":
            nodes.append(element)
    if nodes:
        segments.append(nodes)
    return segments
