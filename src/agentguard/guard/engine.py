"""AgentGuard: the refund decision pipeline, built as a LangGraph state graph.

    load_evidence -> assess_risk -> check_policy -> record
        record --allow----> execute
        record --escalate-> human_review --approve-> recheck -> execute
                                         '--deny---> deny
        record --block----> (end)

`human_review` pauses the graph with LangGraph's `interrupt()`. The paused run is
checkpointed (SQLite on disk, memory in tests), so the merchant can approve or deny it
later from the console, even after a restart, and the graph resumes exactly where it
stopped: re-check PayPal, then execute or not.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from ..paypal.client import PayPalGateway
from ..paypal.models import OrderFacts, PayPalError
from ..store import Store, utcnow
from .checks import HARD_CHECKS, CheckInput, run_checks, worst
from .detector import Detector, HeuristicDetector
from .models import CheckResult, Decision, Outcome, RefundRequest, RiskAssessment, SessionContext
from .policy import Policy

log = logging.getLogger(__name__)

CUSTOMER_MESSAGES = {
    Outcome.ALLOW: "Refund issued.",
    Outcome.ESCALATE: (
        "This refund needs a quick review by the shop owner. It has been queued and the "
        "customer will hear back within one business day."
    ),
    Outcome.BLOCK: "This refund can't be issued for this order.",
}
FAILED_MESSAGE = "The refund could not be processed; a person will follow up."


class GuardState(TypedDict, total=False):
    """Everything is JSON-native so checkpoints survive restarts."""

    request: dict
    context: dict
    transcript: list[dict]
    facts: dict | None
    risk: dict
    checks: list[dict]
    outcome: str
    summary: str
    decision_id: int
    status: str
    refund_id: str | None
    error: str | None
    review: dict | None


class AgentGuard:
    def __init__(
        self,
        paypal: PayPalGateway,
        store: Store,
        detector: Detector | None = None,
        checkpointer: BaseCheckpointSaver | None = None,
    ):
        self.paypal = paypal
        self.store = store
        self.detector = detector or HeuristicDetector()
        self.graph = self._build_graph().compile(checkpointer=checkpointer or _checkpointer_for(store))

    # -- policy -------------------------------------------------------------
    @property
    def policy(self) -> Policy:
        raw = self.store.get_setting("policy")
        return Policy.model_validate(raw) if raw else Policy()

    def set_policy(self, policy: Policy, source_text: str | None = None) -> None:
        self.store.set_setting("policy", policy.model_dump(mode="json"))
        if source_text is not None:
            self.store.set_setting("policy_source", source_text)

    # -- read scoping -------------------------------------------------------
    @staticmethod
    def can_read(facts: OrderFacts, customer_id: str) -> bool:
        """Order lookups are limited to the signed-in customer's own orders (PayPal custom_id)."""
        return facts.customer_id == customer_id

    # -- public API -----------------------------------------------------------
    def submit(
        self, request: RefundRequest, context: SessionContext, transcript: list[dict] | None = None
    ) -> Decision:
        """Run the pipeline. Returns once the refund executed, was blocked, or paused for review."""
        config = _thread(uuid.uuid4().hex)
        self.graph.invoke(
            {
                "request": request.model_dump(mode="json"),
                "context": context.model_dump(mode="json"),
                "transcript": transcript or [],
            },
            config,
        )
        return self._decision(self.graph.get_state(config).values)

    def approve(self, decision_id: int, reviewer: str = "merchant", note: str = "") -> dict:
        return self._resume(decision_id, approved=True, reviewer=reviewer, note=note)

    def deny(self, decision_id: int, reviewer: str = "merchant", note: str = "") -> dict:
        return self._resume(decision_id, approved=False, reviewer=reviewer, note=note)

    def _resume(self, decision_id: int, approved: bool, reviewer: str, note: str) -> dict:
        row = self.store.get_decision(decision_id)
        if row is None:
            raise KeyError(f"decision {decision_id} not found")
        if row["status"] != "pending" or row["outcome"] != Outcome.ESCALATE.value or not row["thread_id"]:
            raise ValueError(f"decision {decision_id} is {row['status']}, not awaiting review")
        answer = {"approved": approved, "reviewer": reviewer, "note": note, "at": utcnow().isoformat()}
        self.graph.invoke(Command(resume=answer), _thread(row["thread_id"]))
        return self.store.get_decision(decision_id)

    def mermaid(self) -> str:
        return self.graph.get_graph().draw_mermaid()

    # -- graph ------------------------------------------------------------------
    def _build_graph(self) -> StateGraph:
        g = StateGraph(GuardState)
        g.add_node("load_evidence", self._load_evidence)
        g.add_node("assess_risk", self._assess_risk)
        g.add_node("check_policy", self._check_policy)
        g.add_node("record", self._record)
        g.add_node("human_review", self._human_review)
        g.add_node("recheck", self._recheck)
        g.add_node("execute", self._execute)
        g.add_node("deny", self._deny)

        g.add_edge(START, "load_evidence")
        g.add_edge("load_evidence", "assess_risk")
        g.add_edge("assess_risk", "check_policy")
        g.add_edge("check_policy", "record")
        g.add_conditional_edges(
            "record",
            lambda s: {"allow": "execute", "escalate": "human_review", "block": END}[s["outcome"]],
            ["execute", "human_review", END],
        )
        g.add_conditional_edges(
            "human_review", lambda s: "recheck" if s["review"]["approved"] else "deny", ["recheck", "deny"]
        )
        g.add_conditional_edges(
            "recheck", lambda s: END if s.get("status") == "denied" else "execute", ["execute", END]
        )
        g.add_edge("execute", END)
        g.add_edge("deny", END)
        return g

    def _load_evidence(self, state: GuardState) -> GuardState:
        """Ground truth comes from PayPal, never from the conversation."""
        facts = self._facts(state["request"]["order_id"])
        return {"facts": facts.model_dump(mode="json") if facts else None}

    def _assess_risk(self, state: GuardState) -> GuardState:
        """The Claude risk agent reads what the customer said. It can only escalate, never approve."""
        context = SessionContext.model_validate(state["context"])
        claim = state["request"].get("customer_claim") or ""
        messages = context.customer_messages or ([claim] if claim else [])
        return {"risk": self.detector.assess(messages).model_dump(mode="json")}

    def _check_policy(self, state: GuardState) -> GuardState:
        request, context, facts = _models(state)
        risk = RiskAssessment.model_validate(state["risk"])
        checks = run_checks(CheckInput(request, context, facts, self.policy, risk, self.store))
        outcome = worst(checks)
        return {
            "checks": [c.model_dump(mode="json") for c in checks],
            "outcome": outcome.value,
            "summary": _summary(outcome, request, checks),
        }

    def _record(self, state: GuardState, config: RunnableConfig) -> GuardState:
        request, context, facts = _models(state)
        outcome = Outcome(state["outcome"])
        # Allowed refunds stay "pending" until PayPal confirms, so concurrent requests see them.
        status = "blocked" if outcome == Outcome.BLOCK else "pending"
        decision_id = self.store.insert_decision(
            {
                "session_id": context.session_id,
                "customer_id": context.customer_id or (facts.customer_id if facts else None) or "operator",
                "order_id": request.order_id,
                "capture_id": facts.capture_id if facts else None,
                "amount": f"{request.amount:.2f}",
                "reason": request.reason,
                "claim": request.customer_claim,
                "outcome": outcome.value,
                "status": status,
                "checks": state["checks"],
                "risk": state["risk"],
                "summary": state["summary"],
                "transcript": state.get("transcript", []),
                "mode": context.channel,
                "thread_id": config["configurable"]["thread_id"],
            }
        )
        return {"decision_id": decision_id, "status": status}

    def _human_review(self, state: GuardState) -> GuardState:
        # Nothing before interrupt(): LangGraph re-runs this node from the top on resume.
        answer = interrupt(
            {"decision_id": state["decision_id"], "summary": state["summary"], "checks": state["checks"]}
        )
        return {"review": answer}

    def _recheck(self, state: GuardState) -> GuardState:
        """The order may have changed while the request sat in the queue."""
        request, context, _ = _models(state)
        facts = self._facts(request.order_id)
        checks = run_checks(
            CheckInput(request, context, facts, self.policy, RiskAssessment(score=0), self.store),
            HARD_CHECKS,
        )
        if worst(checks) == Outcome.BLOCK:
            reason = "; ".join(c.detail for c in checks if c.outcome == Outcome.BLOCK)
            error = f"Re-check failed: {reason}"
            self.store.update_decision(state["decision_id"], status="denied", error=error, **_resolved(state))
            return {"status": "denied", "error": error}
        return {"facts": facts.model_dump(mode="json") if facts else None}

    def _execute(self, state: GuardState) -> GuardState:
        request, _, facts = _models(state)
        reviewed = bool(state.get("review"))
        decision_id = state["decision_id"]
        capture_id = facts.capture_id if facts else ""
        try:
            refund = self.paypal.refund_capture(
                capture_id=capture_id or "",
                amount=request.amount,
                currency=facts.currency if facts else "USD",
                note=f"Refund for order {request.order_id}",
                # Unique per payment and decision: decision ids restart when the demo database is reset.
                request_id=f"agentguard-{capture_id}-{decision_id}",
            )
        except PayPalError as exc:
            log.error("PayPal refund failed for decision %s: %s", decision_id, exc)
            extra = _resolved(state) if reviewed else {}
            self.store.update_decision(decision_id, status="failed", error=str(exc), **extra)
            return {"status": "failed", "error": str(exc)}
        status = "approved" if reviewed else "executed"
        extra = _resolved(state) if reviewed else {}
        self.store.update_decision(decision_id, status=status, refund_id=refund.refund_id, **extra)
        return {"status": status, "refund_id": refund.refund_id}

    def _deny(self, state: GuardState) -> GuardState:
        self.store.update_decision(state["decision_id"], status="denied", **_resolved(state))
        return {"status": "denied"}

    # -- helpers ------------------------------------------------------------------
    def _facts(self, order_id: str) -> OrderFacts | None:
        try:
            return self.paypal.get_order(order_id)
        except PayPalError as exc:
            if exc.status in (400, 404, 422):
                return None
            raise

    def _decision(self, state: dict[str, Any]) -> Decision:
        request, context, facts = _models(state)
        outcome = Outcome(state["outcome"])
        status = state.get("status", "pending")
        message = FAILED_MESSAGE if status == "failed" else CUSTOMER_MESSAGES[outcome]
        return Decision(
            id=state.get("decision_id"),
            outcome=outcome,
            status=status,
            request=request,
            context=context,
            checks=[CheckResult.model_validate(c) for c in state["checks"]],
            risk=RiskAssessment.model_validate(state["risk"]),
            summary=state["summary"],
            customer_message=message,
            capture_id=facts.capture_id if facts else None,
            refund_id=state.get("refund_id"),
            error=state.get("error"),
        )


