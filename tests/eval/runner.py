"""Eval-Runner: lädt Fixtures, lässt die Pseudokrat-Detection-Pipeline
drauf laufen und schreibt einen Score-Report.

Aufruf::

    python -m tests.eval.runner            # Default-Fixtures-Dir, stdout
    python -m tests.eval.runner --json out.json
    python -m tests.eval.runner --fixtures tests/eval/fixtures/lohnkonto_at

Default: alle Fixtures unter ``tests/eval/fixtures/<name>/{input.txt,
expected.json}``.

ML-Detector wird in diesem Lauf **abgeschaltet** — Phase 1 misst nur
die regelbasierten DACH-Recognizer (deterministisch, deshalb ist die
Latte hier ``1.00``). ML-Recall ist Phase 2 (mit Modell-Download).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pseudokrat.anonymizer import Anonymizer
from pseudokrat.recognizers import recognizers_for_store
from pseudokrat.store.key_protector import InMemoryKeyringBackend
from pseudokrat.store.profile import ProfileManager
from tests.eval.fixture_builder import load_expected, load_input_text
from tests.eval.scoring import CategoryScore, Span, aggregate, score_spans

DEFAULT_FIXTURES_DIR = Path(__file__).parent / "fixtures"


@dataclass(frozen=True)
class FixtureResult:
    name: str
    scores: dict[str, CategoryScore]
    predicted_spans: list[Span]
    truth_spans: list[Span]

    @property
    def total(self) -> CategoryScore:
        return aggregate(self.scores.values())


def _build_anonymizer(profile_name: str = "_eval_profile") -> Anonymizer:
    """Baut einen Anonymizer mit nur den DACH-Recognizern (kein ML)."""
    # Eval-Profil in einem Tempdir, damit der Hauptdaten-Ordner unangetastet
    # bleibt und der Lauf reproduzierbar ist.
    tmp = Path(tempfile.mkdtemp(prefix="pseudokrat-eval-"))
    os.environ["PSEUDOKRAT_DATA_DIR"] = str(tmp)
    os.environ["PSEUDOKRAT_DISABLE_ML"] = "1"
    manager = ProfileManager()
    backend = InMemoryKeyringBackend()
    store, audit = manager.open_or_create_simple(profile_name, backend=backend)
    return Anonymizer(
        store=store,
        recognizers=recognizers_for_store(store),
        detector=None,
        audit_log=audit,
        model_version="eval-detector-only",
    )


def evaluate_fixture(directory: Path, anonymizer: Anonymizer) -> FixtureResult:
    text = load_input_text(directory)
    truth = load_expected(directory)
    detected = anonymizer.detect(text)
    pred_spans = [Span(s.start, s.end, s.category) for s in detected]
    scores = score_spans(predicted=pred_spans, truth=truth)
    return FixtureResult(
        name=directory.name,
        scores=scores,
        predicted_spans=pred_spans,
        truth_spans=truth,
    )


def iter_fixture_dirs(root: Path) -> Iterable[Path]:
    for d in sorted(root.iterdir()):
        if d.is_dir() and (d / "input.txt").exists() and (d / "expected.json").exists():
            yield d


def run(fixtures_root: Path) -> list[FixtureResult]:
    anonymizer = _build_anonymizer()
    return [evaluate_fixture(d, anonymizer) for d in iter_fixture_dirs(fixtures_root)]


def aggregate_per_category(results: Iterable[FixtureResult]) -> dict[str, CategoryScore]:
    """Summiere TP/FP/FN über alle Fixtures, ergebe einen Score pro
    Kategorie. Verwendet für Gate-Vergleich."""
    accumulator: dict[str, tuple[int, int, int]] = {}
    for res in results:
        for cat, score in res.scores.items():
            tp, fp, fn = accumulator.get(cat, (0, 0, 0))
            accumulator[cat] = (
                tp + score.true_positives,
                fp + score.false_positives,
                fn + score.false_negatives,
            )
    return {
        cat: CategoryScore(
            category=cat, true_positives=tp, false_positives=fp, false_negatives=fn
        )
        for cat, (tp, fp, fn) in accumulator.items()
    }


def render_report(results: list[FixtureResult]) -> dict[str, Any]:
    per_fixture = []
    for res in results:
        per_fixture.append(
            {
                "name": res.name,
                "totals": {
                    "tp": res.total.true_positives,
                    "fp": res.total.false_positives,
                    "fn": res.total.false_negatives,
                    "precision": round(res.total.precision, 4),
                    "recall": round(res.total.recall, 4),
                    "f1": round(res.total.f1, 4),
                },
                "categories": {
                    cat: {
                        "tp": s.true_positives,
                        "fp": s.false_positives,
                        "fn": s.false_negatives,
                        "precision": round(s.precision, 4),
                        "recall": round(s.recall, 4),
                        "f1": round(s.f1, 4),
                    }
                    for cat, s in sorted(res.scores.items())
                },
            }
        )
    overall = aggregate_per_category(results)
    micro = aggregate(overall.values())
    return {
        "per_fixture": per_fixture,
        "per_category": {
            cat: {
                "tp": s.true_positives,
                "fp": s.false_positives,
                "fn": s.false_negatives,
                "precision": round(s.precision, 4),
                "recall": round(s.recall, 4),
                "f1": round(s.f1, 4),
            }
            for cat, s in sorted(overall.items())
        },
        "totals": {
            "tp": micro.true_positives,
            "fp": micro.false_positives,
            "fn": micro.false_negatives,
            "precision": round(micro.precision, 4),
            "recall": round(micro.recall, 4),
            "f1": round(micro.f1, 4),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pseudokrat Eval-Runner")
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=DEFAULT_FIXTURES_DIR,
        help="Root-Verzeichnis der Fixtures (Default: tests/eval/fixtures).",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="JSON-Report-Pfad (Default: stdout).",
    )
    args = parser.parse_args(argv)

    results = run(args.fixtures)
    report = render_report(results)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.json is None:
        sys.stdout.write(payload + "\n")
    else:
        args.json.write_text(payload, encoding="utf-8")
        print(f"Report geschrieben nach {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
