"""Eval-Runner: lädt Fixtures, lässt die Pseudokrat-Detection-Pipeline
drauf laufen und schreibt einen Score-Report.

Aufruf::

    python -m tests.eval.runner                  # nur Recognizer, kein ML
    python -m tests.eval.runner --with-ml        # plus Privacy-Filter
    python -m tests.eval.runner --json out.json

Default: alle Fixtures unter ``tests/eval/fixtures/<name>/{input.txt,
expected.json}``.

**Zwei Eval-Modi:**

* ``--with-ml`` aus (Default) → nur regelbasierte DACH-Recognizer.
  Erwartung: F1=1.00 für alle deterministischen Kategorien (IBAN, SVNR,
  TAX_ID, UID, AHV, EMAIL, PHONE, COMPANY, BIC). ML-Kategorien (PERSON,
  ADDRESS, DATE) bleiben zwingend 0 — fließt in den Gap-Report.

* ``--with-ml`` an → Privacy-Filter-Modell wird geladen (falls gecached;
  sonst klare Fehlermeldung mit Download-Hinweis). Misst zusätzlich
  PERSON/ADDRESS/DATE-Recall.
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
from pseudokrat.config import Settings
from pseudokrat.pii.model_install import model_status
from pseudokrat.pii.privacy_filter import PIIDetector, PrivacyFilterDetector
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


class ModelNotCachedError(RuntimeError):
    """``--with-ml`` angefordert, aber das Privacy-Filter-Modell ist
    nicht im Cache. Der Runner soll **nicht** automatisch
    nachdownloaden (3 GB!), sondern dem Aufrufer klar sagen, was zu tun
    ist."""


def _build_anonymizer(
    *,
    profile_name: str = "_eval_profile",
    with_ml: bool = False,
) -> Anonymizer:
    """Baut einen Anonymizer mit DACH-Recognizern, optional plus ML.

    Eval-Profil in einem Tempdir, damit der Hauptdaten-Ordner unangetastet
    bleibt und der Lauf reproduzierbar ist.

    ``with_ml=True`` lädt den ``PrivacyFilterDetector``. Wenn das Modell
    nicht im Cache liegt, wirft die Funktion :class:`ModelNotCachedError`
    statt einen Multi-GB-Download anzustoßen — der Eval-Loop soll
    bewusst entscheiden, ob er das Modell vorab installiert oder den
    ML-Lauf überspringt.
    """
    # Eval-Profil in einem Tempdir, damit der Hauptdaten-Ordner unangetastet
    # bleibt und der Lauf reproduzierbar ist.
    tmp = Path(tempfile.mkdtemp(prefix="pseudokrat-eval-"))
    os.environ["PSEUDOKRAT_DATA_DIR"] = str(tmp)
    # Beim ML-Modus PSEUDOKRAT_DISABLE_ML NICHT setzen — der Detector
    # läuft sonst durch den Null-Pfad.
    if with_ml:
        os.environ.pop("PSEUDOKRAT_DISABLE_ML", None)
    else:
        os.environ["PSEUDOKRAT_DISABLE_ML"] = "1"

    manager = ProfileManager()
    backend = InMemoryKeyringBackend()
    store, audit = manager.open_or_create_simple(profile_name, backend=backend)

    detector: PIIDetector | None
    model_version: str
    if with_ml:
        settings = Settings.load()
        status = model_status(settings)
        if not status.is_present:
            raise ModelNotCachedError(
                "Privacy-Filter-Modell ist nicht im Cache.\n"
                f"  Erwartet unter: {status.cache_dir}\n"
                f"  Aktuelle Größe: {status.gigabytes_on_disk:.2f} GB "
                f"(Floor: 0.10 GB).\n"
                "  Vorabinstallation: pseudokrat model download\n"
                "  Oder ohne --with-ml laufen lassen (nur Recognizer)."
            )
        detector = PrivacyFilterDetector(
            model_id=settings.model_id, cache_dir=str(settings.model_cache_dir)
        )
        model_version = f"ml:{settings.model_id}"
    else:
        detector = None  # Anonymizer akzeptiert None; verwendet dann keinen ML-Detektor
        model_version = "eval-detector-only"

    return Anonymizer(
        store=store,
        recognizers=recognizers_for_store(store),
        detector=detector,
        audit_log=audit,
        model_version=model_version,
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


def run(fixtures_root: Path, *, with_ml: bool = False) -> list[FixtureResult]:
    anonymizer = _build_anonymizer(with_ml=with_ml)
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
    parser.add_argument(
        "--with-ml",
        action="store_true",
        help=(
            "Zusätzlich den Privacy-Filter-ML-Detector laufen lassen "
            "(misst PERSON/ADDRESS/DATE). Modell muss vorab via "
            "'pseudokrat model download' gecached sein."
        ),
    )
    args = parser.parse_args(argv)

    try:
        results = run(args.fixtures, with_ml=args.with_ml)
    except ModelNotCachedError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    report = render_report(results)
    report["mode"] = "with-ml" if args.with_ml else "recognizers-only"
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.json is None:
        sys.stdout.write(payload + "\n")
    else:
        args.json.write_text(payload, encoding="utf-8")
        print(f"Report geschrieben nach {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
