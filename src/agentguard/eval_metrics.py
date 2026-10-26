"""Binary classification metrics and API cost accounting shared by the eval scripts in evals/."""

from __future__ import annotations

from collections.abc import Sequence

from . import llm

PRICES = {  # USD per million tokens (input, output)
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}


def confusion(labels: Sequence[bool], predictions: Sequence[bool]) -> dict[str, int]:
    """Counts of true/false positives/negatives. `labels` is the ground truth."""
    if len(labels) != len(predictions):
        raise ValueError("labels and predictions differ in length")
    pairs = list(zip(labels, predictions, strict=True))
    return {
        "tp": sum(y and p for y, p in pairs),
        "fp": sum(not y and p for y, p in pairs),
        "fn": sum(y and not p for y, p in pairs),
        "tn": sum(not y and not p for y, p in pairs),
    }


def _ratio(n: int, d: int) -> float | None:
    # None when the ratio is undefined (e.g. precision with nothing flagged), never a made-up 0 or 1.
    return round(n / d, 3) if d else None


def binary_metrics(labels: Sequence[bool], predictions: Sequence[bool]) -> dict:
    """Precision, recall, F1 and false-positive rate, plus the confusion counts behind them."""
    c = confusion(labels, predictions)
    precision = _ratio(c["tp"], c["tp"] + c["fp"])
    recall = _ratio(c["tp"], c["tp"] + c["fn"])
    f1 = _ratio(2 * c["tp"], 2 * c["tp"] + c["fp"] + c["fn"])
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": _ratio(c["fp"], c["fp"] + c["tn"]),
        **c,
    }


def cost_usd() -> tuple[float, dict]:
    """Cost of every Claude call made so far in this process, from `llm.usage`."""
    total, detail = 0.0, {}
    for (model, kind), n in llm.usage.items():
        detail.setdefault(model, {})[kind] = n
    for model, d in detail.items():
        pin, pout = PRICES.get(model, (0.0, 0.0))
        total += d.get("input", 0) / 1e6 * pin + d.get("output", 0) / 1e6 * pout
    return round(total, 4), detail
