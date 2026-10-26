"""Precision/recall math used by the detector and agent evals."""

import pytest

from agentguard.eval_metrics import binary_metrics, confusion


def test_confusion_counts():
    labels = [True, True, True, False, False, False, False]
    preds = [True, True, False, True, False, False, False]
    assert confusion(labels, preds) == {"tp": 2, "fp": 1, "fn": 1, "tn": 3}


def test_binary_metrics():
    # 8 positives, 6 caught; 12 negatives, 2 false alarms.
    labels = [True] * 8 + [False] * 12
    preds = [True] * 6 + [False] * 2 + [True] * 2 + [False] * 10
    m = binary_metrics(labels, preds)
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (6, 2, 2, 10)
    assert m["precision"] == 0.75
    assert m["recall"] == 0.75
    assert m["f1"] == 0.75
    assert m["false_positive_rate"] == round(2 / 12, 3)


def test_f1_is_harmonic_mean():
    m = binary_metrics([True, True, True, True, False], [True, False, False, False, True])
    p, r = 1 / 2, 1 / 4
    assert m["f1"] == round(2 * p * r / (p + r), 3)


def test_undefined_ratios_are_none_not_zero():
    # Nothing flagged: precision is undefined, recall is 0.
    m = binary_metrics([True, False], [False, False])
    assert m["precision"] is None and m["recall"] == 0.0 and m["false_positive_rate"] == 0.0
    # No positives in the data: recall is undefined.
    m = binary_metrics([False, False], [True, False])
    assert m["recall"] is None and m["precision"] == 0.0 and m["false_positive_rate"] == 0.5


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        confusion([True], [True, False])
