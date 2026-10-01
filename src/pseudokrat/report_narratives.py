"""Reviewed conditional prose from grounded facts, without model execution."""

from __future__ import annotations

import operator
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from pseudokrat.ki_office import ProjectError
from pseudokrat.report_tables import FIELD_PATTERN

_OPS = {"eq": operator.eq, "ne": operator.ne, "lt": operator.lt,
        "le": operator.le, "gt": operator.gt, "ge": operator.ge}


def _require(condition: bool) -> None:
    if not condition:
        raise ProjectError("Textregel unvollständig, mehrdeutig oder nicht unterstützt. Lokal prüfen.")


def compile_narratives(spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Separate v3 prose definitions from the existing v1/v2 source mapping."""
    _require(isinstance(spec, dict))
    if spec.get("version") != 3:
        return spec, {}
    _require(type(spec["version"]) is int)
    required = {"version", "reviewed", "template_sha256", "headers", "fields", "narratives"}
    _require(required <= set(spec) <= required | {"tables"})
    narratives = spec["narratives"]
    _require(isinstance(narratives, dict) and 1 <= len(narratives) <= 200)
    _require(isinstance(spec["fields"], dict))
    for name in narratives:
        _require(isinstance(name, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name) is not None)
        _require(name not in spec["fields"] and not name.startswith("__tbl_"))
        _require(not any(k.startswith(name + ".") for k in spec["fields"]))
        _require(name not in spec.get("tables", {}))
    compiled = {k: v for k, v in spec.items() if k != "narratives"}
    compiled["version"] = 2 if "tables" in compiled else 1
    return compiled, narratives


def _number(value: Any) -> Decimal:
    _require(isinstance(value, str) and 1 <= len(value) <= 64)
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ProjectError("Textregel benötigt eine gültige Dezimalzahl.") from exc
    _require(number.is_finite() and abs(number.adjusted()) <= 100)
    return number


def _validate_template(text: Any, facts: dict[str, Any], used: set[str]) -> str:
    _require(isinstance(text, str) and 1 <= len(text) <= 20_000)
    remainder = FIELD_PATTERN.sub("", text)
    _require("{{" not in remainder and "}}" not in remainder)
    references = set(FIELD_PATTERN.findall(text))
    _require(references <= set(facts))
    used.update(references)
    return str(text)


def render_narratives(definitions: dict[str, Any], facts: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    """Validate every branch; reject overlapping conditions instead of guessing."""
    result = {}
    all_used: set[str] = set()
    for name, definition in definitions.items():
        _require(isinstance(definition, dict))
        _require(set(definition) in ({"template"}, {"cases", "otherwise"}))
        used: set[str] = set()

        checks = []
        selected: int | str = "template"
        if "template" in definition:
            template = _validate_template(definition["template"], facts, used)
        else:
            cases = definition["cases"]
            _require(isinstance(cases, list) and 1 <= len(cases) <= 30)
            template = _validate_template(definition["otherwise"], facts, used)
            selected = "otherwise"
            matches = []
            for index, case in enumerate(cases):
                _require(isinstance(case, dict) and set(case) == {"field", "op", "value", "template"})
                field, op = case["field"], case["op"]
                _require(isinstance(field, str) and field in facts and isinstance(op, str) and op in _OPS)
                actual, threshold = _number(facts[field]["exact_value"]), _number(case["value"])
                branch = _validate_template(case["template"], facts, used)
                used.add(field)
                matched = _OPS[op](actual, threshold)
                checks.append({"field": field, "op": op, "threshold": str(threshold), "actual": str(actual), "matched": matched})
                if matched:
                    matches.append((index, branch))
            _require(len(matches) <= 1)
            if matches:
                selected, template = matches[0]
        _require(bool(used))
        for field in used:
            _require("{{" not in facts[field]["text"] and "}}" not in facts[field]["text"])
        text = FIELD_PATTERN.sub(lambda match: facts[match[1]]["text"], template)
        _require(len(text) <= 100_000)
        result[name] = {"text": text, "selected_branch": selected, "template": template,
                        "conditions": checks, "inputs": sorted(used)}
        all_used.update(used)
    return result, all_used
