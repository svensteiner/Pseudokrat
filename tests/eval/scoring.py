"""Span-Level Precision/Recall/F1 für Eval-Fixtures.

Match-Definition: ein erkannter Span ``(start, end, category)`` matcht
einen Ground-Truth-Span genau dann, wenn

* Kategorie identisch (case-insensitive), **und**
* Überlapp ``intersect / union >= 0.5`` (Jaccard).

Damit tolerieren wir kleine Off-By-One-Differenzen (z. B. inklusiver
vs. exklusiver End-Index, mit/ohne führendes Leerzeichen), bestrafen
aber teilweise falsche Spans (z. B. nur den Vornamen statt
„Vorname Nachname").
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    category: str


@dataclass(frozen=True)
class CategoryScore:
    category: str
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 1.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return (2 * p * r) / (p + r) if (p + r) else 0.0


def _jaccard(a: Span, b: Span) -> float:
    inter = max(0, min(a.end, b.end) - max(a.start, b.start))
    union = max(a.end, b.end) - min(a.start, b.start)
    return inter / union if union else 0.0


def _norm_cat(c: str) -> str:
    return c.strip().upper()


def score_spans(
    *,
    predicted: Sequence[Span],
    truth: Sequence[Span],
    jaccard_threshold: float = 0.5,
) -> dict[str, CategoryScore]:
    """Pro Kategorie: TP/FP/FN über Greedy-Matching gegen Ground-Truth.

    Kategorie-übergreifende Cross-Matches (z. B. Predictor sagt PERSON,
    Truth sagt ORG am selben Span) zählen als FP+FN — der Anonymisierer
    hat das Mapping in der falschen Kategorie hinterlegt, das ist ein
    echter Fehler.
    """
    categories: set[str] = {_norm_cat(s.category) for s in (*predicted, *truth)}
    scores: dict[str, CategoryScore] = {}

    for cat in categories:
        preds_cat = [
            Span(s.start, s.end, _norm_cat(s.category))
            for s in predicted
            if _norm_cat(s.category) == cat
        ]
        truth_cat = [
            Span(s.start, s.end, _norm_cat(s.category))
            for s in truth
            if _norm_cat(s.category) == cat
        ]
        matched_truth: set[int] = set()
        tp = 0
        for pred in preds_cat:
            best_idx: int | None = None
            best_iou = jaccard_threshold
            for i, t in enumerate(truth_cat):
                if i in matched_truth:
                    continue
                iou = _jaccard(pred, t)
                if iou >= best_iou:
                    best_iou = iou
                    best_idx = i
            if best_idx is not None:
                matched_truth.add(best_idx)
                tp += 1
        fp = len(preds_cat) - tp
        fn = len(truth_cat) - len(matched_truth)
        scores[cat] = CategoryScore(
            category=cat, true_positives=tp, false_positives=fp, false_negatives=fn
        )
    return scores


def aggregate(scores: Iterable[CategoryScore]) -> CategoryScore:
    """Micro-Aggregation über alle Kategorien (für Gesamt-F1)."""
    tp = sum(s.true_positives for s in scores)
    fp = sum(s.false_positives for s in scores)
    fn = sum(s.false_negatives for s in scores)
    return CategoryScore(
        category="__total__", true_positives=tp, false_positives=fp, false_negatives=fn
    )
