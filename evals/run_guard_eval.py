"""Score AgentGuard's decisions on labeled refund requests (evals/guard_cases.yaml).

    uv run python evals/run_guard_eval.py            # keyword detector, no API calls (CI)
    uv run python evals/run_guard_eval.py --llm      # Claude manipulation detector

Every case runs in a fresh PayPal simulator seeded with the demo shop, so results are
deterministic apart from the optional LLM detector.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import yaml

from agentguard.demo_world import seed
from agentguard.guard import (
    AgentGuard,
    ClaudeDetector,
    HeuristicDetector,
    Policy,
    RefundRequest,
    SessionContext,
)
from agentguard.paypal import PayPalSimulator
from agentguard.store import Store

HERE = Path(__file__).parent
OUTCOMES = ["allow", "escalate", "block"]


def _request(spec: dict, world) -> tuple[RefundRequest, SessionContext]:
    order = world.orders.get(spec["order"], spec["order"])
    messages = spec.get("messages", [])
    return (
        RefundRequest(
            order_id=order,
            amount=Decimal(str(spec["amount"])),
            reason=spec["reason"],
            customer_claim=messages[-1] if messages else "",
        ),
        SessionContext(
            session_id=spec.get("id", "setup"), customer_id=spec["customer"], customer_messages=messages
        ),
    )


def run_case(case: dict, detector) -> dict:
    paypal, store = PayPalSimulator(), Store(":memory:")
    world = seed(paypal, store)
    guard = AgentGuard(paypal, store, detector)
    if case.get("policy"):
        guard.set_policy(Policy(**case["policy"]))
    for prior in case.get("setup", []):
        guard.submit(*_request(prior, world))
    decision = guard.submit(*_request(case, world))
    actual = decision.outcome.value
    return {
        "id": case["id"],
        "title": case["title"],
        "category": case["category"],
        "expected": case["expect"],
        "actual": actual,
        "pass": actual == case["expect"],
        "money_moved": decision.status == "executed",
        "failed_checks": [c.check for c in decision.failed_checks],
        "summary": decision.summary,
        "risk": round(decision.risk.score, 2),
    }


def summarize(results: list[dict], detector_name: str) -> dict:
    confusion: dict[str, Counter] = defaultdict(Counter)
    for r in results:
        confusion[r["expected"]][r["actual"]] += 1
    by_category = {}
    for cat in ("legit", "review", "attack"):
        rows = [r for r in results if r["category"] == cat]
        by_category[cat] = {"cases": len(rows), "passed": sum(r["pass"] for r in rows)}
    attacks = [r for r in results if r["category"] == "attack"]
    legit = [r for r in results if r["category"] == "legit"]
    passed = sum(r["pass"] for r in results)
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "detector": detector_name,
        "cases": len(results),
        "passed": passed,
        "accuracy": round(passed / len(results), 3),
        "attacks_auto_refunded": sum(r["money_moved"] for r in attacks),
        "legit_refused": sum(r["actual"] == "block" for r in legit),
        "by_category": by_category,
        "confusion": {e: {a: confusion[e][a] for a in OUTCOMES} for e in OUTCOMES},
        "results": results,
    }


def markdown(report: dict) -> str:
    lines = [
        f"### Guard eval ({report['cases']} labeled requests, {report['detector']} detector)",
        "",
        f"- Correct decision: **{report['passed']}/{report['cases']}** ({report['accuracy']:.0%})",
        f"- Attacks that moved money automatically: **{report['attacks_auto_refunded']}**",
        f"- Legitimate requests refused outright: **{report['legit_refused']}**",
        "",
        "| Expected \\ Actual | allow | escalate | block |",
        "|---|---|---|---|",
    ]
    for e in OUTCOMES:
        row = report["confusion"][e]
        lines.append(f"| **{e}** | {row['allow']} | {row['escalate']} | {row['block']} |")
    misses = [r for r in report["results"] if not r["pass"]]
    if misses:
        lines += ["", "Misses:", ""]
        lines += [
            f"- `{r['id']}`: expected {r['expected']}, got {r['actual']} ({r['summary']})" for r in misses
        ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm", action="store_true", help="use the Claude manipulation detector")
    parser.add_argument("--out", default=str(HERE / "results"))
    args = parser.parse_args()

    cases = yaml.safe_load((HERE / "guard_cases.yaml").read_text())
    detector = ClaudeDetector() if args.llm else HeuristicDetector()
    results = [run_case(c, detector) for c in cases]
    report = summarize(results, "claude" if args.llm else "keyword")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "guard_eval.json").write_text(json.dumps(report, indent=2))
    (out / "guard_eval.md").write_text(markdown(report))
    print(markdown(report))
    return 0 if report["attacks_auto_refunded"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
