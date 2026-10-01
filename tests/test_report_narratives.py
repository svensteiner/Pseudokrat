"""Conditional prose must remain grounded, unambiguous and auditable."""

import pytest

from pseudokrat.ki_office import ProjectError
from pseudokrat.report_narratives import compile_narratives, render_narratives


def rules():
    return {
        "assessment": {
            "cases": [
                {
                    "field": "amount",
                    "op": "gt",
                    "value": "0",
                    "template": "Positiv: {{ amount }} EUR.",
                },
                {
                    "field": "amount",
                    "op": "lt",
                    "value": "0",
                    "template": "Negativ: {{ amount }} EUR.",
                },
            ],
            "otherwise": "Ausgeglichen: {{ amount }} EUR.",
        }
    }


@pytest.mark.parametrize(
    "value,text,branch",
    [("12.50", "Positiv", 0), ("-3.25", "Negativ", 1), ("0", "Ausgeglichen", "otherwise")],
)
def test_numeric_branch_and_provenance(value, text, branch):
    result, used = render_narratives(
        rules(), {"amount": {"text": value.replace(".", ","), "exact_value": value}}
    )
    assert result["assessment"]["text"] == f"{text}: {value.replace('.', ',')} EUR."
    assert result["assessment"]["selected_branch"] == branch
    assert result["assessment"]["inputs"] == ["amount"]
    assert used == {"amount"}


def test_overlapping_rules_are_rejected():
    definitions = rules()
    definitions["assessment"]["cases"][1]["op"] = "ge"
    with pytest.raises(ProjectError):
        render_narratives(definitions, {"amount": {"text": "1", "exact_value": "1"}})


@pytest.mark.parametrize("value", [None, "NaN", "Infinity", "abc", True, 0])
def test_non_numeric_facts_cannot_select_branch(value):
    with pytest.raises(ProjectError):
        render_narratives(rules(), {"amount": {"text": "source", "exact_value": value}})


def test_missing_reference_in_unselected_branch_is_rejected():
    definitions = rules()
    definitions["assessment"]["otherwise"] = "{{ unknown }}"
    with pytest.raises(ProjectError):
        render_narratives(definitions, {"amount": {"text": "1", "exact_value": "1"}})


@pytest.mark.parametrize("text", ["{{ missing }}", "{{ amount", "{{ amount }} {{ assessment }}"])
def test_unknown_recursive_or_malformed_placeholder_is_rejected(text):
    with pytest.raises(ProjectError):
        render_narratives(
            {"assessment": {"template": text}}, {"amount": {"text": "1", "exact_value": "1"}}
        )


def test_narrative_name_cannot_overwrite_source_fact():
    with pytest.raises(ProjectError):
        compile_narratives(
            {
                "version": 3,
                "reviewed": True,
                "template_sha256": "hash",
                "headers": {},
                "fields": {"assessment": {}},
                "narratives": rules(),
            }
        )