def _thread(thread_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id}}


def _models(state: dict[str, Any]) -> tuple[RefundRequest, SessionContext, OrderFacts | None]:
    facts = state.get("facts")
    return (
        RefundRequest.model_validate(state["request"]),
        SessionContext.model_validate(state["context"]),
        OrderFacts.model_validate(facts) if facts else None,
    )


def _resolved(state: GuardState) -> dict[str, str]:
    review = state.get("review") or {}
    return {
        "resolved_by": review.get("reviewer", "merchant"),
        "resolved_note": review.get("note", ""),
        "resolved_at": review.get("at") or utcnow().isoformat(),
    }


def _checkpointer_for(store: Store) -> BaseCheckpointSaver:
    """Checkpoints live next to the decision database, or in memory for in-memory stores."""
    if store.path is None:
        return InMemorySaver()
    path = Path(store.path)
    conn = sqlite3.connect(str(path.with_name(f"{path.stem}-graph.db")), check_same_thread=False)
    return SqliteSaver(conn)


def _summary(outcome: Outcome, request: RefundRequest, checks: list[CheckResult]) -> str:
    head = f"${request.amount:.2f} refund on {request.order_id} ({request.reason.replace('_', ' ')})"
    flagged = [c for c in checks if c.outcome != Outcome.ALLOW]
    if not flagged:
        return f"Allowed: {head}. All {len(checks)} checks passed."
    verb = "Blocked" if outcome == Outcome.BLOCK else "Needs review"
    reasons = " ".join(c.detail for c in flagged if c.outcome == outcome) or flagged[0].detail
    return f"{verb}: {head}. {reasons}"
