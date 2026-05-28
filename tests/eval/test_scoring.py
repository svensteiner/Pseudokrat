"""Validiert das Span-Level-Scoring."""

from __future__ import annotations

from tests.eval.scoring import Span, aggregate, score_spans


def test_perfect_match_yields_f1_one() -> None:
    truth = [Span(0, 10, "PERSON"), Span(20, 30, "IBAN")]
    pred = list(truth)
    s = score_spans(predicted=pred, truth=truth)
    assert s["PERSON"].f1 == 1.0
    assert s["IBAN"].f1 == 1.0


def test_missing_prediction_counts_as_false_negative() -> None:
    truth = [Span(0, 10, "PERSON")]
    pred: list[Span] = []
    s = score_spans(predicted=pred, truth=truth)
    assert s["PERSON"].recall == 0.0
    assert s["PERSON"].false_negatives == 1


def test_extra_prediction_counts_as_false_positive() -> None:
    truth: list[Span] = []
    pred = [Span(0, 10, "PERSON")]
    s = score_spans(predicted=pred, truth=truth)
    assert s["PERSON"].precision == 0.0
    assert s["PERSON"].false_positives == 1


def test_offset_within_jaccard_threshold_matches() -> None:
    truth = [Span(0, 10, "PERSON")]
    pred = [Span(1, 11, "PERSON")]  # off-by-one beidseitig → Jaccard 8/10 = 0.8
    s = score_spans(predicted=pred, truth=truth)
    assert s["PERSON"].f1 == 1.0


def test_offset_below_jaccard_threshold_misses() -> None:
    truth = [Span(0, 10, "PERSON")]
    pred = [Span(0, 3, "PERSON")]  # Jaccard 3/10 = 0.3 < 0.5
    s = score_spans(predicted=pred, truth=truth)
    assert s["PERSON"].false_positives == 1
    assert s["PERSON"].false_negatives == 1


def test_wrong_category_counts_as_both_fp_and_fn() -> None:
    truth = [Span(0, 10, "ORG")]
    pred = [Span(0, 10, "PERSON")]
    s = score_spans(predicted=pred, truth=truth)
    assert s["ORG"].false_negatives == 1
    assert s["PERSON"].false_positives == 1


def test_aggregate_micro_f1() -> None:
    truth = [Span(0, 10, "PERSON"), Span(20, 30, "IBAN"), Span(40, 50, "EMAIL")]
    pred = [Span(0, 10, "PERSON"), Span(20, 30, "IBAN")]  # EMAIL fehlt
    scores = score_spans(predicted=pred, truth=truth)
    total = aggregate(scores.values())
    assert total.true_positives == 2
    assert total.false_negatives == 1
    assert total.precision == 1.0
    assert abs(total.recall - 2 / 3) < 1e-9


def test_case_insensitive_category() -> None:
    truth = [Span(0, 10, "person")]
    pred = [Span(0, 10, "PERSON")]
    s = score_spans(predicted=pred, truth=truth)
    assert s["PERSON"].f1 == 1.0
