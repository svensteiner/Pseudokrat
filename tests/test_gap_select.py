"""Tests für die PRL Gap-Phase (``tools/gap_select.py``)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import gap_select
from tools.gap_select import (
    CATEGORY_ALIASES,
    Gap,
    GateSpec,
    GateThreshold,
    identify_gaps,
    parse_gate,
    render_next_gap,
)

# ---------- Gate-Parsing -----------------------------------------------------


def test_parse_gate_extracts_tier1_thresholds_and_aliases_org() -> None:
    md = (
        "## Tier-1\n\n"
        "| Kategorie | F1 (min) | Begründung |\n"
        "|---|---|---|\n"
        "| `PERSON` | **0.95** | Personen |\n"
        "| `ORG` | **0.95** | Firmen |\n"
        "| `IBAN` | **1.00** | Mod-97 |\n\n"
        "Falsch-Positiv-Rate über alle Kategorien: `≤ 0.02` (max).\n"
    )
    spec = parse_gate(md)
    assert spec.max_fp_rate == 0.02
    by_cat = {t.category: t.min_f1 for t in spec.thresholds}
    assert by_cat == {"PERSON": 0.95, "COMPANY": 0.95, "IBAN": 1.0}
    assert "ORG" in CATEGORY_ALIASES


def test_parse_gate_handles_real_production_gate_file() -> None:
    """Der echte ``PRODUCTION_READY_GATE.md`` muss parsbar bleiben."""
    md = (gap_select.REPO_ROOT / "PRODUCTION_READY_GATE.md").read_text(encoding="utf-8")
    spec = parse_gate(md)
    by_cat = {t.category: t.min_f1 for t in spec.thresholds}
    assert by_cat["PERSON"] == 0.95
    assert by_cat["COMPANY"] == 0.95  # Gate sagt ORG, intern COMPANY
    assert by_cat["IBAN"] == 1.0
    assert by_cat["ADDRESS"] == 0.9
    assert by_cat["DATE"] == 0.85
    assert spec.max_fp_rate == 0.02


def test_parse_gate_falls_back_to_default_fp_rate_when_missing() -> None:
    md = "| `IBAN` | **1.00** | Mod-97 |\n"
    spec = parse_gate(md)
    assert spec.max_fp_rate == 0.02  # Fallback


# ---------- Helper-Fixtures --------------------------------------------------


def _perfect_score(tp: int = 1) -> dict[str, object]:
    return {"tp": tp, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0}


def _gate(*pairs: tuple[str, float], fp: float = 0.02) -> GateSpec:
    return GateSpec(
        thresholds=tuple(GateThreshold(c, f) for c, f in pairs),
        max_fp_rate=fp,
    )


# ---------- Tier-1 -----------------------------------------------------------


def test_no_gaps_when_eval_is_perfect_and_no_audit() -> None:
    spec = _gate(("IBAN", 1.0), ("COMPANY", 0.95))
    report = {
        "mode": "recognizers-only",
        "per_category": {
            "IBAN": _perfect_score(2),
            "COMPANY": _perfect_score(3),
        },
        "totals": {"tp": 5, "fp": 0, "fn": 0},
    }
    assert identify_gaps(eval_report=report, audit_report=None, gate=spec) == []


def test_gap_for_category_below_threshold_is_severity_one() -> None:
    spec = _gate(("PERSON", 0.95))
    report = {
        "mode": "recognizers-only",
        "per_category": {
            "PERSON": {
                "tp": 3,
                "fp": 1,
                "fn": 2,
                "precision": 0.75,
                "recall": 0.6,
                "f1": 0.6667,
            }
        },
        "totals": {"tp": 3, "fp": 1, "fn": 2},
    }
    gaps = identify_gaps(eval_report=report, audit_report=None, gate=spec)
    assert len(gaps) >= 1
    top = gaps[0]
    assert top.severity == 1
    assert top.tier == "tier-1"
    assert "PERSON" in top.title
    assert top.metadata["category"] == "PERSON"
    assert top.metadata["f1"] == pytest.approx(0.6667)


def test_dominant_recall_error_is_hinted() -> None:
    spec = _gate(("ADDRESS", 0.9))
    report = {
        "mode": "recognizers-only",
        "per_category": {
            "ADDRESS": {
                "tp": 1,
                "fp": 0,
                "fn": 5,
                "precision": 1.0,
                "recall": 0.167,
                "f1": 0.286,
            }
        },
        "totals": {"tp": 1, "fp": 0, "fn": 5},
    }
    gaps = identify_gaps(eval_report=report, audit_report=None, gate=spec)
    assert any("Recall" in g.fix_hint for g in gaps)


def test_dominant_precision_error_is_hinted() -> None:
    spec = _gate(("COMPANY", 0.95))
    report = {
        "mode": "recognizers-only",
        "per_category": {
            "COMPANY": {
                "tp": 1,
                "fp": 5,
                "fn": 0,
                "precision": 0.167,
                "recall": 1.0,
                "f1": 0.286,
            }
        },
        "totals": {"tp": 1, "fp": 5, "fn": 0},
    }
    gaps = identify_gaps(eval_report=report, audit_report=None, gate=spec)
    assert any("Precision" in g.fix_hint for g in gaps)


# ---------- ML-Kategorien im Recognizers-Only-Mode --------------------------


def test_missing_ml_category_in_recognizers_only_mode_is_severity_three() -> None:
    """PERSON/ADDRESS/DATE fehlend → soft warning, nicht harter Block."""
    spec = _gate(("PERSON", 0.95), ("IBAN", 1.0))
    report = {
        "mode": "recognizers-only",
        "per_category": {"IBAN": _perfect_score(2)},
        "totals": {"tp": 2, "fp": 0, "fn": 0},
    }
    gaps = identify_gaps(eval_report=report, audit_report=None, gate=spec)
    # Genau eine Lücke, severity 3
    assert len(gaps) == 1
    assert gaps[0].severity == 3
    assert "PERSON" in gaps[0].title


def test_missing_ml_category_in_with_ml_mode_is_severity_one() -> None:
    """Im ML-Mode ist eine fehlende PERSON-Kategorie ein harter Gate-Fail."""
    spec = _gate(("PERSON", 0.95))
    report = {
        "mode": "with-ml",
        "per_category": {},
        "totals": {"tp": 0, "fp": 0, "fn": 0},
    }
    gaps = identify_gaps(eval_report=report, audit_report=None, gate=spec)
    assert any(g.severity == 1 and "PERSON" in g.title for g in gaps)


def test_missing_non_ml_category_is_severity_one_even_in_recognizers_mode() -> None:
    """IBAN ohne Score ist immer ein Bug, egal in welchem Mode."""
    spec = _gate(("IBAN", 1.0))
    report = {
        "mode": "recognizers-only",
        "per_category": {},
        "totals": {"tp": 0, "fp": 0, "fn": 0},
    }
    gaps = identify_gaps(eval_report=report, audit_report=None, gate=spec)
    assert any(g.severity == 1 and "IBAN" in g.title for g in gaps)


# ---------- FP-Rate ----------------------------------------------------------


def test_global_fp_rate_above_limit_is_gap() -> None:
    spec = _gate(("IBAN", 1.0), fp=0.02)
    report = {
        "mode": "recognizers-only",
        "per_category": {"IBAN": _perfect_score(20)},
        "totals": {"tp": 20, "fp": 5, "fn": 0},  # FP-Rate 0.2 >> 0.02
    }
    gaps = identify_gaps(eval_report=report, audit_report=None, gate=spec)
    assert any(g.tier == "tier-1" and "FP-Rate" in g.title for g in gaps)


def test_no_fp_gap_when_zero_detections() -> None:
    spec = _gate(("IBAN", 1.0), fp=0.02)
    report = {
        "mode": "recognizers-only",
        "per_category": {"IBAN": _perfect_score(0)},
        "totals": {"tp": 0, "fp": 0, "fn": 0},
    }
    gaps = identify_gaps(eval_report=report, audit_report=None, gate=spec)
    assert not any("FP-Rate" in g.title for g in gaps)


# ---------- Audit-Reports ----------------------------------------------------


def test_audit_check_failure_becomes_severity_three_gap() -> None:
    spec = _gate(("IBAN", 1.0))
    eval_rep = {
        "mode": "recognizers-only",
        "per_category": {"IBAN": _perfect_score(1)},
        "totals": {"tp": 1, "fp": 0, "fn": 0},
    }
    audit_rep = {
        "checks": [
            {
                "name": "ruff",
                "status": "fail",
                "stderr_tail": "E501 line too long",
                "stdout_tail": "",
                "extra": {},
            },
            {"name": "mypy", "status": "pass"},
        ],
        "totals": {"pass": 1, "fail": 1, "skipped": 0},
    }
    gaps = identify_gaps(eval_report=eval_rep, audit_report=audit_rep, gate=spec)
    assert len(gaps) == 1
    assert gaps[0].severity == 3
    assert gaps[0].tier == "tier-2"
    assert "ruff" in gaps[0].title
    assert "E501" in gaps[0].detail


def test_trust_boundary_failure_is_tier_three_gap_with_missing_list() -> None:
    spec = _gate()  # keine Tier-1-Schwellen
    eval_rep = {"mode": "recognizers-only", "per_category": {}, "totals": {}}
    audit_rep = {
        "checks": [
            {
                "name": "trust-boundary-coverage",
                "status": "fail",
                "extra": {"missing": ["S3 (Speicher-Hygiene)", "S5 (Audit-Hash)"]},
            }
        ],
        "totals": {"pass": 0, "fail": 1, "skipped": 0},
    }
    gaps = identify_gaps(eval_report=eval_rep, audit_report=audit_rep, gate=spec)
    assert len(gaps) == 1
    assert gaps[0].tier == "tier-3"
    assert "2 offen" in gaps[0].title
    assert "S3" in gaps[0].detail and "S5" in gaps[0].detail


def test_passing_audit_check_yields_no_gap() -> None:
    spec = _gate()
    eval_rep = {"mode": "recognizers-only", "per_category": {}, "totals": {}}
    audit_rep = {
        "checks": [
            {"name": "ruff", "status": "pass"},
            {"name": "pip-audit", "status": "skipped"},
        ],
        "totals": {"pass": 1, "fail": 0, "skipped": 1},
    }
    assert identify_gaps(eval_report=eval_rep, audit_report=audit_rep, gate=spec) == []


# ---------- Sortierung -------------------------------------------------------


def test_gaps_are_sorted_by_severity_ascending() -> None:
    spec = _gate(("PERSON", 0.95), fp=0.02)
    eval_rep = {
        "mode": "recognizers-only",
        "per_category": {
            "PERSON": {
                "tp": 0,
                "fp": 0,
                "fn": 1,
                "precision": 1.0,
                "recall": 0.0,
                "f1": 0.0,
            }
        },
        "totals": {"tp": 0, "fp": 3, "fn": 1},  # FP-Rate 1.0
    }
    audit_rep = {
        "checks": [
            {"name": "ruff", "status": "fail", "stderr_tail": "x"},
        ],
        "totals": {"pass": 0, "fail": 1, "skipped": 0},
    }
    gaps = identify_gaps(eval_report=eval_rep, audit_report=audit_rep, gate=spec)
    sevs = [g.severity for g in gaps]
    assert sevs == sorted(sevs)
    assert gaps[0].severity == 1  # Tier-1-Eval-Defizit zuerst


# ---------- Rendering -------------------------------------------------------


def test_render_empty_gap_list_says_all_clear() -> None:
    spec = _gate(("IBAN", 1.0))
    out = render_next_gap([], mode="recognizers-only", gate=spec)
    assert "Keine offenen Lücken" in out
    assert "recognizers-only" in out


def test_render_single_gap_includes_title_detail_fix() -> None:
    spec = _gate(("IBAN", 1.0))
    gap = Gap(
        severity=1,
        tier="tier-1",
        title="IBAN F1 = 0.50 < 1.0",
        detail="2 FN bei 4 truth-Spans.",
        fix_hint="IBAN-Recognizer überprüfen.",
    )
    out = render_next_gap([gap], mode="recognizers-only", gate=spec)
    assert "## IBAN F1 = 0.50 < 1.0" in out
    assert "2 FN bei 4 truth-Spans." in out
    assert "**Fix-Vorschlag:** IBAN-Recognizer überprüfen." in out


def test_render_multiple_gaps_lists_remaining() -> None:
    spec = _gate(("IBAN", 1.0))
    gaps = [
        Gap(severity=1, tier="tier-1", title="A", detail="d", fix_hint="f"),
        Gap(severity=3, tier="tier-2", title="B", detail="d", fix_hint="f"),
        Gap(severity=3, tier="tier-3", title="C", detail="d", fix_hint="f"),
    ]
    out = render_next_gap(gaps, mode="recognizers-only", gate=spec)
    assert "## A" in out
    assert "Weitere Lücken" in out
    assert "[tier-2, sev 3] B" in out
    assert "[tier-3, sev 3] C" in out


# ---------- CLI -------------------------------------------------------------


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_cli_exit_zero_when_no_gaps(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    eval_path = tmp_path / "eval.json"
    _write_json(
        eval_path,
        {
            "mode": "recognizers-only",
            "per_category": {"IBAN": _perfect_score(1)},
            "totals": {"tp": 1, "fp": 0, "fn": 0},
        },
    )
    gate_path = tmp_path / "gate.md"
    gate_path.write_text(
        "| `IBAN` | **1.00** | Mod-97 |\nFalsch-Positiv-Rate `≤ 0.02` (max).\n",
        encoding="utf-8",
    )
    rc = gap_select.main(["--eval", str(eval_path), "--gate", str(gate_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Keine offenen Lücken" in out


def test_cli_exit_nonzero_writes_output_file(tmp_path: Path) -> None:
    eval_path = tmp_path / "eval.json"
    _write_json(
        eval_path,
        {
            "mode": "recognizers-only",
            "per_category": {
                "IBAN": {
                    "tp": 0,
                    "fp": 0,
                    "fn": 1,
                    "precision": 1.0,
                    "recall": 0.0,
                    "f1": 0.0,
                }
            },
            "totals": {"tp": 0, "fp": 0, "fn": 1},
        },
    )
    gate_path = tmp_path / "gate.md"
    gate_path.write_text(
        "| `IBAN` | **1.00** | Mod-97 |\nFalsch-Positiv-Rate `≤ 0.02` (max).\n",
        encoding="utf-8",
    )
    out_path = tmp_path / "next_gap.md"
    rc = gap_select.main(
        [
            "--eval",
            str(eval_path),
            "--gate",
            str(gate_path),
            "--output",
            str(out_path),
        ]
    )
    assert rc == 1
    body = out_path.read_text(encoding="utf-8")
    assert "IBAN" in body
    assert "F1" in body


def test_cli_combines_audit_report(tmp_path: Path) -> None:
    eval_path = tmp_path / "eval.json"
    _write_json(
        eval_path,
        {
            "mode": "recognizers-only",
            "per_category": {"IBAN": _perfect_score(1)},
            "totals": {"tp": 1, "fp": 0, "fn": 0},
        },
    )
    audit_path = tmp_path / "audit.json"
    _write_json(
        audit_path,
        {
            "checks": [
                {
                    "name": "mypy",
                    "status": "fail",
                    "stderr_tail": "error: incompatible types",
                    "stdout_tail": "",
                    "extra": {},
                }
            ],
            "totals": {"pass": 0, "fail": 1, "skipped": 0},
        },
    )
    gate_path = tmp_path / "gate.md"
    gate_path.write_text(
        "| `IBAN` | **1.00** | Mod-97 |\nFalsch-Positiv-Rate `≤ 0.02`.\n",
        encoding="utf-8",
    )
    out_path = tmp_path / "next_gap.md"
    rc = gap_select.main(
        [
            "--eval",
            str(eval_path),
            "--audit",
            str(audit_path),
            "--gate",
            str(gate_path),
            "--output",
            str(out_path),
        ]
    )
    assert rc == 1
    body = out_path.read_text(encoding="utf-8")
    assert "mypy" in body
