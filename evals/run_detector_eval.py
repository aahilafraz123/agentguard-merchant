"""Measure the manipulation detector's precision and recall on labeled chats (evals/detector_cases.yaml).

    uv run python evals/run_detector_eval.py --keyword-only   # keyword detector only, no API calls
    uv run python evals/run_detector_eval.py                  # keyword + Claude detector (Haiku, ~2 cents)

A chat is flagged when its score reaches Policy().manipulation_threshold, the same cut-off the
guard uses to send a refund to review. Three detectors are scored on the same chats:

    keyword   HeuristicDetector, regexes only
    claude    ClaudeDetector exactly as the guard runs it: max(Haiku score, keyword score)
    haiku     the Haiku score on its own, read from the same API call (no second call)
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import yaml

from agentguard import llm
from agentguard.config import settings
from agentguard.eval_metrics import binary_metrics, cost_usd
from agentguard.guard import ClaudeDetector, HeuristicDetector, Policy
from agentguard.guard.detector import TACTICS

HERE = Path(__file__).parent
SWEEP = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
LABEL = {"keyword": "Keyword", "claude": "Claude (Haiku + keyword)", "haiku": "Haiku alone"}

# ClaudeDetector returns max(Haiku, keyword). To also score Haiku on its own without a second
# call, wrap llm.parse and keep the raw structured output of the call made on this thread.
_last_parse = threading.local()


def _record_raw_score(parse):
    def wrapper(**kwargs):
        response = parse(**kwargs)
        parsed = getattr(response, "parsed_output", None)
        _last_parse.score = parsed.score if parsed is not None else None
        return response

    return wrapper


def score_case(case: dict, keyword: HeuristicDetector, claude: ClaudeDetector | None) -> dict:
    kw = keyword.assess(case["messages"])
    row = {
        "id": case["id"],
        "manipulative": case["manipulative"],
        "tactic": case.get("tactic"),
        "hard_negative": case.get("hard_negative", False),
        "turns": len(case["messages"]),
        "scores": {"keyword": kw.score},
        "tactics": {"keyword": kw.tactics},
    }
    if claude is not None:
        _last_parse.score = None
        assessed = claude.assess(case["messages"])
        row["scores"]["claude"] = assessed.score
        row["tactics"]["claude"] = assessed.tactics
        row["claude_source"] = assessed.source  # "heuristic" means the API call failed
        row["rationale"] = assessed.rationale
        if assessed.source == "llm" and _last_parse.score is not None:
            row["scores"]["haiku"] = round(_last_parse.score, 3)
    return row


def detector_report(rows: list[dict], name: str, threshold: float) -> dict:
    scored = [r for r in rows if name in r["scores"]]
    labels = [r["manipulative"] for r in scored]

    def at(t: float) -> dict:
        return binary_metrics(labels, [r["scores"][name] >= t for r in scored])

    by_tactic = {}
    for tactic in TACTICS:
        hits = [r["scores"][name] >= threshold for r in scored if r["tactic"] == tactic]
        if hits:
            by_tactic[tactic] = {
                "cases": len(hits),
                "caught": sum(hits),
                "recall": round(sum(hits) / len(hits), 3),
            }
    hard = [r for r in scored if r["hard_negative"]]
    return {
        "detector": name,
        "label": LABEL[name],
        "cases": len(scored),
        **at(threshold),
        "recall_by_tactic": by_tactic,
        "hard_negatives": len(hard),
        "hard_negatives_flagged": sum(r["scores"][name] >= threshold for r in hard),
        "sweep": [{"threshold": t, **at(t)} for t in SWEEP],
    }


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.0%}"


def markdown(report: dict) -> str:
    ds = report["detectors"]
    lines = [
        f"### Manipulation detector eval ({report['cases']} labeled chats: "
        f"{report['manipulative']} manipulative, {report['genuine']} genuine, "
        f"{report['hard_negatives']} of them hard negatives)",
        "",
        f"Flagged when score >= {report['threshold']} (`Policy().manipulation_threshold`, the guard's "
        "cut-off). Positive = manipulative.",
        "",
        "| Detector | Precision | Recall | F1 | False-positive rate | TP | FP | FN | TN "
        "| Hard negatives flagged |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for d in ds:
        lines.append(
            f"| {d['label']} | {_pct(d['precision'])} | {_pct(d['recall'])} | {_pct(d['f1'])} | "
            f"{_pct(d['false_positive_rate'])} | {d['tp']} | {d['fp']} | {d['fn']} | {d['tn']} | "
            f"{d['hard_negatives_flagged']}/{d['hard_negatives']} |"
        )
    lines += [
        "",
        "Recall by tactic:",
        "",
        "| Tactic | Cases | " + " | ".join(d["label"] for d in ds) + " |",
        "|---|---|" + "---|" * len(ds),
    ]
    for tactic in TACTICS:
        cells = [ds[0]["recall_by_tactic"].get(tactic)]
        if cells[0] is None:
            continue
        cells += [d["recall_by_tactic"].get(tactic) for d in ds[1:]]
        lines.append(
            f"| {tactic} | {cells[0]['cases']} | "
            + " | ".join(f"{c['caught']}/{c['cases']}" if c else "-" for c in cells)
            + " |"
        )
    lines += [
        "",
        "Threshold sweep (precision / recall):",
        "",
        "| Threshold | " + " | ".join(d["label"] for d in ds) + " |",
        "|---|" + "---|" * len(ds),
    ]
    for i, t in enumerate(SWEEP):
        cells = [f"{_pct(d['sweep'][i]['precision'])} / {_pct(d['sweep'][i]['recall'])}" for d in ds]
        lines.append(f"| {t} | " + " | ".join(cells) + " |")

    threshold = report["threshold"]
    for d in ds:
        name = d["detector"]
        missed = [r for r in report["results"] if r["manipulative"] and r["scores"].get(name, 1) < threshold]
        false_alarms = [
            r for r in report["results"] if not r["manipulative"] and r["scores"].get(name, 0) >= threshold
        ]
        if missed or false_alarms:
            lines += ["", f"{d['label']} errors:", ""]
            lines += [f"- missed `{r['id']}` ({r['tactic']}, score {r['scores'][name]:.2f})" for r in missed]
            lines += [f"- false alarm `{r['id']}` (score {r['scores'][name]:.2f})" for r in false_alarms]
    if report.get("claude_fallbacks"):
        lines += ["", f"Claude calls that failed and fell back to keywords: {report['claude_fallbacks']}"]
    lines += ["", f"API cost of this run: ~${report['cost_usd']:.3f}"]
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--keyword-only", action="store_true", help="skip the Claude detector (no API calls)")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--out", default=str(HERE / "results"))
    args = p.parse_args()

    cases = yaml.safe_load((HERE / "detector_cases.yaml").read_text())
    unknown = {c["tactic"] for c in cases if c["manipulative"]} - set(TACTICS)
    if unknown:
        print(f"Unknown tactics in detector_cases.yaml: {sorted(unknown)}", file=sys.stderr)
        return 2
    if not args.keyword_only and not settings.llm_enabled:
        print("ANTHROPIC_API_KEY is not set; use --keyword-only.", file=sys.stderr)
        return 2

    claude = None
    if not args.keyword_only:
        llm.parse = _record_raw_score(llm.parse)
        claude = ClaudeDetector()
    keyword = HeuristicDetector()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda c: score_case(c, keyword, claude), cases))

    threshold = Policy().manipulation_threshold
    names = ["keyword"] + ([] if args.keyword_only else ["claude", "haiku"])
    cost, usage_detail = cost_usd()
    report = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": None if args.keyword_only else settings.utility_model,
        "threshold": threshold,
        "cases": len(rows),
        "manipulative": sum(r["manipulative"] for r in rows),
        "genuine": sum(not r["manipulative"] for r in rows),
        "hard_negatives": sum(r["hard_negative"] for r in rows),
        "claude_fallbacks": sum(r.get("claude_source") == "heuristic" for r in rows),
        "cost_usd": cost,
        "usage": usage_detail,
        "detectors": [detector_report(rows, n, threshold) for n in names],
        "results": rows,
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "detector_eval.json").write_text(json.dumps(report, indent=2))
    (out / "detector_eval.md").write_text(markdown(report))
    print(markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
