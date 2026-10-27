"""Time AgentGuard refund decisions: how long the guard adds before a refund can go to PayPal.

    uv run python scripts/bench_latency.py offline -n 300   # simulator + keyword detector, no network
    uv run python scripts/bench_latency.py sandbox -n 20    # PayPal sandbox reads + Claude Haiku detector

Every request is a signed-in customer asking for someone else's order, so the ownership check
blocks it and no refund is ever attempted (refund_capture is also stubbed to raise). The full
pipeline still runs: load evidence from PayPal, assess risk, run the nine checks, record. The
sandbox mode uses the demo shop's sandbox orders, so run the app once first to seed them, and
costs about a tenth of a cent per decision in Haiku calls.

Writes evals/results/latency_<mode>.json and .md.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from agentguard.config import settings
from agentguard.demo_world import load_world, seed
from agentguard.guard import AgentGuard, ClaudeDetector, HeuristicDetector, RefundRequest, SessionContext
from agentguard.paypal import PayPalRestClient, PayPalSimulator
from agentguard.store import Store

OUT = Path(__file__).parent.parent / "evals" / "results"
MESSAGE = "Hi, my sampler never showed up. Can you refund it please?"


def percentile(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(p / 100 * (len(xs) - 1)))]


def summary(xs: list[float]) -> dict:
    return {
        "n": len(xs),
        "p50_ms": round(percentile(xs, 50) * 1000, 2),
        "p95_ms": round(percentile(xs, 95) * 1000, 2),
        "mean_ms": round(statistics.mean(xs) * 1000, 2),
    }


def ms(value: float) -> str:
    return f"{value:.0f} ms" if value >= 10 else f"{value:.2f} ms"


def no_refunds(*args, **kwargs):
    raise RuntimeError("the latency benchmark must never refund")


def setup(mode: str):
    if mode == "offline":
        paypal = PayPalSimulator()
        world = seed(paypal, Store(":memory:"))
        return paypal, world.orders["marcus_sampler"], HeuristicDetector()
    if settings.paypal_mode != "sandbox" or not settings.llm_enabled:
        sys.exit("sandbox mode needs PAYPAL_CLIENT_ID/SECRET and ANTHROPIC_API_KEY in .env")
    world = load_world(Store(settings.db_path))
    if world is None:
        sys.exit("No sandbox orders yet: start the app once so it seeds the demo shop.")
    paypal = PayPalRestClient(
        settings.paypal_client_id or "", settings.paypal_client_secret or "", settings.paypal_base_url
    )
    paypal.access_token()  # a running proxy already holds a token
    return paypal, world.orders["marcus_sampler"], ClaudeDetector()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=["offline", "sandbox"])
    p.add_argument("-n", type=int, default=20, help="decisions to time")
    args = p.parse_args()

    paypal, order_id, detector = setup(args.mode)
    paypal.refund_capture = no_refunds
    guard = AgentGuard(paypal, Store(":memory:"), detector)

    reads, risk, decisions = [], [], []
    for i in range(args.n):
        t = time.perf_counter()
        paypal.get_order(order_id)
        reads.append(time.perf_counter() - t)

        t = time.perf_counter()
        detector.assess([MESSAGE])
        risk.append(time.perf_counter() - t)

        t = time.perf_counter()
        decision = guard.submit(
            RefundRequest(order_id=order_id, amount=Decimal("48.00"), reason="not_received"),
            SessionContext(session_id=f"bench-{i}", customer_id="c_sarah", customer_messages=[MESSAGE]),
        )
        decisions.append(time.perf_counter() - t)
        assert decision.outcome.value == "block", decision.outcome

    report = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": args.mode,
        "detector": settings.utility_model if args.mode == "sandbox" else "keyword",
        "paypal": "sandbox" if args.mode == "sandbox" else "simulator",
        "paypal_order_read": summary(reads),
        "risk_assessment": summary(risk),
        "guard_decision": summary(decisions),
        "decisions_per_second_one_worker": round(args.n / sum(decisions), 1),
    }
    rows = [
        ("PayPal order read", report["paypal_order_read"]),
        ("Risk assessment", report["risk_assessment"]),
        ("Full guard decision", report["guard_decision"]),
    ]
    md = "\n".join(
        [
            f"### Guard decision latency ({args.mode}: PayPal {report['paypal']}, "
            f"detector {report['detector']}, {args.n} decisions)",
            "",
            "| Step | p50 | p95 | mean |",
            "|---|---|---|---|",
            *(f"| {name} | {ms(s['p50_ms'])} | {ms(s['p95_ms'])} | {ms(s['mean_ms'])} |" for name, s in rows),
            "",
            f"Sequential throughput on one worker: {report['decisions_per_second_one_worker']} decisions/s",
        ]
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"latency_{args.mode}.json").write_text(json.dumps(report, indent=2))
    (OUT / f"latency_{args.mode}.md").write_text(md + "\n")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
